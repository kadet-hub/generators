"""External Secrets Operator resource generators for Kapitan.

Renders external-secrets.io/v1 SecretStore, ClusterSecretStore,
ExternalSecret and ClusterExternalSecret. Provider blocks pass through
unchanged; see README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


__version__ = "1.0.5"

logger = logging.getLogger(__name__)

inv = inventory()

API_VERSION = "external-secrets.io/v1"

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


def _error(kind: str, name: str, reason: str) -> ValueError:
    return ValueError(f"external-secrets {kind} '{name}': {reason}")


class ExternalSecretsResource(k8s.Base):
    """One ESO custom resource. Namespace is omitted for cluster-scoped kinds.

    Required kwargs:
        kind, name, config: inventory entry, spec: rendered spec.
    Optional kwargs:
        namespace
    """

    def new(self) -> None:
        self.need("config")
        self.need("spec")
        self.kwargs.apiVersion = API_VERSION
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        if self.kwargs.get("namespace"):
            self.add_namespace(self.kwargs.namespace)
        self.add_labels(config.get("labels") or {})
        self.add_annotations(config.get("annotations") or {})
        self.root.spec = self.kwargs.spec


def _store_spec(kind: str, name: str, config: dict) -> dict:
    spec = config.get("spec")
    if not spec:
        raise _error(kind, name, "'spec' is required")
    return spec


# Flat inventory key -> ExternalSecret spec key. Flat keys win over `spec`.
_FLAT_KEY_MAP = {
    "store": "secretStoreRef",
    "cluster_store": "secretStoreRef",
    "refresh_interval": "refreshInterval",
}


def _secret_spec(
    kind: str, name: str, config: dict, generator_config: dict, namespace: str | None
) -> dict:
    spec = config.get("spec") or {}
    # ClusterExternalSecret wraps the ExternalSecret spec in externalSecretSpec.
    target = spec.setdefault("externalSecretSpec", {}) if namespace is None else spec

    store = config.get("store")
    cluster_store = config.get("cluster_store")
    if store and cluster_store:
        raise _error(kind, name, "set either 'store' or 'cluster_store', not both")

    for flat_key, crd_key in _FLAT_KEY_MAP.items():
        if config.get(flat_key) is not None and crd_key in target:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for %s '%s'",
                flat_key,
                crd_key,
                kind,
                name,
            )

    if store:
        target["secretStoreRef"] = {"kind": "SecretStore", "name": store}
    elif cluster_store:
        target["secretStoreRef"] = {"kind": "ClusterSecretStore", "name": cluster_store}

    if config.get("refresh_interval") is not None:
        target["refreshInterval"] = config["refresh_interval"]
    elif "refreshInterval" not in target and not config.get("allow_default_refresh"):
        raise _error(
            kind,
            name,
            "'refresh_interval' is required (or set allow_default_refresh: true)",
        )

    store_kind = (target.get("secretStoreRef") or {}).get("kind")
    if (
        generator_config.get("deny_cluster_scoped")
        and store_kind == "ClusterSecretStore"
    ):
        raise _error(
            kind, name, "ClusterSecretStore reference denied by deny_cluster_scoped"
        )

    prefix = generator_config.get("namespace_key_prefix")
    if prefix:
        if namespace is None:
            raise _error(
                kind,
                name,
                "namespace_key_prefix cannot be enforced: keys are shared across namespaces",
            )
        _check_remote_keys(kind, name, target, f"{prefix.rstrip('/')}/{namespace}/")

    return spec


def _check_remote_keys(kind: str, name: str, spec: dict, required: str) -> None:
    keys = [(item.get("remoteRef") or {}).get("key") for item in spec.get("data") or []]
    for item in spec.get("dataFrom") or []:
        if "find" in item:
            raise _error(
                kind,
                name,
                "dataFrom.find cannot be checked against namespace_key_prefix",
            )
        if "extract" in item:
            keys.append(item["extract"].get("key"))
    for key in keys:
        if key is None:
            continue
        if not key.startswith(required) or ".." in key.split("/"):
            raise _error(
                kind,
                name,
                f"remote key '{key}' must start with '{required}' and must not contain '..'",
            )


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.external_secrets."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("external_secrets", {}) or {}
    )
    if not generator_config:
        return obj

    default_namespace = generator_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )
    sections = (
        ("secretstores", "SecretStore", "ss", True),
        ("clustersecretstores", "ClusterSecretStore", "css", False),
        ("externalsecrets", "ExternalSecret", "es", True),
        ("clusterexternalsecrets", "ClusterExternalSecret", "ces", False),
    )
    for section, kind, suffix, namespaced in sections:
        for key, config in (generator_config.get(section) or {}).items():
            config = config or {}
            name = config.get("name", key)
            if not namespaced and generator_config.get("deny_cluster_scoped"):
                raise _error(
                    kind, name, "cluster-scoped kind denied by deny_cluster_scoped"
                )
            namespace = (
                config.get("namespace", default_namespace) if namespaced else None
            )
            if kind.endswith("SecretStore"):
                spec = _store_spec(kind, name, config)
            else:
                spec = _secret_spec(kind, name, config, generator_config, namespace)
            output_key = (
                f"{namespace}/{name}-{suffix}" if namespaced else f"{name}-{suffix}"
            )
            obj.root[output_key] = ExternalSecretsResource(
                kind=kind, name=name, config=config, spec=spec, namespace=namespace
            )
    return obj


__all__ = ["API_VERSION", "ExternalSecretsResource", "inv", "k8s", "main"]
