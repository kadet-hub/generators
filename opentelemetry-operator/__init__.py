"""OpenTelemetry Operator resource generators for Kapitan.

Renders opentelemetry.io OpenTelemetryCollector (v1beta1), Instrumentation,
TargetAllocator and OpAMPBridge (v1alpha1); see README.md for the inventory
contract.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.0"

API_GROUP = "opentelemetry.io"
TARGET_ALLOCATOR_LABEL = "opentelemetry.io/target-allocator"


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.opentelemetry_operator.namespace -> parameters.namespace -> "default"."""
    generator_config = (
        inv.parameters.get("generators", {}).get("opentelemetry_operator", {}) or {}
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


def _flat_keys(crd_fields: str) -> dict[str, str]:
    """Map the snake_case spelling of each CRD field to the field: hostPID -> host_pid."""
    return {
        re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", f).lower(): f
        for f in crd_fields.split()
    }


# Pod-level fields shared by the collector and the target allocator.
_POD_FIELDS = """
    additionalContainers affinity args dnsPolicy enableServiceLinks env envFrom
    hostAliases hostNetwork hostPID hostUsers image imagePullPolicy initContainers
    ipFamilies ipFamilyPolicy lifecycle livenessProbe managementState networkPolicy
    nodeSelector observability podAnnotations podDisruptionBudget podDnsConfig
    podSecurityContext ports priorityClassName readinessProbe replicas resizePolicy
    resources securityContext serviceAccount sessionAffinity sessionAffinityConfig
    shareProcessNamespace terminationGracePeriodSeconds tolerations
    topologySpreadConstraints trafficDistribution volumeMounts volumes
"""


class OpenTelemetryResource(k8s.Base):
    """One OpenTelemetry Operator custom resource; subclasses set kind and keys.

    Required kwargs: name, config (inventory entry).
    """

    KIND = ""
    API_VERSION = f"{API_GROUP}/v1alpha1"
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = self.API_VERSION
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


class OpenTelemetryCollector(OpenTelemetryResource):
    KIND = "OpenTelemetryCollector"
    API_VERSION = f"{API_GROUP}/v1beta1"
    _FLAT_KEY_MAP = _flat_keys(
        _POD_FIELDS
        + """
        autoscaler command config configVersions configmaps daemonSetUpdateStrategy
        deploymentUpdateStrategy httpRoute ingress mode
        persistentVolumeClaimRetentionPolicy podManagementPolicy serviceName
        startupProbe targetAllocator upgradeStrategy volumeClaimTemplates
        """
    )

    def body(self) -> None:
        config = self.kwargs.config
        target_allocator = config.get("target_allocator")
        if isinstance(target_allocator, str):
            # Shorthand: link a standalone TargetAllocator by name.
            self.kwargs.config = {
                k: v for k, v in config.items() if k != "target_allocator"
            }
        super().body()
        if isinstance(target_allocator, str):
            self.add_label(TARGET_ALLOCATOR_LABEL, target_allocator)
        spec = self.root.spec
        embedded = spec.get("targetAllocator") or {}
        uses_ta = TARGET_ALLOCATOR_LABEL in self.root.metadata.labels or (
            embedded.get("enabled") is True
        )
        # The target allocator supports only statefulset and daemonset mode; the
        # operator defaults mode to deployment.
        if uses_ta and "mode" not in spec:
            spec["mode"] = "statefulset"


class Instrumentation(OpenTelemetryResource):
    KIND = "Instrumentation"
    _FLAT_KEY_MAP = _flat_keys(
        """
        apacheHttpd defaults dotnet env exporter go imagePullPolicy
        initContainerSecurityContext java nginx nodejs propagators python resource
        sampler
        """
    )


class TargetAllocator(OpenTelemetryResource):
    KIND = "TargetAllocator"
    _FLAT_KEY_MAP = _flat_keys(
        _POD_FIELDS
        + """
        allocationStrategy allowInsecureAuthSecrets collectorNotReadyGracePeriod
        filterStrategy global mtls prometheusCR scrapeConfigs telemetry
        """
    )


class OpAMPBridge(OpenTelemetryResource):
    KIND = "OpAMPBridge"
    _FLAT_KEY_MAP = _flat_keys(
        """
        affinity capabilities componentsAllowed description endpoint env envFrom
        headers hostNetwork image imagePullPolicy ipFamilies ipFamilyPolicy
        nodeSelector podAnnotations podDnsConfig podSecurityContext ports
        priorityClassName proxy replicas resources securityContext serviceAccount
        tls tolerations topologySpreadConstraints upgradeStrategy volumeMounts
        volumes
        """
    )


SECTIONS = (
    ("collectors", OpenTelemetryCollector, "otelcol"),
    ("instrumentations", Instrumentation, "otelinst"),
    ("target_allocators", TargetAllocator, "targetallocator"),
    ("opamp_bridges", OpAMPBridge, "opampbridge"),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.opentelemetry_operator."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("opentelemetry_operator", {}) or {}
    )
    default_namespace = _default_namespace()
    for section, resource_class, suffix in SECTIONS:
        for name, config in (generator_config.get(section) or {}).items():
            config = config or {}
            namespace = config.get("namespace") or default_namespace
            obj.root[f"{namespace}/{name}-{suffix}"] = resource_class(
                name=name, config=config
            )
    return obj


__all__ = [
    "API_GROUP",
    "Instrumentation",
    "OpAMPBridge",
    "OpenTelemetryCollector",
    "OpenTelemetryResource",
    "TargetAllocator",
    "inv",
    "k8s",
    "main",
]
