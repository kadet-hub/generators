"""Loki Operator resource generators for Kapitan.

Renders loki.grafana.com/v1 LokiStack, AlertingRule, RecordingRule and
RulerConfig; see README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.0"

API_VERSION = "loki.grafana.com/v1"
STACK_LABEL = "loki.grafana.com/lokistack"


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.loki.namespace -> parameters.namespace -> "default"."""
    generator_config = inv.parameters.get("generators", {}).get("loki", {}) or {}
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


class LokiResource(k8s.Base):
    """One Loki Operator custom resource; subclasses set kind and _FLAT_KEY_MAP.

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


class LokiStack(LokiResource):
    KIND = "LokiStack"
    _FLAT_KEY_MAP = {
        "size": "size",
        "storage": "storage",
        "storage_class_name": "storageClassName",
        "hash_ring": "hashRing",
        "limits": "limits",
        "management_state": "managementState",
        "network_policies": "networkPolicies",
        "proxy": "proxy",
        "replication": "replication",
        "rules": "rules",
        "template": "template",
        "tenants": "tenants",
    }

    def body(self) -> None:
        super().body()
        spec = self.root.spec
        if isinstance(spec.get("storage"), str):
            secret_type = spec.storage
            spec.storage = {
                "secret": {
                    "name": f"{self.root.metadata.name}-{secret_type}",
                    "type": secret_type,
                }
            }
        storage = spec.get("storage")
        if storage is not None and "schemas" not in storage:
            storage.schemas = [{"version": "v13", "effectiveDate": "2023-10-15"}]
        tenants = spec.get("tenants")
        if tenants and not tenants.get("mode"):
            mode = _tenants_mode(tenants)
            if mode:
                tenants.mode = mode
        rules = spec.get("rules")
        if rules and rules.get("enabled") and "selector" not in rules:
            rules.selector = {"matchLabels": {STACK_LABEL: self.root.metadata.name}}
            other_namespaces = [
                ns
                for ns in self.kwargs.get("rule_namespaces") or []
                if ns != self.root.metadata.namespace
            ]
            if other_namespaces and "namespaceSelector" not in rules:
                rules.namespaceSelector = {
                    "matchExpressions": [
                        {
                            "key": "kubernetes.io/metadata.name",
                            "operator": "In",
                            "values": other_namespaces,
                        }
                    ]
                }


def _tenants_mode(tenants: dict) -> str | None:
    """The tenancy mode the operator's mode validation accepts for this block."""
    authorization = tenants.get("authorization") or {}
    if "passthrough" in tenants:
        return "passthrough"
    if "opa" in authorization:
        return "dynamic"
    if "roles" in authorization or "roleBindings" in authorization:
        return "static"
    return None


class LokiRule(LokiResource):
    _FLAT_KEY_MAP = {"tenant_id": "tenantID", "groups": "groups"}

    def body(self) -> None:
        super().body()
        if self.kwargs.get("loki_stack"):
            self.root.metadata.labels.setdefault(STACK_LABEL, self.kwargs.loki_stack)


class AlertingRule(LokiRule):
    KIND = "AlertingRule"


class RecordingRule(LokiRule):
    KIND = "RecordingRule"


class RulerConfig(LokiResource):
    KIND = "RulerConfig"
    _FLAT_KEY_MAP = {
        "alertmanager": "alertmanager",
        "evaluation_interval": "evaluationInterval",
        "overrides": "overrides",
        "poll_interval": "pollInterval",
        "remote_write": "remoteWrite",
    }


SECTIONS = (
    ("loki_stacks", LokiStack, "lokistack"),
    ("alerting_rules", AlertingRule, "alertingrule"),
    ("recording_rules", RecordingRule, "recordingrule"),
    ("ruler_configs", RulerConfig, "rulerconfig"),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.loki."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("loki", {}) or {}
    )
    default_namespace = _default_namespace()
    stacks = generator_config.get("loki_stacks") or {}
    only_stack = next(iter(stacks)) if len(stacks) == 1 else None
    rule_namespaces: dict[str, set[str]] = {}
    for section in ("alerting_rules", "recording_rules"):
        for config in (generator_config.get(section) or {}).values():
            config = config or {}
            stack = config.get("loki_stack") or only_stack
            if stack:
                rule_namespaces.setdefault(stack, set()).add(
                    config.get("namespace") or default_namespace
                )
    for section, resource_class, suffix in SECTIONS:
        for name, config in (generator_config.get(section) or {}).items():
            config = config or {}
            namespace = config.get("namespace") or default_namespace
            obj.root[f"{namespace}/{name}-{suffix}"] = resource_class(
                name=name,
                config=config,
                loki_stack=config.get("loki_stack") or only_stack,
                rule_namespaces=sorted(rule_namespaces.get(name, ())),
            )
    return obj


__all__ = [
    "API_VERSION",
    "AlertingRule",
    "LokiResource",
    "LokiRule",
    "LokiStack",
    "RecordingRule",
    "RulerConfig",
    "inv",
    "k8s",
    "main",
]
