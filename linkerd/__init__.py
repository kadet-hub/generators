"""Linkerd service mesh policy generators for Kapitan."""

import logging
from typing import Any


__version__ = "1.0.0"

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
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


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when a flat abstraction key will override a value from `spec`."""
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


def _default_namespace() -> str:
    """Namespace fallback chain: generators.linkerd.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("linkerd", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


POLICY_GROUP = "policy.linkerd.io"
# Kinds that exist only in policy.linkerd.io. Linkerd reads a ref without
# group as the core group, so such a ref would never match.
_POLICY_KINDS = ("Server", "MeshTLSAuthentication", "NetworkAuthentication")
_AUTHENTICATION_SECTIONS = {
    "meshtls_authentications": "MeshTLSAuthentication",
    "network_authentications": "NetworkAuthentication",
}


def _policy_ref(ref: Any) -> Any:
    """Add the policy.linkerd.io group to a ref of a policy-only kind without one."""
    if isinstance(ref, dict) and ref.get("kind") in _POLICY_KINDS and "group" not in ref:
        return {**ref, "group": POLICY_GROUP}
    return ref


def _authentication_ref(ref: Any, namespace: str, policy: str) -> Any:
    """Resolve a bare name to the generator's MeshTLS/NetworkAuthentication entry."""
    if not isinstance(ref, str):
        return ref
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("linkerd", {}) or {}
    )
    found = [
        (kind, (generator_config.get(section) or {})[ref] or {})
        for section, kind in _AUTHENTICATION_SECTIONS.items()
        if ref in (generator_config.get(section) or {})
    ]
    if len(found) != 1:
        raise ValueError(
            f"linkerd AuthorizationPolicy '{policy}': required_authentication_refs "
            f"entry '{ref}' must name exactly one entry of meshtls_authentications "
            "or network_authentications; write other refs as a dict"
        )
    kind, entry = found[0]
    result = {"group": POLICY_GROUP, "kind": kind, "name": ref}
    ref_namespace = entry.get("namespace", _default_namespace())
    if ref_namespace != namespace:
        result["namespace"] = ref_namespace
    return result


class LinkerdServer(k8s.Base):
    _FLAT_KEY_MAP = {
        "selector_labels": "podSelector",
        "port": "port",
    }

    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1beta3"
        self.kwargs.kind = "Server"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_label("server", self.kwargs.name)
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        # Passthrough first; modelled flat keys win below.
        spec_override = config.get("spec")
        if spec_override:
            self.root.spec.update(_convert_to_dict(spec_override))
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        selector_labels = config.get("selector_labels")
        if selector_labels:
            self.root.spec.podSelector.matchLabels = _convert_to_dict(selector_labels)
        elif "podSelector" not in self.root.spec:
            # An empty matchLabels would select every pod in the namespace.
            raise ValueError(
                f"linkerd Server '{self.kwargs.name}' needs a selector: set "
                "selector_labels or spec.podSelector"
            )
        if config.get("port"):
            self.root.spec.port = config.get("port")


class LinkerdServerAuthorization(k8s.Base):
    _FLAT_KEY_MAP = {
        "selector_labels": "server",
        "client": "client",
    }

    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1beta1"
        self.kwargs.kind = "ServerAuthorization"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        # Passthrough first; modelled flat keys win below.
        spec_override = config.get("spec")
        if spec_override:
            self.root.spec.update(_convert_to_dict(spec_override))
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        if config.get("selector_labels"):
            self.root.spec.server.selector.matchLabels = _convert_to_dict(
                config.get("selector_labels")
            )
        if config.get("client"):
            self.root.spec.client = _convert_to_dict(config.get("client"))


class LinkerdServiceProfile(k8s.Base):
    def new(self) -> None:
        self.kwargs.apiVersion = "linkerd.io/v1alpha2"
        self.kwargs.kind = "ServiceProfile"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        if config.get("spec"):
            self.root.spec = config.get("spec")


class LinkerdAuthorizationPolicy(k8s.Base):
    _FLAT_KEY_MAP = {
        "target_ref": "targetRef",
        "required_authentication_refs": "requiredAuthenticationRefs",
    }

    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1alpha1"
        self.kwargs.kind = "AuthorizationPolicy"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        namespace = config.get("namespace", _default_namespace())
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(namespace)

        # Passthrough first; modelled flat keys win below.
        spec_override = config.get("spec")
        if spec_override:
            self.root.spec.update(_convert_to_dict(spec_override))
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        target_ref = config.get("target_ref")
        if isinstance(target_ref, str):
            target_ref = {"group": POLICY_GROUP, "kind": "Server", "name": target_ref}
        if target_ref is not None:
            self.root.spec.targetRef = target_ref
        refs = config.get("required_authentication_refs")
        if refs is not None:
            self.root.spec.requiredAuthenticationRefs = [
                _authentication_ref(ref, namespace, self.kwargs.name) for ref in refs
            ]

        spec = self.root.spec
        if "targetRef" in spec:
            spec.targetRef = _policy_ref(_convert_to_dict(spec.targetRef))
        if "requiredAuthenticationRefs" in spec:
            spec.requiredAuthenticationRefs = [
                _policy_ref(ref)
                for ref in _convert_to_dict(spec.requiredAuthenticationRefs)
            ]


class LinkerdHttpRoute(k8s.Base):
    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1beta2"
        self.kwargs.kind = "HTTPRoute"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        if config.get("spec"):
            self.root.spec = config.get("spec")


class LinkerdMeshTLSAuthentication(k8s.Base):
    _FLAT_KEY_MAP = {
        "identities": "identities",
        "identity_refs": "identityRefs",
    }

    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1alpha1"
        self.kwargs.kind = "MeshTLSAuthentication"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        # Passthrough first; modelled flat keys win below.
        spec_override = config.get("spec")
        if spec_override:
            self.root.spec.update(_convert_to_dict(spec_override))
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        if config.get("identities") is not None:
            self.root.spec.identities = config.get("identities")
        if config.get("identity_refs") is not None:
            self.root.spec.identityRefs = [
                {"kind": "ServiceAccount", "name": ref} if isinstance(ref, str) else ref
                for ref in config.get("identity_refs")
            ]


class LinkerdNetworkAuthentication(k8s.Base):
    _FLAT_KEY_MAP = {"networks": "networks"}

    def new(self) -> None:
        self.kwargs.apiVersion = "policy.linkerd.io/v1alpha1"
        self.kwargs.kind = "NetworkAuthentication"

        super().new()
        self.need("name")

    def body(self) -> None:
        super().body()

        config = self.kwargs.config
        default_namespace = _default_namespace()
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))
        self.add_namespace(config.get("namespace", default_namespace))

        # Passthrough first; modelled flat keys win below.
        spec_override = config.get("spec")
        if spec_override:
            self.root.spec.update(_convert_to_dict(spec_override))
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        if config.get("networks") is not None:
            self.root.spec.networks = [
                {"cidr": network} if isinstance(network, str) else network
                for network in config.get("networks")
            ]


def main(input_params=None) -> BaseObj:
    """Generate Linkerd resources from inventory.

    Reads from parameters.generators.linkerd:
    - servers: Server configurations
    - server_authorizations: ServerAuthorization configurations
    - service_profiles: ServiceProfile configurations
    - authorization_policies: AuthorizationPolicy configurations
    - http_routes: HTTPRoute configurations
    - meshtls_authentications: MeshTLSAuthentication configurations
    - network_authentications: NetworkAuthentication configurations
    """
    obj = BaseObj()

    # Get linkerd config from generators namespace
    linkerd_config = inv.parameters.get("generators", {}).get("linkerd", {}) or {}
    default_namespace = _default_namespace()

    # Generate Servers
    for name, config in linkerd_config.get("servers", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-server"] = LinkerdServer(name=name, config=config)

    # Generate ServerAuthorizations
    for name, config in linkerd_config.get("server_authorizations", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-serverauth"] = LinkerdServerAuthorization(
            name=name, config=config
        )

    # Generate ServiceProfiles
    for name, config in linkerd_config.get("service_profiles", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-serviceprofile"] = LinkerdServiceProfile(
            name=name, config=config
        )

    # Generate AuthorizationPolicies
    for name, config in linkerd_config.get("authorization_policies", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-authpolicy"] = LinkerdAuthorizationPolicy(
            name=name, config=config
        )

    # Generate HTTPRoutes
    for name, config in linkerd_config.get("http_routes", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-httproute"] = LinkerdHttpRoute(
            name=name, config=config
        )

    # Generate MeshTLSAuthentications
    for name, config in linkerd_config.get("meshtls_authentications", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-meshtlsauth"] = LinkerdMeshTLSAuthentication(
            name=name, config=config
        )

    # Generate NetworkAuthentications
    for name, config in linkerd_config.get("network_authentications", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-networkauth"] = LinkerdNetworkAuthentication(
            name=name, config=config
        )

    return obj


__all__ = [
    "LinkerdServer",
    "LinkerdServerAuthorization",
    "LinkerdServiceProfile",
    "LinkerdAuthorizationPolicy",
    "LinkerdHttpRoute",
    "LinkerdMeshTLSAuthentication",
    "LinkerdNetworkAuthentication",
    "main",
    "k8s",
    "inv",
    "_convert_to_dict",
]
