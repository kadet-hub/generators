"""Grafana Operator v5 generators for Kapitan.

Renders grafana.integreatly.org/v1beta1 Grafana, GrafanaDashboard,
GrafanaDatasource, GrafanaFolder, GrafanaAlertRuleGroup, GrafanaContactPoint,
GrafanaNotificationPolicy, GrafanaLibraryPanel, GrafanaMuteTiming,
GrafanaNotificationPolicyRoute, GrafanaNotificationTemplate and
GrafanaServiceAccount; see README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


__version__ = "1.0.0"

inv = inventory()
logger = logging.getLogger(__name__)

API_VERSION = "grafana.integreatly.org/v1beta1"
GRAFANA_HTTP_PORT = 3000
OVERRIDE_WARNING = "Flat key '%s' overrides spec passthrough '%s' for resource '%s'"


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert OmegaConf / BaseObj objects to plain Python dicts."""
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


def _generator_config() -> dict:
    return _convert_to_dict(inv.parameters.get("generators", {}).get("grafana", {})) or {}


def _namespace(config: dict) -> Any:
    """Entry namespace -> generators.grafana.namespace -> parameters.namespace -> default."""
    return config.get(
        "namespace",
        _generator_config().get("namespace", inv.parameters.get("namespace", "default")),
    )


def _selector(value: Any) -> Any:
    """A plain label map becomes ``{matchLabels: ...}``; a LabelSelector passes through."""
    if (
        isinstance(value, dict)
        and value
        and not {"matchLabels", "matchExpressions"} & value.keys()
    ):
        return {"matchLabels": value}
    return value


def _named_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) and "name" in item for item in value)
    )


def _merge(base: Any, override: Any) -> Any:
    """Deep merge; lists of named items (containers, volumes) merge by name."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _merge(base[key], value) if key in base else value
        return merged
    if _named_list(base) and _named_list(override):
        merged = [dict(item) for item in base]
        index = {item["name"]: i for i, item in enumerate(merged)}
        for item in override:
            if item["name"] in index:
                merged[index[item["name"]]] = _merge(merged[index[item["name"]]], item)
            else:
                merged.append(item)
        return merged
    return override


def _overlap(override: Any, base: Any, path: str = "") -> str | None:
    """Path of the first value in *base* that merging *override* replaces."""
    if isinstance(override, dict) and isinstance(base, dict):
        for key, value in override.items():
            if key in base:
                found = _overlap(value, base[key], f"{path}.{key}" if path else key)
                if found:
                    return found
        return None
    if _named_list(override) and _named_list(base):
        by_name = {item["name"]: item for item in base}
        for item in override:
            if item["name"] in by_name:
                rest = {k: v for k, v in item.items() if k != "name"}
                found = _overlap(rest, by_name[item["name"]], f"{path}[{item['name']}]")
                if found:
                    return found
        return None
    return path


class GrafanaBase(k8s.Base):
    """One Grafana Operator content resource; subclasses set the class attributes.

    Required kwargs: name, config (inventory entry).
    """

    KIND = ""
    # The kind has spec.instanceSelector, which its CRD requires.
    SELECTOR = True
    # Flat inventory key -> spec field; each replaces the spec field.
    FLAT_KEYS: dict[str, str] = {}
    # spec fields the generator requires, besides instanceSelector.
    REQUIRED: tuple[str, ...] = ()
    # spec field that defaults to the entry key.
    NAME_FIELD = ""

    _SYNC_KEYS = {
        "resync_period": "resyncPeriod",
        "suspend": "suspend",
        "allow_cross_namespace_import": "allowCrossNamespaceImport",
    }

    def new(self) -> None:
        self.need("name")
        self.need("config")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def _flat_value(self, flat_key: str, value: Any) -> Any:
        return _selector(value) if flat_key == "instance_selector" else value

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)
        self.add_namespace(_namespace(config))
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        spec: dict = {}
        if self.NAME_FIELD:
            spec[self.NAME_FIELD] = self.kwargs.name
        generator_selector = _generator_config().get("instance_selector")
        if self.SELECTOR and generator_selector:
            spec["instanceSelector"] = _selector(generator_selector)

        passthrough = config.get("spec") or {}
        spec.update(passthrough)

        flat_keys = dict(self.FLAT_KEYS)
        if self.SELECTOR:
            flat_keys["instance_selector"] = "instanceSelector"
        for flat_key, spec_key in flat_keys.items():
            value = config.get(flat_key)
            if value is None:
                continue
            if passthrough.get(spec_key) is not None:
                logger.warning(OVERRIDE_WARNING, flat_key, spec_key, self.kwargs.name)
            spec[spec_key] = self._flat_value(flat_key, value)

        required = self.REQUIRED + (("instanceSelector",) if self.SELECTOR else ())
        for spec_key in required:
            if not spec.get(spec_key):
                flat_key = next((f for f, s in flat_keys.items() if s == spec_key), spec_key)
                raise ValueError(
                    f"grafana {self.KIND} '{self.kwargs.name}': '{flat_key}' is required"
                )

        self.root.spec = spec


_CONTENT_KEYS = {
    "json": "json",
    "gzip_json": "gzipJson",
    "url": "url",
    "configmap_ref": "configMapRef",
    "grafana_com": "grafanaCom",
    "jsonnet": "jsonnet",
    "jsonnet_lib": "jsonnetLib",
    "folder_ref": "folderRef",
    "folder_uid": "folderUID",
    "uid": "uid",
    "datasources": "datasources",
    "plugins": "plugins",
    "envs": "envs",
    "env_from": "envFrom",
    "content_cache_duration": "contentCacheDuration",
    "url_authorization": "urlAuthorization",
}


class GrafanaDashboard(GrafanaBase):
    KIND = "GrafanaDashboard"
    FLAT_KEYS = {**GrafanaBase._SYNC_KEYS, **_CONTENT_KEYS, "folder": "folder"}


class GrafanaLibraryPanel(GrafanaBase):
    KIND = "GrafanaLibraryPanel"
    FLAT_KEYS = {**GrafanaBase._SYNC_KEYS, **_CONTENT_KEYS}


class GrafanaDatasource(GrafanaBase):
    KIND = "GrafanaDatasource"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "datasource": "datasource",
        "values_from": "valuesFrom",
        "plugins": "plugins",
        "uid": "uid",
    }
    REQUIRED = ("datasource",)


class GrafanaFolder(GrafanaBase):
    KIND = "GrafanaFolder"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "title": "title",
        "parent_folder_ref": "parentFolderRef",
        "parent_folder_uid": "parentFolderUID",
        "permissions": "permissions",
        "uid": "uid",
    }
    NAME_FIELD = "title"


class GrafanaAlertRuleGroup(GrafanaBase):
    KIND = "GrafanaAlertRuleGroup"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "interval": "interval",
        "rules": "rules",
        "group_name": "name",
        "folder_ref": "folderRef",
        "folder_uid": "folderUID",
        "editable": "editable",
    }
    REQUIRED = ("interval", "rules")


class GrafanaContactPoint(GrafanaBase):
    """The deprecated single-receiver flat keys become one ``receivers`` entry;
    explicit ``receivers`` wins."""

    KIND = "GrafanaContactPoint"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "receivers": "receivers",
        "point_name": "name",
        "editable": "editable",
    }
    RECEIVER_KEYS = {
        "type": "type",
        "settings": "settings",
        "uid": "uid",
        "values_from": "valuesFrom",
        "disable_resolve_message": "disableResolveMessage",
    }

    def body(self) -> None:
        config = _convert_to_dict(self.kwargs.config)
        legacy = [k for k in self.RECEIVER_KEYS if config.get(k) is not None]
        receiver = {self.RECEIVER_KEYS[k]: config.pop(k) for k in legacy}
        if receiver and config.get("receivers") is not None:
            logger.warning(
                "Flat key 'receivers' overrides %s for resource '%s'",
                ", ".join(f"'{k}'" for k in legacy),
                self.kwargs.name,
            )
        elif receiver:
            config["receivers"] = [receiver]
        self.kwargs.config = config
        super().body()


class GrafanaNotificationPolicy(GrafanaBase):
    KIND = "GrafanaNotificationPolicy"
    FLAT_KEYS = {**GrafanaBase._SYNC_KEYS, "route": "route", "editable": "editable"}
    REQUIRED = ("route",)


class GrafanaMuteTiming(GrafanaBase):
    KIND = "GrafanaMuteTiming"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "name": "name",
        "time_intervals": "time_intervals",
        "editable": "editable",
    }
    NAME_FIELD = "name"


class GrafanaNotificationTemplate(GrafanaBase):
    KIND = "GrafanaNotificationTemplate"
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "name": "name",
        "template": "template",
        "editable": "editable",
    }
    NAME_FIELD = "name"


class GrafanaNotificationPolicyRoute(GrafanaBase):
    """Matcher ``type`` (= != =~ !~, or equal, not_equal, regex, not_regex)
    becomes ``isRegex``/``isEqual``."""

    KIND = "GrafanaNotificationPolicyRoute"
    SELECTOR = False
    FLAT_KEYS = {
        "route_selector": "routeSelector",
        "receiver": "receiver",
        "matchers": "matchers",
        "object_matchers": "object_matchers",
        "match_re": "match_re",
        "group_by": "group_by",
        "group_wait": "group_wait",
        "group_interval": "group_interval",
        "repeat_interval": "repeat_interval",
        "continue": "continue",
        "mute_time_intervals": "mute_time_intervals",
        "active_time_intervals": "active_time_intervals",
        "routes": "routes",
        "provenance": "provenance",
    }

    MATCHER_TYPE_MAP = {
        "=": {"isRegex": False, "isEqual": True},
        "equal": {"isRegex": False, "isEqual": True},
        "!=": {"isRegex": False, "isEqual": False},
        "not_equal": {"isRegex": False, "isEqual": False},
        "=~": {"isRegex": True, "isEqual": True},
        "regex": {"isRegex": True, "isEqual": True},
        "!~": {"isRegex": True, "isEqual": False},
        "not_regex": {"isRegex": True, "isEqual": False},
    }

    def _convert_matcher(self, matcher: dict) -> dict:
        result = {"value": matcher.get("value", "")}
        if "name" in matcher:
            result["name"] = matcher["name"]
        type_mapping = self.MATCHER_TYPE_MAP.get(matcher.get("type", "="))
        if type_mapping:
            result.update(type_mapping)
        else:
            result["isRegex"] = matcher.get("isRegex", False)
            if "isEqual" in matcher:
                result["isEqual"] = matcher["isEqual"]
        return result

    def _flat_value(self, flat_key: str, value: Any) -> Any:
        if flat_key == "matchers":
            return [self._convert_matcher(m) for m in value]
        return value


VALID_SERVICE_ACCOUNT_ROLES = frozenset({"Admin", "Editor", "Viewer"})


class GrafanaServiceAccount(GrafanaBase):
    KIND = "GrafanaServiceAccount"
    SELECTOR = False
    FLAT_KEYS = {
        **GrafanaBase._SYNC_KEYS,
        "name": "name",
        "instance_name": "instanceName",
        "role": "role",
        "tokens": "tokens",
        "is_disabled": "isDisabled",
    }

    def body(self) -> None:
        super().body()
        role = self.root.spec.get("role")
        if role and role not in VALID_SERVICE_ACCOUNT_ROLES:
            raise ValueError(
                f"Invalid role '{role}'. "
                f"Must be one of: {', '.join(sorted(VALID_SERVICE_ACCOUNT_ROLES))}"
            )


class Grafana(k8s.Base):
    """Grafana instance. Precedence: defaults < spec < flat keys
    (image, persistence, ingress, config), merged deeply."""

    def new(self):
        self.need("name")
        self.need("grafana_instance")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = "Grafana"
        super().new()

    def _flat_trees(self, instance: dict, spec: dict) -> list[tuple[str, dict]]:
        name = self.name
        trees = []

        image = instance.get("image")
        if image:
            trees.append(("image", _containers([{"name": "grafana", "image": image}])))

        config = instance.get("config")
        if config:
            trees.append(("config", {"config": config}))

        persistence = instance.get("persistence", {})
        if persistence.get("enabled"):
            # The operator mounts the volume grafana-data at /var/lib/grafana and
            # names the PVC it creates <name>-pvc; RWO needs Recreate.
            claim_spec = {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": persistence.get("size", "1Gi")}},
            }
            if persistence.get("storageclass"):
                claim_spec["storageClassName"] = persistence["storageclass"]
            trees.append(
                (
                    "persistence",
                    {
                        "persistentVolumeClaim": {"spec": claim_spec},
                        "deployment": {
                            "spec": {
                                "strategy": {"type": "Recreate"},
                                "template": {
                                    "spec": {
                                        "volumes": [
                                            {
                                                "name": "grafana-data",
                                                "persistentVolumeClaim": {
                                                    "claimName": f"{name}-pvc"
                                                },
                                            }
                                        ],
                                    }
                                },
                            }
                        },
                    },
                )
            )

        ingress = instance.get("ingress", {})
        if ingress.get("enabled"):
            hostname = ingress.get("hostname")
            if not hostname:
                raise ValueError(
                    f"grafana Grafana '{name}': 'ingress.hostname' is required"
                )
            merged_config = _merge(spec.get("config", {}), config or {})
            try:
                port = int(merged_config.get("server", {}).get("http_port"))
            except (TypeError, ValueError):
                port = GRAFANA_HTTP_PORT
            trees.append(
                (
                    "ingress",
                    {
                        "ingress": {
                            "metadata": {
                                "annotations": ingress.get("annotations", {}),
                                "labels": ingress.get("labels", {}),
                            },
                            "spec": {
                                "ingressClassName": ingress.get("ingress_class", "nginx"),
                                "tls": [
                                    {
                                        "hosts": [hostname],
                                        "secretName": f"{name}-grafana-tls-secret",
                                    }
                                ],
                                "rules": [
                                    {
                                        "host": hostname,
                                        "http": {
                                            "paths": [
                                                {
                                                    "path": "/",
                                                    "pathType": "Prefix",
                                                    "backend": {
                                                        "service": {
                                                            "name": f"{name}-service",
                                                            "port": {"number": port},
                                                        }
                                                    },
                                                }
                                            ]
                                        },
                                    }
                                ],
                            },
                        }
                    },
                )
            )
        return trees

    def body(self):
        super().body()
        instance = _convert_to_dict(self.kwargs.grafana_instance)
        self.add_namespace(_namespace(instance))
        self.add_annotations(instance.get("annotations", {}))
        self.add_labels(instance.get("labels", {}))

        defaults: dict = {}
        if instance.get("persistence", {}).get("enabled"):
            # The operator runs Grafana as group 10001; fsGroup makes the claim writable.
            defaults = {
                "deployment": {
                    "spec": {"template": {"spec": {"securityContext": {"fsGroup": 10001}}}}
                }
            }
        passthrough = instance.get("spec") or {}
        spec = _merge(defaults, passthrough)
        for flat_key, tree in self._flat_trees(instance, passthrough):
            path = _overlap(tree, passthrough)
            if path:
                logger.warning(OVERRIDE_WARNING, flat_key, path, self.name)
            spec = _merge(spec, tree)
        self.root.spec = spec


def _containers(containers: list) -> dict:
    return {"deployment": {"spec": {"template": {"spec": {"containers": containers}}}}}


# =============================================================================
# Legacy Generator Functions
# =============================================================================


def generate_grafana_instance(input_params):
    obj = BaseObj()
    for name, instance_config in _generator_config().get("instances", {}).items():
        namespace = _namespace(instance_config)
        obj.root[f"{namespace}/{name}-grafana-instance"] = Grafana(
            name=name, grafana_instance=instance_config
        )
    return obj


def generate_manifests(input_params):
    all_manifests = BaseObj()
    all_manifests.root.update(generate_grafana_instance(input_params).root)
    return all_manifests


# =============================================================================
# Main Entry Point
# =============================================================================

_SECTIONS = (
    ("dashboards", GrafanaDashboard, "dashboard"),
    ("datasources", GrafanaDatasource, "datasource"),
    ("folders", GrafanaFolder, "folder"),
    ("alert_rule_groups", GrafanaAlertRuleGroup, "alertrulegroup"),
    ("contact_points", GrafanaContactPoint, "contactpoint"),
    ("notification_policies", GrafanaNotificationPolicy, "notificationpolicy"),
    ("library_panels", GrafanaLibraryPanel, "librarypanel"),
    ("mute_timings", GrafanaMuteTiming, "mutetiming"),
    ("notification_policy_routes", GrafanaNotificationPolicyRoute, "notificationpolicyroute"),
    ("notification_templates", GrafanaNotificationTemplate, "notificationtemplate"),
    ("service_accounts", GrafanaServiceAccount, "serviceaccount"),
)


def main(input_params: dict | None = None) -> BaseObj:
    """Generate Grafana Operator resources from parameters.generators.grafana.

    ``input_params: {function: generate_manifests}`` renders only the instances
    (legacy mode).
    """
    function = input_params.get("function", None) if input_params else None
    if function == "generate_manifests":
        return generate_manifests(input_params)

    obj = BaseObj()
    config = _generator_config()
    if not config:
        return obj

    obj.root.update(generate_grafana_instance(input_params).root)
    for section, cls, suffix in _SECTIONS:
        for name, resource_config in config.get(section, {}).items():
            resource_config = resource_config or {}
            namespace = _namespace(resource_config)
            obj.root[f"{namespace}/{name}-{suffix}"] = cls(name=name, config=resource_config)
    return obj


__all__ = [
    # Classes
    "Grafana",
    "GrafanaBase",
    "GrafanaLibraryPanel",
    "GrafanaMuteTiming",
    "GrafanaNotificationPolicyRoute",
    "GrafanaNotificationTemplate",
    "GrafanaServiceAccount",
    # Legacy functions
    "generate_grafana_instance",
    "generate_manifests",
    # Utils
    "_convert_to_dict",
    # Entry point
    "main",
    # Imports
    "inv",
    "k8s",
]
