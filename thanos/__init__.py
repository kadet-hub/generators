"""Thanos Operator resource generators for Kapitan.

Renders monitoring.thanos.io/v1alpha1 ThanosQuery, ThanosReceive, ThanosRuler,
ThanosStore and ThanosCompact; see README.md for the inventory contract.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.1"

API_VERSION = "monitoring.thanos.io/v1alpha1"

# Secret key used by every upstream sample, component doc and integration test.
OBJECT_STORAGE_KEY = "thanos.yaml"

# Replica labels of Prometheus Operator, ThanosReceive ingesters and
# ThanosRuler; the upstream ThanosQuery sample deduplicates on all three.
REPLICA_LABELS = ["prometheus_replica", "replica", "rule_replica"]


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.thanos.namespace -> parameters.namespace -> "default"."""
    generator_config = inv.parameters.get("generators", {}).get("thanos", {}) or {}
    return str(
        generator_config.get("namespace") or inv.parameters.get("namespace", "default")
    )


def _object_storage(value: Any) -> Any:
    """``<secret>`` -> ``{name: <secret>, key: thanos.yaml}``; a dict passes through."""
    if isinstance(value, str):
        return {"name": value, "key": OBJECT_STORAGE_KEY}
    return _convert_to_dict(value)


def _shared_object_storage() -> Any:
    """generators.thanos.object_storage_config, the default for every kind."""
    generator_config = inv.parameters.get("generators", {}).get("thanos", {}) or {}
    return _object_storage(generator_config.get("object_storage_config"))


def _setdefault(target: Any, key: str, value: Any) -> Any:
    """Set ``target[key]`` to a copy of *value* unless the inventory set it."""
    if target.get(key) is None and value is not None:
        target[key] = copy.deepcopy(value)
    return target.get(key)


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


# Top-level spec fields shared by the single-workload components (Query,
# Ruler, Store, Compact). The CRD spec.labels / spec.annotations fields are
# deliberately absent: the resource-level keys set metadata instead.
_COMPONENT_KEYS = {
    "additional_args": "additionalArgs",
    "additional_containers": "additionalContainers",
    "additional_env": "additionalEnv",
    "additional_ports": "additionalPorts",
    "additional_service_ports": "additionalServicePorts",
    "additional_volume_mounts": "additionalVolumeMounts",
    "additional_volumes": "additionalVolumes",
    "affinity": "affinity",
    "base_image": "baseImage",
    "config_maps": "configMaps",
    "image_pull_policy": "imagePullPolicy",
    "image_pull_secrets": "imagePullSecrets",
    "log_format": "logFormat",
    "log_level": "logLevel",
    "node_selector": "nodeSelector",
    "paused": "paused",
    "pod_disruption_budget_config": "podDisruptionBudgetConfig",
    "resource_requirements": "resourceRequirements",
    "secrets": "secrets",
    "security_context": "securityContext",
    "tolerations": "tolerations",
    "topology_spread_constraints": "topologySpreadConstraints",
    "version": "version",
}

# Top-level spec fields of the StatefulSet-backed kinds.
_STATEFUL_KEYS = {
    "min_ready_seconds": "minReadySeconds",
    "persistent_volume_claim_retention_policy": "persistentVolumeClaimRetentionPolicy",
    "pod_management_policy": "podManagementPolicy",
    "termination_grace_period_seconds": "terminationGracePeriodSeconds",
}


class ThanosResource(k8s.Base):
    """One Thanos Operator custom resource; subclasses set kind and _FLAT_KEY_MAP.

    Required kwargs: name, config (inventory entry).
    """

    KIND = ""
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)

        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for flat_key, crd_key in self._FLAT_KEY_MAP.items():
            _set_field(spec, config, flat_key, target_key=crd_key)
        self.defaults(spec, config)

    def defaults(self, spec: Any, config: dict) -> None:
        """Fill what the inventory left out; see README.md for each source."""

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


class _ObjectStorageResource(ThanosResource):
    """Expands ``object_storage_config: <secret>``; defaults to the shared one."""

    def defaults(self, spec: Any, config: dict) -> None:
        if isinstance(config.get("object_storage_config"), str):
            spec.objectStorageConfig = _object_storage(config["object_storage_config"])
        _setdefault(spec, "objectStorageConfig", _shared_object_storage())


class ThanosQuery(ThanosResource):
    KIND = "ThanosQuery"
    _FLAT_KEY_MAP = {
        **_COMPONENT_KEYS,
        "custom_store_label_selector": "customStoreLabelSelector",
        "grpc_proxy_strategy": "grpcProxyStrategy",
        "query_frontend": "queryFrontend",
        "replica_labels": "replicaLabels",
        "replicas": "replicas",
        "telemetry_quantiles": "telemetryQuantiles",
        "web_config": "webConfig",
    }

    def defaults(self, spec: Any, config: dict) -> None:
        _setdefault(spec, "replicas", 1)
        _setdefault(spec, "replicaLabels", REPLICA_LABELS)


class ThanosReceive(ThanosResource):
    KIND = "ThanosReceive"
    _FLAT_KEY_MAP = {
        **_STATEFUL_KEYS,
        "ingester_spec": "ingesterSpec",
        "paused": "paused",
        "router_spec": "routerSpec",
    }

    def defaults(self, spec: Any, config: dict) -> None:
        router = _setdefault(spec, "routerSpec", {})
        _setdefault(router, "replicas", 1)
        _setdefault(router, "replicationFactor", 1)
        _setdefault(router, "externalLabels", {"receive": "true"})
        ingester = _setdefault(spec, "ingesterSpec", {})
        _setdefault(ingester, "defaultObjectStorageConfig", _shared_object_storage())
        for hashring in ingester.get("hashrings") or []:
            _setdefault(hashring, "replicas", 1)
            _setdefault(hashring, "externalLabels", {"replica": "$(POD_NAME)"})
            _setdefault(_setdefault(hashring, "tsdbConfig", {}), "retention", "2h")


class ThanosRuler(ThanosResource):
    KIND = "ThanosRuler"
    _FLAT_KEY_MAP = {
        **_COMPONENT_KEYS,
        **_STATEFUL_KEYS,
        "alert_label_drop": "alertLabelDrop",
        "alertmanager_url": "alertmanagerURL",
        "evaluation_interval": "evaluationInterval",
        "query_label_selector": "queryLabelSelector",
        "replicas": "replicas",
        "rule_config_selector": "ruleConfigSelector",
        "rule_tenancy_config": "ruleTenancyConfig",
        "ruler_mode": "rulerMode",
        "storage": "storage",
    }

    def defaults(self, spec: Any, config: dict) -> None:
        _setdefault(spec, "replicas", 1)
        _setdefault(
            spec,
            "ruleConfigSelector",
            {"matchLabels": {"operator.thanos.io/prometheus-rule": "true"}},
        )
        mode = _setdefault(spec, "rulerMode", {})
        _setdefault(mode, "type", "Stateful")
        if mode.get("type") == "Stateful":
            stateful = _setdefault(mode, "stateful", {})
            _setdefault(stateful, "objectStorageConfig", _shared_object_storage())
            _setdefault(stateful, "retention", "2h")
            _setdefault(stateful, "externalLabels", {"rule_replica": "$(NAME)"})


class ThanosStore(_ObjectStorageResource):
    KIND = "ThanosStore"
    _FLAT_KEY_MAP = {
        **_COMPONENT_KEYS,
        **_STATEFUL_KEYS,
        "block_config": "blockConfig",
        "caching_bucket_config": "cachingBucketConfig",
        "ignore_deletion_marks_delay": "ignoreDeletionMarksDelay",
        "index_cache_config": "indexCacheConfig",
        "index_header_config": "indexHeaderConfig",
        "object_storage_config": "objectStorageConfig",
        "replicas": "replicas",
        "sharding_strategy": "shardingStrategy",
        "storage": "storage",
        "store_limits_options": "storeLimitsOptions",
        "time_range_config": "timeRangeConfig",
    }

    def defaults(self, spec: Any, config: dict) -> None:
        super().defaults(spec, config)
        _setdefault(spec, "replicas", 1)
        _setdefault(_setdefault(spec, "shardingStrategy", {}), "type", "block")


class ThanosCompact(_ObjectStorageResource):
    KIND = "ThanosCompact"
    _FLAT_KEY_MAP = {
        **_COMPONENT_KEYS,
        **_STATEFUL_KEYS,
        "block_config": "blockConfig",
        "block_viewer_global_sync": "blockViewerGlobalSync",
        "compact_config": "compactConfig",
        "debug_config": "debugConfig",
        "downsampling_config": "downsamplingConfig",
        "object_storage_config": "objectStorageConfig",
        "retention_config": "retentionConfig",
        "sharding_config": "shardingConfig",
        "storage": "storage",
        "time_range_config": "timeRangeConfig",
        "vertical_compaction_config": "verticalCompactionConfig",
    }

    def defaults(self, spec: Any, config: dict) -> None:
        super().defaults(spec, config)
        retention = _setdefault(spec, "retentionConfig", {})
        shorthand = config.get("retention")
        flat = config.get("retention_config") or {}
        for resolution in ("raw", "fiveMinutes", "oneHour"):
            if shorthand is None or resolution in flat:
                _setdefault(retention, resolution, "0d")
                continue
            if retention.get(resolution) is not None:
                logger.warning(
                    "Shorthand 'retention' overrides spec passthrough "
                    "'retentionConfig.%s' for resource '%s'",
                    resolution,
                    self.kwargs.name,
                )
            retention[resolution] = shorthand
        concurrency = (spec.get("compactConfig") or {}).get("compactConcurrency") or 1
        _setdefault(spec, "resourceRequirements", {"requests": {"cpu": concurrency}})


SECTIONS = (
    ("thanos_queries", ThanosQuery),
    ("thanos_receives", ThanosReceive),
    ("thanos_rulers", ThanosRuler),
    ("thanos_stores", ThanosStore),
    ("thanos_compacts", ThanosCompact),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.thanos."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("thanos", {}) or {}
    )
    default_namespace = _default_namespace()
    for section, resource_class in SECTIONS:
        for name, config in (generator_config.get(section) or {}).items():
            config = config or {}
            namespace = config.get("namespace") or default_namespace
            key = f"{namespace}/{name}-{resource_class.KIND.lower()}"
            obj.root[key] = resource_class(name=name, config=config)
    return obj


__all__ = [
    "API_VERSION",
    "ThanosCompact",
    "ThanosQuery",
    "ThanosReceive",
    "ThanosResource",
    "ThanosRuler",
    "ThanosStore",
    "inv",
    "k8s",
    "main",
]
