"""Calico resource generators for Kapitan.

Renders projectcalico.org/v3 NetworkPolicy, GlobalNetworkPolicy, NetworkSet,
GlobalNetworkSet, IPPool, BGPPeer and BGPConfiguration for Calico v3.33.0;
see README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.0"

API_VERSION = "projectcalico.org/v3"


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.calico_resources.namespace -> parameters.namespace -> "default"."""
    generator_config = (
        inv.parameters.get("generators", {}).get("calico_resources", {}) or {}
    )
    return str(
        generator_config.get("namespace") or inv.parameters.get("namespace", "default")
    )


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


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when flat keys will override passthrough values from ``spec``."""
    spec = _convert_to_dict(config.get("spec")) or {}
    if not spec:
        return
    for flat_key, crd_key in mapping.items():
        if config.get(flat_key) is not None and spec.get(crd_key) is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


# =============================================================================
# Shorthands
# =============================================================================

# Selector fields of a spec and of a rule's source/destination.
_SELECTOR_KEYS = (
    "selector",
    "notSelector",
    "namespaceSelector",
    "serviceAccountSelector",
    "nodeSelector",
    "peerSelector",
    "localWorkloadSelector",
)


def _label_value(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _selector(value: Any, where: str) -> Any:
    """``{k: v, ...}`` -> ``"k == 'v' && ..."``; strings pass through.

    An empty dict is refused: Calico treats an empty selector as unset, so a
    rule would match every peer.
    """
    if not isinstance(value, dict):
        return value
    if not value:
        raise ValueError(f"{where}: empty label selector; write all() to select everything")
    parts = []
    for key in sorted(value):
        label = _label_value(value[key])
        quote = '"' if "'" in label else "'"
        parts.append(f"{key} == {quote}{label}{quote}")
    return " && ".join(parts)


def _port(entry: Any, default_protocol: str | None) -> tuple[str | None, Any]:
    """``8080`` / ``"53/UDP"`` / ``"6040:6050"`` / ``"http"`` -> (protocol, port)."""
    text = str(entry)
    protocol = default_protocol
    if "/" in text:
        text, protocol = text.rsplit("/", 1)
    port: Any = int(text) if text.isdigit() else text
    return protocol, port


def _rules(rules: list, where: str) -> list:
    """Expand ``ports`` and selector dicts in a list of rules."""
    result = []
    for index, rule in enumerate(rules):
        rule = dict(rule)
        for side in ("source", "destination"):
            if isinstance(rule.get(side), dict):
                rule[side] = {
                    k: _selector(v, f"{where}[{index}].{side}.{k}") if k in _SELECTOR_KEYS else v
                    for k, v in rule[side].items()
                }
        ports = rule.pop("ports", None)
        if ports is None:
            result.append(rule)
            continue
        if not ports:
            raise ValueError(f"{where}[{index}]: empty ports; Calico would match every port")
        # Ports need a protocol (Rule.protocol in the CRD); TCP unless given.
        by_protocol: dict[str, list] = {}
        for entry in ports:
            protocol, port = _port(entry, rule.get("protocol") or "TCP")
            by_protocol.setdefault(protocol, []).append(port)
        for protocol, protocol_ports in by_protocol.items():
            expanded = dict(rule, protocol=protocol)
            destination = dict(expanded.get("destination") or {})
            destination["ports"] = list(destination.get("ports") or []) + protocol_ports
            expanded["destination"] = destination
            result.append(expanded)
    return result


# =============================================================================
# Resources
# =============================================================================


class CalicoResource(k8s.Base):
    """One projectcalico.org/v3 resource; subclasses set KIND and _FLAT_KEY_MAP.

    Required kwargs: name, config (inventory entry).
    """

    KIND = ""
    NAMESPACED = False
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        if self.NAMESPACED:
            self.add_namespace(config.get("namespace") or _default_namespace())
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))

        # Precedence: spec < flat keys < shorthand expansion of the result.
        spec = dict(_convert_to_dict(config.get("spec")) or {})
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for flat_key, crd_key in self._FLAT_KEY_MAP.items():
            if config.get(flat_key) is not None:
                spec[crd_key] = _convert_to_dict(config[flat_key])

        where = f"{self.KIND} {self.kwargs.name}"
        for key in _SELECTOR_KEYS:
            if key in spec:
                spec[key] = _selector(spec[key], f"{where}: {key}")
        for key in ("ingress", "egress"):
            if spec.get(key) is not None:
                spec[key] = _rules(spec[key], f"{where}: {key}")
        self.root.spec = spec


_POLICY_KEYS = {
    "selector": "selector",
    "service_account_selector": "serviceAccountSelector",
    "order": "order",
    "tier": "tier",
    "types": "types",
    "ingress": "ingress",
    "egress": "egress",
    "performance_hints": "performanceHints",
}


class NetworkPolicy(CalicoResource):
    KIND = "NetworkPolicy"
    NAMESPACED = True
    _FLAT_KEY_MAP = _POLICY_KEYS


class GlobalNetworkPolicy(CalicoResource):
    KIND = "GlobalNetworkPolicy"
    _FLAT_KEY_MAP = {
        **_POLICY_KEYS,
        "namespace_selector": "namespaceSelector",
        "apply_on_forward": "applyOnForward",
        "pre_dnat": "preDNAT",
        "do_not_track": "doNotTrack",
    }


class NetworkSet(CalicoResource):
    KIND = "NetworkSet"
    NAMESPACED = True
    _FLAT_KEY_MAP = {"nets": "nets"}


class GlobalNetworkSet(CalicoResource):
    KIND = "GlobalNetworkSet"
    _FLAT_KEY_MAP = {"nets": "nets"}


class IPPool(CalicoResource):
    KIND = "IPPool"
    _FLAT_KEY_MAP = {
        "cidr": "cidr",
        "block_size": "blockSize",
        "ipip_mode": "ipipMode",
        "vxlan_mode": "vxlanMode",
        "nat_outgoing": "natOutgoing",
        "node_selector": "nodeSelector",
        "namespace_selector": "namespaceSelector",
        "allowed_uses": "allowedUses",
        "assignment_mode": "assignmentMode",
        "disabled": "disabled",
        "disable_bgp_export": "disableBGPExport",
    }


class BGPPeer(CalicoResource):
    KIND = "BGPPeer"
    _FLAT_KEY_MAP = {
        "peer_ip": "peerIP",
        "as_number": "asNumber",
        "node": "node",
        "node_selector": "nodeSelector",
        "peer_selector": "peerSelector",
        "local_as_number": "localASNumber",
        "password": "password",
        "source_address": "sourceAddress",
        "next_hop_mode": "nextHopMode",
        "keepalive_time": "keepaliveTime",
        "max_restart_time": "maxRestartTime",
        "reachable_by": "reachableBy",
        "ttl_security": "ttlSecurity",
        "filters": "filters",
    }


class BGPConfiguration(CalicoResource):
    KIND = "BGPConfiguration"
    _FLAT_KEY_MAP = {
        "as_number": "asNumber",
        "node_to_node_mesh_enabled": "nodeToNodeMeshEnabled",
        "listen_port": "listenPort",
        "log_severity_screen": "logSeverityScreen",
        "service_cluster_ips": "serviceClusterIPs",
        "service_external_ips": "serviceExternalIPs",
        "service_load_balancer_ips": "serviceLoadBalancerIPs",
        "communities": "communities",
        "prefix_advertisements": "prefixAdvertisements",
        "bind_mode": "bindMode",
    }


SECTIONS = (
    ("network_policies", NetworkPolicy, "np"),
    ("global_network_policies", GlobalNetworkPolicy, "gnp"),
    ("network_sets", NetworkSet, "netset"),
    ("global_network_sets", GlobalNetworkSet, "gnetset"),
    ("ip_pools", IPPool, "ippool"),
    ("bgp_peers", BGPPeer, "bgppeer"),
    ("bgp_configurations", BGPConfiguration, "bgpconfig"),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.calico_resources."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("calico_resources", {}) or {}
    )
    default_namespace = _default_namespace()
    for section, resource_class, suffix in SECTIONS:
        for name, config in (generator_config.get(section) or {}).items():
            config = config or {}
            key = f"{name}-{suffix}"
            if resource_class.NAMESPACED:
                key = f"{config.get('namespace') or default_namespace}/{key}"
            obj.root[key] = resource_class(name=name, config=config)
    return obj


__all__ = [
    "API_VERSION",
    "BGPConfiguration",
    "BGPPeer",
    "CalicoResource",
    "GlobalNetworkPolicy",
    "GlobalNetworkSet",
    "IPPool",
    "NetworkPolicy",
    "NetworkSet",
    "inv",
    "k8s",
    "main",
]
