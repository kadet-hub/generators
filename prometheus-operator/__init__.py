"""Prometheus Operator resource generators for Kapitan.

Renders monitoring.coreos.com Prometheus, PrometheusAgent, Alertmanager,
AlertmanagerConfig, ThanosRuler, Probe, ScrapeConfig, ServiceMonitor,
PodMonitor and PrometheusRule from ``parameters.generators.prometheus_operator``.
Common fields are flat snake_case keys; ``spec`` passes everything else
through. ``rbac: true`` on a Prometheus or PrometheusAgent adds its
ServiceAccount, ClusterRole and ClusterRoleBinding. Shorthands expand
selectors, storage sizes, Probe targets, scrape endpoints, namespace lists and
a single rule group. ``release_label`` adds the kube-prometheus-stack
``release`` label to the kinds that chart selects by it. See README.md for the
inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


__version__ = "1.1.3"

logger = logging.getLogger(__name__)

inv = inventory()

GROUP = "monitoring.coreos.com"

_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """Namespace when a resource sets none (repo convention).

    generators.prometheus_operator.namespace -> parameters.namespace -> "default".
    """
    generator_config = (
        inv.parameters.get("generators", {}).get("prometheus_operator", {}) or {}
    )
    return generator_config.get("namespace") or inv.parameters.get(
        "namespace", "default"
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


def _expand(flat_key: str, value: Any) -> Any:
    """Expand a shorthand to its CRD form; any other value passes through."""
    if flat_key == "namespace_selector" and isinstance(value, list):
        return {"matchNames": value}
    if flat_key in ("endpoints", "pod_metrics_endpoints"):
        if isinstance(value, str):
            return [{"port": value}]
        if isinstance(value, list):
            return [{"port": v} if isinstance(v, str) else v for v in value]
    if (
        (flat_key == "selector" or flat_key.endswith("_selector"))
        and flat_key != "namespace_selector"
        and isinstance(value, dict)
        and value
        and not {"matchLabels", "matchExpressions"} & value.keys()
    ):
        return {"matchLabels": value}
    if flat_key == "storage" and isinstance(value, str):
        return {"volumeClaimTemplate": {"spec": {"resources": {"requests": {"storage": value}}}}}
    if flat_key == "prober" and isinstance(value, str):
        return {"url": value}
    if flat_key == "targets" and isinstance(value, list):
        return {"staticConfig": {"static": value}}
    return value


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set ``target[target_key]`` from ``config[source_key]`` when it is not None."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _expand(source_key, _convert_to_dict(value))


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


# =============================================================================
# Custom resources
# =============================================================================


class PrometheusOperatorBase(k8s.Base):
    """One namespaced monitoring.coreos.com CR: metadata, passthrough, flat keys."""

    API_VERSION = f"{GROUP}/v1"
    KIND = ""
    _FLAT_KEY_MAP: dict[str, str] = {}
    # kube-prometheus-stack selects this kind by the label release: <release>.
    _RELEASE_SELECTED = False

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = self.API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        self.root.spec = {}
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
        release = self.kwargs.get("release_label")
        if self._RELEASE_SELECTED and release:
            self.add_label("release", release)
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# Shared by Prometheus and PrometheusAgent (CommonPrometheusFields upstream).
_COMMON_PROMETHEUS_KEYS = {
    "service_account_name": "serviceAccountName",
    "replicas": "replicas",
    "shards": "shards",
    "version": "version",
    "image": "image",
    "scrape_interval": "scrapeInterval",
    "external_labels": "externalLabels",
    "resources": "resources",
    "storage": "storage",
    "remote_write": "remoteWrite",
    "service_monitor_selector": "serviceMonitorSelector",
    "service_monitor_namespace_selector": "serviceMonitorNamespaceSelector",
    "pod_monitor_selector": "podMonitorSelector",
    "pod_monitor_namespace_selector": "podMonitorNamespaceSelector",
    "probe_selector": "probeSelector",
    "probe_namespace_selector": "probeNamespaceSelector",
    "scrape_config_selector": "scrapeConfigSelector",
    "scrape_config_namespace_selector": "scrapeConfigNamespaceSelector",
}


class Prometheus(PrometheusOperatorBase):
    KIND = "Prometheus"
    _FLAT_KEY_MAP = {
        **_COMMON_PROMETHEUS_KEYS,
        "retention": "retention",
        "retention_size": "retentionSize",
        "evaluation_interval": "evaluationInterval",
        "rule_selector": "ruleSelector",
        "rule_namespace_selector": "ruleNamespaceSelector",
        "alerting": "alerting",
    }


class PrometheusAgent(PrometheusOperatorBase):
    API_VERSION = f"{GROUP}/v1alpha1"
    KIND = "PrometheusAgent"
    _FLAT_KEY_MAP = {**_COMMON_PROMETHEUS_KEYS, "mode": "mode"}


class Alertmanager(PrometheusOperatorBase):
    KIND = "Alertmanager"
    _FLAT_KEY_MAP = {
        "replicas": "replicas",
        "retention": "retention",
        "service_account_name": "serviceAccountName",
        "config_secret": "configSecret",
        "alertmanager_config_selector": "alertmanagerConfigSelector",
        "alertmanager_config_namespace_selector": "alertmanagerConfigNamespaceSelector",
        "storage": "storage",
    }


class AlertmanagerConfig(PrometheusOperatorBase):
    API_VERSION = f"{GROUP}/v1alpha1"
    KIND = "AlertmanagerConfig"
    _FLAT_KEY_MAP = {
        "route": "route",
        "receivers": "receivers",
        "inhibit_rules": "inhibitRules",
        "mute_time_intervals": "muteTimeIntervals",
    }


class ThanosRuler(PrometheusOperatorBase):
    KIND = "ThanosRuler"
    _FLAT_KEY_MAP = {
        "replicas": "replicas",
        "retention": "retention",
        "evaluation_interval": "evaluationInterval",
        "rule_selector": "ruleSelector",
        "rule_namespace_selector": "ruleNamespaceSelector",
        "query_endpoints": "queryEndpoints",
        "query_config": "queryConfig",
        "alertmanagers_url": "alertmanagersUrl",
        "alertmanagers_config": "alertmanagersConfig",
        "service_account_name": "serviceAccountName",
    }


class Probe(PrometheusOperatorBase):
    KIND = "Probe"
    _RELEASE_SELECTED = True
    _FLAT_KEY_MAP = {
        "prober": "prober",
        "module": "module",
        "targets": "targets",
        "interval": "interval",
        "scrape_timeout": "scrapeTimeout",
        "job_name": "jobName",
    }


class ScrapeConfig(PrometheusOperatorBase):
    API_VERSION = f"{GROUP}/v1alpha1"
    KIND = "ScrapeConfig"
    _RELEASE_SELECTED = True
    _FLAT_KEY_MAP = {
        "job_name": "jobName",
        "static_configs": "staticConfigs",
        "kubernetes_sd_configs": "kubernetesSDConfigs",
        "http_sd_configs": "httpSDConfigs",
        "scrape_interval": "scrapeInterval",
        "metrics_path": "metricsPath",
        "scheme": "scheme",
    }


class ServiceMonitor(PrometheusOperatorBase):
    KIND = "ServiceMonitor"
    _RELEASE_SELECTED = True
    _FLAT_KEY_MAP = {
        "selector": "selector",
        "namespace_selector": "namespaceSelector",
        "endpoints": "endpoints",
        "job_label": "jobLabel",
        "target_labels": "targetLabels",
        "pod_target_labels": "podTargetLabels",
        "sample_limit": "sampleLimit",
    }


class PodMonitor(PrometheusOperatorBase):
    KIND = "PodMonitor"
    _RELEASE_SELECTED = True
    _FLAT_KEY_MAP = {
        "selector": "selector",
        "namespace_selector": "namespaceSelector",
        "pod_metrics_endpoints": "podMetricsEndpoints",
        "job_label": "jobLabel",
        "pod_target_labels": "podTargetLabels",
        "sample_limit": "sampleLimit",
    }


class PrometheusRule(PrometheusOperatorBase):
    """``rules: [...]`` is one group named after the resource."""

    KIND = "PrometheusRule"
    _RELEASE_SELECTED = True
    _FLAT_KEY_MAP = {"groups": "groups"}

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        rules = config.get("rules")
        if rules is None:
            return
        if config.get("groups") is not None:
            raise ValueError(
                f"prometheus-operator PrometheusRule '{self.kwargs.name}': "
                "set either rules or groups, not both"
            )
        _warn_collisions(config, {"rules": "groups"}, self.kwargs.name)
        self.root.spec.groups = [
            {"name": self.kwargs.name, "rules": _convert_to_dict(rules)}
        ]


# =============================================================================
# Implicit RBAC (rbac: true on Prometheus / PrometheusAgent)
# =============================================================================

# Upstream Documentation/platform/rbac.md: what Prometheus needs for service
# discovery and scraping. The agent discovers targets the same way.
RBAC_RULES = [
    {
        "apiGroups": [""],
        "resources": ["nodes", "nodes/metrics", "services", "endpoints", "pods"],
        "verbs": ["get", "list", "watch"],
    },
    {"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get"]},
    {
        "apiGroups": ["discovery.k8s.io"],
        "resources": ["endpointslices"],
        "verbs": ["get", "list", "watch"],
    },
    {
        "apiGroups": ["networking.k8s.io"],
        "resources": ["ingresses"],
        "verbs": ["get", "list", "watch"],
    },
    {"nonResourceURLs": ["/metrics"], "verbs": ["get"]},
]


class ServiceAccount(k8s.Base):
    def new(self) -> None:
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "ServiceAccount"
        super().new()

    def body(self) -> None:
        super().body()
        self.add_namespace(self.kwargs.namespace)
        self.add_labels(self.kwargs.labels)


class ClusterRole(k8s.Base):
    def new(self) -> None:
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "ClusterRole"
        super().new()

    def body(self) -> None:
        super().body()
        self.add_labels(self.kwargs.labels)
        self.root.rules = RBAC_RULES


class ClusterRoleBinding(k8s.Base):
    def new(self) -> None:
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "ClusterRoleBinding"
        super().new()

    def body(self) -> None:
        super().body()
        self.add_labels(self.kwargs.labels)
        self.root.roleRef = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": self.kwargs.name,
        }
        self.root.subjects = [
            {
                "kind": "ServiceAccount",
                "name": self.kwargs.service_account,
                "namespace": self.kwargs.namespace,
            }
        ]


def _add_rbac(obj: BaseObj, resource: PrometheusOperatorBase) -> None:
    """Emit SA, ClusterRole and ClusterRoleBinding for *resource*; wire its SA."""
    spec = resource.root.spec
    namespace = resource.root.metadata.namespace
    service_account = spec.get("serviceAccountName") or resource.kwargs.name
    spec.serviceAccountName = service_account
    labels = _convert_to_dict(resource.kwargs.config.get("labels", {}))
    # ClusterRole names are cluster-wide: prefix the namespace so same-named
    # CRs in different namespaces get their own role and binding.
    cluster_name = f"{namespace}-{resource.kwargs.name}"
    if f"{cluster_name}-clusterrole" in obj.root:
        raise ValueError(
            f"prometheus-operator {resource.KIND} '{resource.kwargs.name}': "
            f"rbac ClusterRole '{cluster_name}' already generated by another resource"
        )
    obj.root[f"{namespace}/{service_account}-sa"] = ServiceAccount(
        name=service_account, namespace=namespace, labels=labels
    )
    obj.root[f"{cluster_name}-clusterrole"] = ClusterRole(
        name=cluster_name, labels=labels
    )
    obj.root[f"{cluster_name}-crb"] = ClusterRoleBinding(
        name=cluster_name,
        labels=labels,
        service_account=service_account,
        namespace=namespace,
    )


# =============================================================================
# main()
# =============================================================================

# inventory section -> (resource class, output suffix = CRD shortName)
SECTIONS: dict[str, tuple[type[PrometheusOperatorBase], str]] = {
    "prometheuses": (Prometheus, "prom"),
    "prometheus_agents": (PrometheusAgent, "promagent"),
    "alertmanagers": (Alertmanager, "am"),
    "alertmanager_configs": (AlertmanagerConfig, "amcfg"),
    "thanos_rulers": (ThanosRuler, "ruler"),
    "probes": (Probe, "prb"),
    "scrape_configs": (ScrapeConfig, "scfg"),
    "service_monitors": (ServiceMonitor, "smon"),
    "pod_monitors": (PodMonitor, "pmon"),
    "prometheus_rules": (PrometheusRule, "promrule"),
}

_RBAC_KINDS = (Prometheus, PrometheusAgent)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.prometheus_operator."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("prometheus_operator", {}) or {}
    )
    release_label = generator_config.get("release_label")
    counts = {}
    for section, (resource_class, suffix) in SECTIONS.items():
        entries = generator_config.get(section) or {}
        counts[section] = len(entries)
        for name, config in entries.items():
            config = config or {}
            resource = resource_class(
                name=name, config=config, release_label=release_label
            )
            namespace = resource.root.metadata.namespace
            obj.root[f"{namespace}/{name}-{suffix}"] = resource
            if resource_class in _RBAC_KINDS and config.get("rbac"):
                _add_rbac(obj, resource)
    logger.info("prometheus-operator generated resources: %s", counts)
    return obj


__all__ = [
    "Alertmanager",
    "AlertmanagerConfig",
    "ClusterRole",
    "ClusterRoleBinding",
    "PodMonitor",
    "Probe",
    "Prometheus",
    "PrometheusAgent",
    "PrometheusOperatorBase",
    "PrometheusRule",
    "RBAC_RULES",
    "SECTIONS",
    "ScrapeConfig",
    "ServiceAccount",
    "ServiceMonitor",
    "ThanosRuler",
    "inv",
    "k8s",
    "main",
]
