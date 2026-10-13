"""CloudNativePG generator for Kapitan.

Renders postgresql.cnpg.io/v1 Cluster, Database, Pooler, ScheduledBackup and
Backup and Barman Cloud Plugin ObjectStores (barmancloud.cnpg.io/v1); see
README.md for the inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, CompileError, inventory

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

CNPG = "postgresql.cnpg.io/v1"
BARMAN = "barmancloud.cnpg.io/v1"
BARMAN_PLUGIN = "barman-cloud.cloudnative-pg.io"

try:
    from omegaconf import DictConfig, ListConfig, OmegaConf

    _OMEGACONF_TYPES: tuple[type, ...] = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _plain(obj: Any) -> Any:
    """Recursively convert BaseObj / OmegaConf objects to plain Python values."""
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        return _plain(OmegaConf.to_container(obj, resolve=True))
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


def _warn(flat_key: str, spec_key: str, name: str) -> None:
    logger.warning(
        "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
        flat_key,
        spec_key,
        name,
    )


def _spec(name: str, config: dict, defaults: dict, flat_keys: dict[str, str]) -> dict:
    """Generator defaults < ``spec`` passthrough < flat keys."""
    passthrough = config.get("spec") or {}
    spec = {**defaults, **passthrough}
    for flat_key, crd_key in flat_keys.items():
        if config.get(flat_key) is None:
            continue
        if crd_key in passthrough:
            _warn(flat_key, crd_key, name)
        spec[crd_key] = config[flat_key]
    if isinstance(spec.get("cluster"), str):
        spec["cluster"] = {"name": spec["cluster"]}
    return spec


def _resource(api_version: str, kind: str, name: str, namespace: str, config: dict, spec: dict) -> dict:
    metadata: dict[str, Any] = {"name": name, "namespace": namespace}
    for key in ("labels", "annotations"):
        if config.get(key):
            metadata[key] = config[key]
    return {"apiVersion": api_version, "kind": kind, "metadata": metadata, "spec": spec}


def _size(value: Any) -> Any:
    """``storage: 20Gi`` -> ``storage: {size: 20Gi}``."""
    return {"size": value} if isinstance(value, str) else value


CLUSTER_KEYS = {
    "instances": "instances",
    "image_name": "imageName",
    "image_catalog_ref": "imageCatalogRef",
    "storage": "storage",
    "wal_storage": "walStorage",
    "postgresql": "postgresql",
    "bootstrap": "bootstrap",
    "resources": "resources",
    "affinity": "affinity",
    "monitoring": "monitoring",
    "managed": "managed",
    "plugins": "plugins",
    "replica": "replica",
    "external_clusters": "externalClusters",
    "certificates": "certificates",
}


def cluster(name: str, namespace: str, config: dict) -> dict:
    # instances: 3 as in docs/src/samples/cluster-example.yaml; the CRD default is 1.
    spec = _spec(name, config, {"instances": 3}, CLUSTER_KEYS)
    for key in ("storage", "walStorage"):
        if key in spec:
            spec[key] = _size(spec[key])
    storage = spec.get("storage") or {}
    template_size = (((storage.get("pvcTemplate") or {}).get("resources") or {}).get("requests") or {}).get("storage")
    if not storage.get("size") and not template_size:
        # The operator's admission rejects a Cluster without a storage size.
        raise CompileError(f"cloudnative-pg: cluster '{name}' needs storage (for example storage: 10Gi)")

    in_tree = (spec.get("backup") or {}).get("barmanObjectStore") is not None
    backup = config.get("backup")
    if backup is not None:
        if not isinstance(backup, dict) or not backup.get("object_store"):
            raise CompileError(f"cloudnative-pg: cluster '{name}' backup needs object_store")
        if in_tree:
            # The webhook rejects a WAL archiver plugin next to barmanObjectStore.
            raise CompileError(f"cloudnative-pg: cluster '{name}' sets backup and spec.backup.barmanObjectStore; use one")
        parameters = {"barmanObjectName": backup["object_store"]}
        if backup.get("server_name"):
            parameters["serverName"] = backup["server_name"]
        if any(p.get("name") == BARMAN_PLUGIN for p in (config.get("spec") or {}).get("plugins") or []):
            _warn("backup", f"plugins[{BARMAN_PLUGIN}]", name)
        plugins = [p for p in spec.get("plugins") or [] if p.get("name") != BARMAN_PLUGIN]
        spec["plugins"] = [*plugins, {"name": BARMAN_PLUGIN, "isWALArchiver": True, "parameters": parameters}]
    deprecated = [
        field
        for field, used in (
            ("backup.barmanObjectStore (removed in CloudNativePG 1.31.0)", in_tree),
            ("monitoring.enablePodMonitor", (spec.get("monitoring") or {}).get("enablePodMonitor")),
        )
        if used
    ]
    if deprecated:
        logger.warning("Cluster '%s' uses deprecated %s; see README", name, " and ".join(deprecated))
    return _resource(CNPG, "Cluster", name, namespace, config, spec)


def _barman_store(cluster_spec: dict) -> Any:
    """barmanObjectName of the Cluster's Barman Cloud Plugin entry, None without one."""
    for plugin in cluster_spec.get("plugins") or []:
        if plugin.get("name") == BARMAN_PLUGIN and plugin.get("enabled", True):
            return (plugin.get("parameters") or {}).get("barmanObjectName") or ""
    return None


DATABASE_KEYS = {
    "cluster": "cluster",
    "database_name": "name",
    "owner": "owner",
    "ensure": "ensure",
    "database_reclaim_policy": "databaseReclaimPolicy",
    "encoding": "encoding",
    "locale": "locale",
    "template": "template",
    "extensions": "extensions",
    "schemas": "schemas",
}


def database(name: str, namespace: str, config: dict) -> dict:
    spec = _spec(name, config, {"name": name}, DATABASE_KEYS)
    return _resource(CNPG, "Database", name, namespace, config, spec)


POOLER_KEYS = {
    "cluster": "cluster",
    "instances": "instances",
    "type": "type",
    "pgbouncer": "pgbouncer",
    "template": "template",
    "service_template": "serviceTemplate",
}


def pooler(name: str, namespace: str, config: dict) -> dict:
    # pgbouncer is required by the CRD; its poolMode defaults to session there.
    spec = _spec(name, config, {"pgbouncer": {}}, POOLER_KEYS)
    if config.get("pool_mode") is not None:
        if "poolMode" in ((config.get("spec") or {}).get("pgbouncer") or {}):
            _warn("pool_mode", "pgbouncer.poolMode", name)
        spec["pgbouncer"] = {**(spec["pgbouncer"] or {}), "poolMode": config["pool_mode"]}
    cluster_name = (spec.get("cluster") or {}).get("name")
    if cluster_name and name in (cluster_name, *(f"{cluster_name}-{s}" for s in ("rw", "ro", "r"))):
        # The Pooler's Service is named after it and would patch the Cluster's own Service.
        raise CompileError(
            f"cloudnative-pg: pooler '{name}' collides with a Service of cluster '{cluster_name}'; "
            f"name it for example {cluster_name}-pooler-{spec.get('type', 'rw')}"
        )
    return _resource(CNPG, "Pooler", name, namespace, config, spec)


BACKUP_KEYS = {
    "cluster": "cluster",
    "method": "method",
    "plugin_configuration": "pluginConfiguration",
    "target": "target",
    "online": "online",
}
SCHEDULED_BACKUP_KEYS = {
    **BACKUP_KEYS,
    "schedule": "schedule",
    "immediate": "immediate",
    "suspend": "suspend",
    "backup_owner_reference": "backupOwnerReference",
}


def _backup_spec(name: str, config: dict, defaults: dict, flat_keys: dict) -> dict:
    # method: plugin, since the CRD default barmanObjectStore is deprecated since 1.26.
    spec = _spec(name, config, {"method": "plugin", **defaults}, flat_keys)
    if spec["method"] == "plugin":
        spec.setdefault("pluginConfiguration", {"name": BARMAN_PLUGIN})
    return spec


def backup(name: str, namespace: str, config: dict) -> dict:
    return _resource(CNPG, "Backup", name, namespace, config, _backup_spec(name, config, {}, BACKUP_KEYS))


def scheduled_backup(name: str, namespace: str, config: dict) -> dict:
    spec = _backup_spec(name, config, {"backupOwnerReference": "self"}, SCHEDULED_BACKUP_KEYS)
    schedule = spec.get("schedule")
    if isinstance(schedule, str) and len(schedule.split()) == 5:
        # CloudNativePG cron has a leading seconds field.
        spec["schedule"] = "0 " + schedule
    return _resource(CNPG, "ScheduledBackup", name, namespace, config, spec)


OBJECT_STORE_KEYS = {
    "configuration": "configuration",
    "retention_policy": "retentionPolicy",
    "instance_sidecar_configuration": "instanceSidecarConfiguration",
}


def object_store(name: str, namespace: str, config: dict) -> dict:
    spec = _spec(name, config, {}, OBJECT_STORE_KEYS)
    if (spec.get("configuration") or {}).get("serverName"):
        raise CompileError(
            f"cloudnative-pg: object store '{name}' must leave configuration.serverName empty; "
            "set backup.server_name on the cluster instead"
        )
    return _resource(BARMAN, "ObjectStore", name, namespace, config, spec)


SECTIONS = (
    ("clusters", "cluster", cluster),
    ("databases", "database", database),
    ("poolers", "pooler", pooler),
    ("scheduled_backups", "scheduledbackup", scheduled_backup),
    ("backups", "backup", backup),
    ("object_stores", "objectstore", object_store),
)


def _check_references(resources: dict) -> None:
    """Cross-resource rules the operator and the plugin enforce at runtime."""
    clusters = {(r["metadata"]["namespace"], r["metadata"]["name"]): r["spec"] for r in resources["clusters"]}
    stores = {}
    for r in resources["object_stores"]:
        stores.setdefault(r["metadata"]["name"], []).append(r["metadata"]["namespace"])
    for (namespace, name), spec in clusters.items():
        store = _barman_store(spec)
        if store in stores and namespace not in stores[store]:
            # The plugin reads the ObjectStore from the Cluster's namespace.
            raise CompileError(
                f"cloudnative-pg: cluster '{name}' in namespace '{namespace}' uses object store '{store}' "
                f"defined in namespace {', '.join(stores[store])}"
            )
    for kind in ("backups", "scheduled_backups"):
        for r in resources[kind]:
            spec, namespace = r["spec"], r["metadata"]["namespace"]
            target = clusters.get((namespace, (spec.get("cluster") or {}).get("name")))
            uses_barman = spec.get("method") == "plugin" and (spec.get("pluginConfiguration") or {}).get("name") == BARMAN_PLUGIN
            if target is not None and uses_barman and _barman_store(target) is None:
                raise CompileError(
                    f"cloudnative-pg: {r['kind']} '{r['metadata']['name']}' uses the Barman Cloud Plugin, "
                    f"but cluster '{spec['cluster']['name']}' has no backup.object_store"
                )


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.cloudnative-pg."""
    params = inventory().parameters
    config = _plain(params.get("generators", {}).get("cloudnative-pg", {})) or {}
    default_namespace = config.get("namespace") or params.get("namespace") or "default"
    out = BaseObj()
    resources: dict[str, list] = {}
    for section, suffix, build in SECTIONS:
        entries = config.get(section) or {}
        resources[section] = []
        for name in sorted(entries):
            entry = entries[name] or {}
            namespace = entry.get("namespace") or default_namespace
            resource = build(name, namespace, entry)
            resources[section].append(resource)
            out.root[f"{namespace}/{name}-{suffix}"] = resource
    _check_references(resources)
    return out
