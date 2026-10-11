"""KEDA resource generators for Kapitan.

Renders keda.sh/v1alpha1 ScaledObject, ScaledJob, TriggerAuthentication and
ClusterTriggerAuthentication; see README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.1"

API_VERSION = "keda.sh/v1alpha1"


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.keda.namespace -> parameters.namespace -> "default"."""
    generator_config = inv.parameters.get("generators", {}).get("keda", {}) or {}
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


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge any user-supplied ``spec`` dict into *spec_target*."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set ``target[target_key]`` from ``config[source_key]`` when it is not None."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _convert_to_dict(value)


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when flat keys will override passthrough values from ``spec``."""
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


def _ref(value: Any) -> Any:
    """A bare string names the referenced object: ``x`` -> ``{name: x}``."""
    return {"name": value} if isinstance(value, str) else value


def _trigger(trigger: dict) -> dict:
    """Expand ``authentication_ref``; every other trigger key stays verbatim."""
    result = {k: v for k, v in trigger.items() if k != "authentication_ref"}
    if trigger.get("authentication_ref") is not None:
        result["authenticationRef"] = _ref(trigger["authentication_ref"])
    return result


_TRIGGER_AUTHENTICATION_KEYS = {
    "aws_secret_manager": "awsSecretManager",
    "azure_key_vault": "azureKeyVault",
    "azure_service_principal": "azureServicePrincipal",
    "bound_service_account_token": "boundServiceAccountToken",
    "config_map_target_ref": "configMapTargetRef",
    "env": "env",
    "file_path": "filePath",
    "gcp_secret_manager": "gcpSecretManager",
    "hashi_corp_vault": "hashiCorpVault",
    "oauth2": "oauth2",
    "pod_identity": "podIdentity",
    "secret_target_ref": "secretTargetRef",
}


class KedaResource(k8s.Base):
    """One KEDA custom resource; subclasses set kind and _FLAT_KEY_MAP.

    Required kwargs: name, config (inventory entry).
    """

    KIND = ""
    NAMESPACED = True
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=self.NAMESPACED)

        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for flat_key, crd_key in self._FLAT_KEY_MAP.items():
            _set_field(spec, config, flat_key, target_key=crd_key)

        if config.get("triggers") is not None:
            spec.triggers = [_trigger(t) for t in _convert_to_dict(config["triggers"])]

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace") or _default_namespace()

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Populate metadata from *config*."""
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


class ScaledObject(KedaResource):
    KIND = "ScaledObject"
    _FLAT_KEY_MAP = {
        "scale_target_ref": "scaleTargetRef",
        "triggers": "triggers",
        "min_replica_count": "minReplicaCount",
        "max_replica_count": "maxReplicaCount",
        "idle_replica_count": "idleReplicaCount",
        "polling_interval": "pollingInterval",
        "cooldown_period": "cooldownPeriod",
        "initial_cooldown_period": "initialCooldownPeriod",
        "fallback": "fallback",
        "advanced": "advanced",
    }

    def body(self) -> None:
        super().body()
        if self.kwargs.config.get("scale_target_ref") is not None:
            self.root.spec.scaleTargetRef = _ref(self.root.spec.scaleTargetRef)


class ScaledJob(KedaResource):
    KIND = "ScaledJob"
    _FLAT_KEY_MAP = {
        "job_target_ref": "jobTargetRef",
        "triggers": "triggers",
        "env_source_container_name": "envSourceContainerName",
        "min_replica_count": "minReplicaCount",
        "max_replica_count": "maxReplicaCount",
        "polling_interval": "pollingInterval",
        "successful_jobs_history_limit": "successfulJobsHistoryLimit",
        "failed_jobs_history_limit": "failedJobsHistoryLimit",
        "scaling_strategy": "scalingStrategy",
        "rollout": "rollout",
    }


class TriggerAuthentication(KedaResource):
    KIND = "TriggerAuthentication"
    _FLAT_KEY_MAP = _TRIGGER_AUTHENTICATION_KEYS


class ClusterTriggerAuthentication(KedaResource):
    KIND = "ClusterTriggerAuthentication"
    NAMESPACED = False
    _FLAT_KEY_MAP = _TRIGGER_AUTHENTICATION_KEYS


SECTIONS = (
    ("scaled_objects", ScaledObject, "so"),
    ("scaled_jobs", ScaledJob, "sj"),
    ("trigger_authentications", TriggerAuthentication, "ta"),
    ("cluster_trigger_authentications", ClusterTriggerAuthentication, "cta"),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.keda."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("keda", {}) or {}
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
    "ClusterTriggerAuthentication",
    "KedaResource",
    "ScaledJob",
    "ScaledObject",
    "TriggerAuthentication",
    "inv",
    "k8s",
    "main",
]
