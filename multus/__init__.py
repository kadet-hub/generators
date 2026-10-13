"""Multus CNI generator for Kapitan.

Generates Multus CNI resources for Kubernetes multi-network attachments:
- NetworkAttachmentDefinition: Define additional network interfaces for pods

Multus is a meta CNI plugin that enables attaching multiple network interfaces
to pods in Kubernetes.

Schema reference: k8s.cni.cncf.io/v1
See: https://github.com/k8snetworkplumbingwg/multus-cni
"""

__version__ = "1.0.1"

import json
import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


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


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge user-provided `spec` dict into the resource spec verbatim."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when a flat abstraction key would overwrite a value from `spec`."""
    spec = _convert_to_dict(config.get("spec")) or {}
    if not spec:
        return
    flat = _convert_to_dict(config)
    for flat_key, crd_key in mapping.items():
        flat_value, spec_value = flat, spec
        for part in flat_key.split("."):
            flat_value = flat_value.get(part) if isinstance(flat_value, dict) else None
        for part in crd_key.split("."):
            spec_value = spec_value.get(part) if isinstance(spec_value, dict) else None
        if flat_value is not None and spec_value is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


# =============================================================================
# Base Multus Resource Class
# =============================================================================


def _default_namespace() -> str:
    """Namespace fallback chain: generators.multus.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("multus", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


class MultusBase(k8s.Base):
    """Base class for Multus resources with common metadata patterns."""

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", _default_namespace())

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Add common metadata fields from config."""
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# =============================================================================
# NetworkAttachmentDefinition
# =============================================================================


class NetworkAttachmentDefinition(MultusBase):
    """Multus NetworkAttachmentDefinition resource.

    Defines an additional network interface that can be attached to pods via
    the ``k8s.v1.cni.cncf.io/networks`` annotation.

    The CNI configuration is provided either as a pre-built JSON string via
    ``config_json``, or as a structured dict via ``cni_config`` which is
    serialised to JSON automatically.

    Required kwargs:
        name: Resource name.
        config: NetworkAttachmentDefinition configuration dictionary.

    Example config (structured)::

        bridge-network:
          namespace: kube-system
          cni_config:
            type: bridge
            bridge: br0
            isGateway: true
            ipMasq: true
            ipam:
              type: host-local
              subnet: 192.168.1.0/24
              routes:
                - dst: 0.0.0.0/0

    Example config (raw JSON)::

        macvlan-network:
          namespace: kube-system
          config_json: |
            {"type":"macvlan","master":"eth1","mode":"bridge","ipam":{"type":"dhcp"}}
    """

    _FLAT_KEY_MAP = {
        "config_json": "config",
        "cni_config": "config",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "k8s.cni.cncf.io/v1"
        self.kwargs.kind = "NetworkAttachmentDefinition"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)
        # Multus matches this annotation against the device plugin or DRA
        # resource name to pass the allocated deviceID to the CNI plugin.
        if config.get("resource_name"):
            self.add_annotation(
                "k8s.v1.cni.cncf.io/resourceName", config["resource_name"]
            )
        self._build_spec(config)

    def _build_spec(self, config: dict) -> None:
        """Build the NetworkAttachmentDefinition spec."""
        spec = self.root.spec

        # 1. Passthrough — merge any unmodelled fields first.
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # 2. Explicit abstractions — flat keys take precedence.
        # config_json takes precedence – user supplies a raw JSON/config string
        raw_json = config.get("config_json")
        if raw_json:
            spec.config = raw_json
            return

        # Structured cni_config dict – serialise to JSON
        cni_config = config.get("cni_config")
        if cni_config:
            cni_dict = _convert_to_dict(cni_config)
            # Inject name into CNI config if not already present
            if "name" not in cni_dict:
                cni_dict["name"] = self.kwargs.name
            spec.config = json.dumps(cni_dict, indent=2, sort_keys=True)


# =============================================================================
# main()
# =============================================================================


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for Kapitan kadet.

    Reads ``generators.multus.networks`` from inventory and generates
    NetworkAttachmentDefinition resources.

    Args:
        input_params: Optional input parameters (unused).

    Returns:
        BaseObj containing generated Multus resources.
    """
    obj = BaseObj()

    multus_config = inv.parameters.get("generators", {}).get("multus", {}) or {}
    multus_config = _convert_to_dict(multus_config)

    default_namespace = multus_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )
    for network_name, network_config in multus_config.get("networks", {}).items():
        network_config_dict = _convert_to_dict(network_config) or {}
        namespace = network_config_dict.get("namespace", default_namespace)
        nad = NetworkAttachmentDefinition(
            name=network_name,
            config=network_config_dict,
        )
        obj.root[f"{namespace}/{network_name}-net-attach-def"] = nad

    return obj


__all__ = [
    "NetworkAttachmentDefinition",
    "MultusBase",
    "main",
    "inv",
    "k8s",
]
