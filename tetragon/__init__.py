"""Kapitan kadet generator for Tetragon policies (cilium.io/v1alpha1).

Reads parameters.generators.tetragon and renders TracingPolicy and
TracingPolicyNamespaced; see README.md for the inventory contract and
docs/specs/tetragon.md for the requirements.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "0.1.0"

API_VERSION = "cilium.io/v1alpha1"

#: TET-6: flat key -> top-level spec field; values pass through unchanged (DEC-1).
FLAT_KEY_MAP = {
    "kprobes": "kprobes",
    "tracepoints": "tracepoints",
    "uprobes": "uprobes",
    "usdts": "usdts",
    "lsmhooks": "lsmhooks",
    "fentries": "fentries",
    "enforcers": "enforcers",
    "lists": "lists",
    "options": "options",
    "loader": "loader",
    "pod_selector": "podSelector",
    "container_selector": "containerSelector",
    "host_selector": "hostSelector",
    "selectors_macros": "selectorsMacros",
}


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj / OmegaConf objects to plain Python dicts."""
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


def _default_namespace(generator_config: dict) -> str:
    """TET-2: generators.tetragon.namespace -> parameters.namespace -> "default"."""
    return str(
        generator_config.get("namespace")
        or inv.parameters.get("namespace")
        or "default"
    )


class TetragonPolicy(k8s.Base):
    """Shared metadata and spec handling; subclasses set KIND."""

    KIND = ""

    def new(self) -> None:
        self.need("name")
        self.need("config")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        if self.kwargs.get("namespace"):
            self.add_namespace(self.kwargs.namespace)
        self.add_annotations(config.get("annotations") or {})
        self.add_labels(config.get("labels") or {})
        spec = dict(config.get("spec") or {})
        for flat_key, crd_key in FLAT_KEY_MAP.items():
            if config.get(flat_key) is None:
                continue
            if crd_key in spec:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    flat_key,
                    crd_key,
                    self.kwargs.name,
                )
            spec[crd_key] = config[flat_key]
        self.root.spec = spec


class TracingPolicy(TetragonPolicy):
    KIND = "TracingPolicy"


class TracingPolicyNamespaced(TetragonPolicy):
    KIND = "TracingPolicyNamespaced"


#: inventory section -> (resource class, namespaced)
SECTIONS: dict[str, tuple[type[TetragonPolicy], bool]] = {
    "tracing_policies": (TracingPolicy, False),
    "tracing_policies_namespaced": (TracingPolicyNamespaced, True),
}


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("tetragon", {}) or {}
    )
    default_namespace = _default_namespace(generator_config)
    for section, (resource_class, namespaced) in SECTIONS.items():
        rendered: dict[str, str] = {}
        for key, config in (generator_config.get(section) or {}).items():
            config = config or {}
            # TET-3: the resource takes the entry's name, else its key.
            name = config.get("name") or key
            namespace = (config.get("namespace") or default_namespace) if namespaced else None
            suffix = resource_class.KIND.lower()
            output = f"{namespace}/{name}-{suffix}" if namespaced else f"{name}-{suffix}"
            if output in rendered:
                where = f" in namespace '{namespace}'" if namespaced else ""
                raise ValueError(
                    f"tetragon: {section} '{rendered[output]}' and '{key}' both render '{name}'{where}"
                )
            rendered[output] = key
            obj.root[output] = resource_class(name=name, namespace=namespace, config=config)
    return obj


__all__ = ["TracingPolicy", "TracingPolicyNamespaced", "main"]
