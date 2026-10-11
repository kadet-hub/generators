"""Cilium network policy generator for Kapitan.

Generates Cilium CRDs for network policy management:
- CiliumNetworkPolicy: Namespace-scoped network policies with L3-L7 support
- CiliumClusterwideNetworkPolicy: Cluster-scoped policies, also supports NodeSelector
- CiliumLoadBalancerIPPool: LB-IPAM IP pool management
- CiliumL2AnnouncementPolicy: L2 aware load-balancer announcement policy

API group: cilium.io/v2
See: https://docs.cilium.io/en/stable/network/kubernetes/policy/
     https://docs.cilium.io/en/stable/security/policy/
     https://docs.cilium.io/en/latest/network/lb-ipam/
     https://docs.cilium.io/en/latest/network/l2-announcements/
"""

__version__ = "1.0.0"

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

CILIUM_API_VERSION = "cilium.io/v2"
CILIUM_API_VERSION_V2ALPHA1 = "cilium.io/v2alpha1"


# =============================================================================
# Helper Functions
# =============================================================================


try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES: tuple[type, ...] = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj/kadet/OmegaConf objects to plain dicts."""
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


def _build_selector(selector: dict) -> dict:
    """Convert a selector dict from snake_case inventory keys to camelCase.

    Handles:
    - ``match_labels``  → ``matchLabels``
    - ``match_expressions`` → ``matchExpressions``

    Any unknown keys are passed through as-is (supports users writing
    camelCase directly in the inventory).
    """
    result: dict[str, Any] = {}
    for key, value in selector.items():
        if key == "match_labels":
            result["matchLabels"] = value
        elif key == "match_expressions":
            result["matchExpressions"] = _convert_to_dict(value)
        else:
            # pass-through: user wrote camelCase already
            result[key] = _convert_to_dict(value)
    return result


# Upstream DNS proxy rule for toFQDNs policies:
# https://github.com/cilium/cilium/blob/v1.20.2/examples/policies/l3/fqdn/fqdn.yaml
_KUBE_DNS = {
    "k8s:io.kubernetes.pod.namespace": "kube-system",
    "k8s:k8s-app": "kube-dns",
}
_RULE_LISTS = ("ingress", "egress", "ingressDeny", "egressDeny")


def _dns_rule(patterns: Any) -> dict:
    """Egress rule to kube-dns with an L7 DNS rule; True allows every name."""
    if patterns is True:
        patterns = ["*"]
    return {
        "toEndpoints": [{"matchLabels": dict(_KUBE_DNS)}],
        "toPorts": [
            {
                "ports": [{"port": "53"}],
                "rules": {"dns": [{"matchPattern": p} for p in patterns]},
            }
        ],
    }


def _port(entry: Any) -> dict:
    """``8080``, ``"53/UDP"`` or ``"http"`` -> PortProtocol."""
    port, _, protocol = str(entry).partition("/")
    return {"port": port, "protocol": protocol.upper()} if protocol else {"port": port}


def _expand_ports(rule: dict) -> dict:
    """Rule shorthand ``ports: [...]`` -> one ``toPorts`` entry."""
    if "ports" not in rule:
        return rule
    rule = dict(rule)
    ports = rule.pop("ports")
    rule["toPorts"] = list(rule.get("toPorts") or []) + [
        {"ports": [_port(p) for p in ports]}
    ]
    return rule


def _block(entry: Any) -> Any:
    """``"192.0.2.0/28"`` -> cidr block, ``"<start>-<stop>"`` -> range block."""
    if not isinstance(entry, str):
        return entry
    if "-" in entry:
        start, stop = entry.split("-", 1)
        return {"start": start.strip(), "stop": stop.strip()}
    return {"cidr": entry}


# =============================================================================
# Base Cilium Resource Class
# =============================================================================


def _set_flat_fields(
    spec: Any,
    config: dict,
    fields: dict[str, str],
    *,
    selectors: tuple[str, ...] = (),
) -> None:
    """Set CRD fields from flat config keys; selector keys get case mapping."""
    for flat_key, crd_key in fields.items():
        value = config.get(flat_key)
        if value is None:
            continue
        if flat_key in selectors:
            spec[crd_key] = _build_selector(_convert_to_dict(value))
        else:
            spec[crd_key] = _convert_to_dict(value)


def _default_namespace() -> str:
    """Namespace fallback chain: generators.cilium.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("cilium", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


class CiliumBase(k8s.Base):
    """Base class for Cilium policy resources."""

    _FIELD_MAP = {
        "endpoint_selector": "endpointSelector",
        "node_selector": "nodeSelector",
        "description": "description",
        "enable_default_deny": "enableDefaultDeny",
        "ingress": "ingress",
        "egress": "egress",
    }

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", _default_namespace())

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))

    def _validate_policy_selectors(
        self, config: dict, *, allow_node_selector: bool
    ) -> None:
        """Enforce the selector contract for policy resources."""
        spec_override = _convert_to_dict(config.get("spec") or {})
        has_endpoint = (
            config.get("endpoint_selector") is not None
            or "endpointSelector" in spec_override
        )
        has_node = (
            config.get("node_selector") is not None or "nodeSelector" in spec_override
        )
        if allow_node_selector:
            # For CiliumClusterwideNetworkPolicy either selector is valid
            if not has_endpoint and not has_node:
                raise ValueError(
                    "Either 'endpoint_selector' or 'node_selector' must be specified "
                    "for CiliumClusterwideNetworkPolicy."
                )
        elif not has_endpoint:
            # For CiliumNetworkPolicy endpointSelector is mandatory
            raise ValueError("'endpoint_selector' is required for CiliumNetworkPolicy.")

    def _build_spec(self, config: dict, *, allow_node_selector: bool) -> None:
        """Populate ``self.root.spec`` from *config*."""
        spec = self.root.spec

        # 1. Passthrough — merge any unmodelled fields first.
        _merge_spec_passthrough(spec, config)

        # 2. Explicit abstractions — flat keys take precedence.
        self._validate_policy_selectors(config, allow_node_selector=allow_node_selector)
        fields = self._FIELD_MAP
        if not allow_node_selector:
            # node_selector is only valid on the clusterwide policy
            fields = {k: v for k, v in fields.items() if k != "node_selector"}
            if config.get("node_selector") is not None:
                logger.warning(
                    "cilium: 'node_selector' is ignored on CiliumNetworkPolicy %s; "
                    "it is only valid on CiliumClusterwideNetworkPolicy",
                    self.kwargs.name,
                )
        _set_flat_fields(
            spec,
            config,
            fields,
            selectors=("endpoint_selector", "node_selector"),
        )

        # 3. Shorthands.
        allow_dns = config.get("allow_dns")
        if allow_dns:
            spec.egress = _convert_to_dict(spec.get("egress") or []) + [
                _dns_rule(_convert_to_dict(allow_dns))
            ]
        for key in _RULE_LISTS:
            if key in spec:
                spec[key] = [_expand_ports(r) for r in _convert_to_dict(spec[key])]


# =============================================================================
# CiliumNetworkPolicy  (namespaced)
# =============================================================================


class CiliumNetworkPolicy(CiliumBase):
    """Namespace-scoped Cilium network policy (L3-L7).

    Required kwargs:
        name: Policy name.
        config: Policy configuration dict.

    ``config`` keys:

    - ``namespace`` - target namespace (default: ``inv.parameters.namespace``)
    - ``endpoint_selector`` - **required** label selector for matched endpoints
    - ``ingress`` - list of ingress rule objects (passed through)
    - ``egress`` - list of egress rule objects (passed through)
    - ``description`` - human-readable description
    - ``enable_default_deny`` - ``{ingress: bool, egress: bool}``
    - ``labels`` / ``annotations`` - metadata
    - ``spec`` - passthrough for any unmodelled CRD fields
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = CILIUM_API_VERSION
        self.kwargs.kind = "CiliumNetworkPolicy"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config, include_namespace=True)
        _warn_collisions(config, self._FIELD_MAP, self.kwargs.name)
        self._build_spec(config, allow_node_selector=False)


# =============================================================================
# CiliumClusterwideNetworkPolicy  (cluster-scoped)
# =============================================================================


class CiliumClusterwideNetworkPolicy(CiliumBase):
    """Cluster-scoped Cilium network policy (L3-L7).

    Unlike :class:`CiliumNetworkPolicy`, this resource is cluster-scoped and
    supports ``node_selector`` in addition to ``endpoint_selector``.

    Required kwargs:
        name: Policy name.
        config: Policy configuration dict.

    ``config`` keys:

    - ``endpoint_selector`` - selector for matched endpoints (mutually exclusive
      with ``node_selector``)
    - ``node_selector`` - selector for matched nodes (only valid here)
    - ``ingress`` - list of ingress rule objects (passed through)
    - ``egress`` - list of egress rule objects (passed through)
    - ``description`` - human-readable description
    - ``enable_default_deny`` - ``{ingress: bool, egress: bool}``
    - ``labels`` / ``annotations`` - metadata
    - ``spec`` - passthrough for any unmodelled CRD fields
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = CILIUM_API_VERSION
        self.kwargs.kind = "CiliumClusterwideNetworkPolicy"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        # Cluster-scoped: no namespace
        self._add_common_metadata(config, include_namespace=False)
        _warn_collisions(config, self._FIELD_MAP, self.kwargs.name)
        self._build_spec(config, allow_node_selector=True)


# =============================================================================
# CiliumLoadBalancerIPPool
# =============================================================================


class CiliumLoadBalancerIPPool(CiliumBase):
    """Cilium LB-IPAM IP pool resource.

    Defines a pool of IP addresses that Cilium can assign to Services of type
    LoadBalancer.

    Required kwargs:
        name: Pool name.
        config: Pool configuration dict.

    ``config`` keys:

    - ``blocks`` - list of IP blocks (e.g. ``[{"cidr": "10.0.0.0/24"}]`` or
      ``[{"start": "10.0.0.1", "stop": "10.0.0.9"}]``)
    - ``cidrs`` - legacy alias for ``blocks`` (spec.cidrs was removed in
      cilium.io/v2)
    - ``disabled`` - boolean to disable the pool
    - ``labels`` / ``annotations`` - metadata
    - ``spec`` - passthrough for any unmodelled CRD fields
    """

    _FIELD_MAP = {
        "blocks": "blocks",
        "cidrs": "blocks",
        "disabled": "disabled",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = CILIUM_API_VERSION
        self.kwargs.kind = "CiliumLoadBalancerIPPool"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        # CiliumLoadBalancerIPPool is cluster-scoped upstream
        self._add_common_metadata(config, include_namespace=False)
        _warn_collisions(config, self._FIELD_MAP, self.kwargs.name)
        self._build_pool_spec(config)

    def _build_pool_spec(self, config: dict) -> None:
        """Build the CiliumLoadBalancerIPPool spec."""
        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _set_flat_fields(spec, config, self._FIELD_MAP)
        if "blocks" in spec:
            spec.blocks = [_block(b) for b in _convert_to_dict(spec.blocks)]


# =============================================================================
# CiliumL2AnnouncementPolicy
# =============================================================================


class CiliumL2AnnouncementPolicy(CiliumBase):
    """Cilium L2 announcement policy resource.

    Controls which nodes announce IPs for LoadBalancer services via L2
    (ARP/NDP).

    Required kwargs:
        name: Policy name.
        config: Policy configuration dict.

    ``config`` keys:

    - ``node_selector`` - node selector for announcement
    - ``service_selector`` - service selector for announcement
    - ``interfaces`` - list of interface names to announce on
    - ``external_ips`` - boolean to announce external IPs
    - ``load_balancer_ips`` - boolean to announce LB IPs
    - ``labels`` / ``annotations`` - metadata
    - ``spec`` - passthrough for any unmodelled CRD fields
    """

    _FIELD_MAP = {
        "node_selector": "nodeSelector",
        "service_selector": "serviceSelector",
        "interfaces": "interfaces",
        "external_ips": "externalIPs",
        "load_balancer_ips": "loadBalancerIPs",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = CILIUM_API_VERSION_V2ALPHA1
        self.kwargs.kind = "CiliumL2AnnouncementPolicy"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        # Cluster-scoped: no namespace
        self._add_common_metadata(config, include_namespace=False)
        _warn_collisions(config, self._FIELD_MAP, self.kwargs.name)
        self._build_l2_spec(config)

    def _build_l2_spec(self, config: dict) -> None:
        """Build the CiliumL2AnnouncementPolicy spec."""
        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _set_flat_fields(
            spec,
            config,
            self._FIELD_MAP,
            selectors=("node_selector", "service_selector"),
        )
        # Both flags default to false upstream, so a policy without either
        # announces nothing:
        # https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/l2-announcements.rst?plain=1#L158-L163
        if "externalIPs" not in spec and "loadBalancerIPs" not in spec:
            spec.loadBalancerIPs = True


# =============================================================================
# main()
# =============================================================================

# inventory key → (resource class, output suffix, namespace-scoped)
RESOURCE_MAP = {
    "network_policies": (CiliumNetworkPolicy, "cnp", True),
    "clusterwide_policies": (CiliumClusterwideNetworkPolicy, "ccnp", False),
    "lb_ip_pools": (CiliumLoadBalancerIPPool, "lbippool", False),
    "l2_announcement_policies": (CiliumL2AnnouncementPolicy, "l2ap", False),
}


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for Kapitan kadet.

    Reads ``generators.cilium`` from inventory and generates:

    - ``CiliumNetworkPolicy`` resources (from ``network_policies`` key)
    - ``CiliumClusterwideNetworkPolicy`` resources (from ``clusterwide_policies`` key)
    - ``CiliumLoadBalancerIPPool`` resources (from ``lb_ip_pools`` key)
    - ``CiliumL2AnnouncementPolicy`` resources (from ``l2_announcement_policies`` key)

    Output keys follow the pattern:
    - ``<namespace>/<name>-cnp`` for CiliumNetworkPolicy
    - ``<name>-ccnp`` for CiliumClusterwideNetworkPolicy
    - ``<name>-lbippool`` for CiliumLoadBalancerIPPool
    - ``<name>-l2ap`` for CiliumL2AnnouncementPolicy

    Args:
        input_params: Unused; present for Kapitan kadet compatibility.

    Returns:
        BaseObj containing all generated Cilium resources.
    """
    obj = BaseObj()

    cilium_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("cilium", {}) or {}
    )

    default_namespace = _default_namespace()

    for inventory_key, (resource_cls, suffix, namespaced) in RESOURCE_MAP.items():
        for name, config in cilium_config.get(inventory_key, {}).items():
            config = _convert_to_dict(config) or {}
            resource = resource_cls(name=name, config=config)
            if namespaced:
                namespace = config.get("namespace", default_namespace)
                obj.root[f"{namespace}/{name}-{suffix}"] = resource
            else:
                obj.root[f"{name}-{suffix}"] = resource

    return obj


__all__ = [
    "CiliumNetworkPolicy",
    "CiliumClusterwideNetworkPolicy",
    "CiliumLoadBalancerIPPool",
    "CiliumL2AnnouncementPolicy",
    "CiliumBase",
    "main",
    "inv",
    "k8s",
    "CILIUM_API_VERSION",
    "CILIUM_API_VERSION_V2ALPHA1",
    "_convert_to_dict",
    "_build_selector",
    "_merge_spec_passthrough",
    "_warn_collisions",
]
