"""Utility functions for Kubernetes resource generation.

This module provides helper functions and utilities used across the Kubernetes
generator, including template rendering, dictionary merging, and component iteration.
"""

import base64
import copy
from typing import Any, Generator, cast

from box import Box

from kapitan.inputs.kadet import BaseObj, inventory
from kapitan.inputs.kadet import search_paths as _kadet_search_paths
from kapitan.utils import render_jinja2_file


def get_search_paths() -> list[str]:
    """Search paths of the compile item being rendered, ["."] outside a compile.

    Read on every call: kapitan sets them per compile item, and the
    `kapitan.cached.args` global is being removed upstream (kapicorp/kapitan#1532).
    """
    return cast("list[str]", _kadet_search_paths.get(["."]))


class _CurrentInventory:
    """Inventory of the target being compiled, resolved on every access.

    Kapitan re-runs only this package's __init__ per target; submodules stay
    cached in the worker process, so an inventory bound at import time kept
    serving the first target's values to later targets (kapicorp/kapitan#1611).
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(inventory(), name)


inv: Any = _CurrentInventory()


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert OmegaConf / BaseObj objects to plain Python dicts."""
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        from omegaconf import OmegaConf

        return _convert_to_dict(OmegaConf.to_container(obj, resolve=True))
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "root"):
        return _convert_to_dict(obj.root)
    if isinstance(obj, dict):
        return {k: _convert_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_to_dict(item) for item in obj]
    return obj


def _is_dict_like(obj: Any) -> bool:
    """Check if obj behaves like a dict (including OmegaConf DictConfig)."""
    if isinstance(obj, dict):
        return True
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        return True
    return False


def get_namespace(config: dict | None = None, default: str | None = None) -> str | None:
    """Get namespace from config, falling back to inventory parameters.

    This safely handles OmegaConf DictConfig objects that return empty dicts
    when accessing non-existent keys via attribute access.

    Args:
        config: Optional config dict to check for 'namespace' key first.
        default: Default value if no namespace is found anywhere.

    Returns:
        The namespace string, or default if not found.
    """
    # First check config if provided
    if config is not None:
        ns = config.get("namespace")
        if ns and isinstance(ns, str):
            return ns

    # Fall back to inventory parameters using .get() to avoid empty dicts
    ns = inv.parameters.get("namespace")
    if ns and isinstance(ns, str):
        return ns

    return default


def pod_labels(workload: Any) -> Any:
    """Pod template labels of a rendered workload, CronJobs included, without auto-vivifying."""
    spec = workload.get("spec") or {}
    if "jobTemplate" in spec:
        spec = spec["jobTemplate"].get("spec") or {}
    return ((spec.get("template") or {}).get("metadata") or {}).get("labels") or {}


def j2(filename: str, ctx: dict[str, Any]) -> str:
    """Render a Jinja2 template file.

    Args:
        filename: Path to the Jinja2 template file.
        ctx: Context dictionary for template rendering.

    Returns:
        Rendered template content as a string.
    """
    return cast(
        "str", render_jinja2_file(filename, ctx, search_paths=get_search_paths())
    )


def merge(source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
    """Deep merge source dict into destination dict.

    Recursively merges source into destination. For nested dictionaries,
    the merge is recursive. For other values, source values do not
    overwrite existing destination values.

    Args:
        source: Source dictionary to merge from.
        destination: Destination dictionary to merge into.

    Returns:
        The merged destination dictionary.
    """
    for key, value in source.items():
        if _is_dict_like(value):
            node = destination.get(key)
            if node is None:
                # Copy: inserting by reference aliases shared default
                # sub-dicts across components (a later in-place mutation
                # would leak into every consumer).
                destination[key] = copy.deepcopy(value)
            else:
                merge(value, node)
        elif key not in destination or destination[key] is None:
            destination[key] = (
                copy.deepcopy(value) if isinstance(value, list) else value
            )

    return destination


def encode_string(unencoded_string: str) -> str:
    """Base64 encode a string.

    Args:
        unencoded_string: Plain text string to encode.

    Returns:
        Base64 encoded string.
    """
    return base64.b64encode(unencoded_string.encode("utf-8")).decode("ascii")


def get_components() -> Generator[tuple[str, Any], None, None]:
    """Generator that yields enabled components with merged defaults.

    Iterates through all components defined in the inventory and yields
    those that are enabled. For each component, default configurations
    are merged in from generator defaults and application defaults.

    Yields:
        Tuple of (component_name, component_config) for each enabled component.
    """
    if "components" in inv.parameters:
        manifest = inv.parameters.get("generators", {}).get("manifest", {})
        generator_defaults = manifest.get("default_config", {})
        resource_defaults = manifest.get("resource_defaults", {})

        for name, component in inv.parameters.get("components", {}).items():
            if component.get("enabled", True):
                if "application" in component:
                    application_defaults = (
                        inv.parameters.get("applications", {})
                        .get(component.get("application"), {})
                        .get("component_defaults", {})
                    )
                    merge(generator_defaults, application_defaults)
                    if component.get("type", "undefined") in component.get(
                        "globals", {}
                    ):
                        merge(
                            application_defaults,
                            component.get("globals", {}).get(component.get("type"), {}),
                        )
                    merge(application_defaults, component)

                merge(generator_defaults, component)
                # kapitan-reference default: untyped components are Deployments
                component_type = component.get("type") or "deployment"
                component.type = component_type
                if component_type in resource_defaults:
                    merge(resource_defaults[component_type], component)

                component.name = name
                # Wrap OmegaConf DictConfig in Box for consistent attribute access
                if _OMEGACONF_TYPES and isinstance(component, _OMEGACONF_TYPES):
                    component = Box(_convert_to_dict(component), default_box=True)
                yield name, component


def generate_docs(input_params):
    """Generate documentation for components."""
    obj = BaseObj()
    template = input_params.get("template_path", None)
    if template:
        for name, component in get_components():
            obj.root[f"{name}-readme.md"] = j2(
                template,
                {
                    "service_component": component.dump(),
                    "inventory": inv.parameters.dump(),
                },
            )
    return obj
