"""Kapitan kadet generator for Velero resources (velero.io/v1).

Reads parameters.generators.velero and renders Backup, Schedule, Restore,
BackupStorageLocation and VolumeSnapshotLocation; see README.md for the
inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.0"

API_VERSION = "velero.io/v1"

#: The Velero server only watches its install namespace, "velero" by default.
DEFAULT_NAMESPACE = "velero"

#: Backup spec flat keys; also applied inside a Schedule `template`.
BACKUP_FLAT_KEY_MAP = {
    "included_namespaces": "includedNamespaces",
    "excluded_namespaces": "excludedNamespaces",
    "included_resources": "includedResources",
    "excluded_resources": "excludedResources",
    "label_selector": "labelSelector",
    "storage_location": "storageLocation",
    "volume_snapshot_locations": "volumeSnapshotLocations",
    "ttl": "ttl",
    "snapshot_volumes": "snapshotVolumes",
    "default_volumes_to_fs_backup": "defaultVolumesToFsBackup",
    "snapshot_move_data": "snapshotMoveData",
    "include_cluster_resources": "includeClusterResources",
}


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _default_namespace() -> str:
    """generators.velero.namespace -> "velero"; parameters.namespace is not read."""
    generator_config = inv.parameters.get("generators", {}).get("velero", {}) or {}
    return generator_config.get("namespace") or DEFAULT_NAMESPACE


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


def _apply_flat_keys(
    target: Any, config: dict, mapping: dict[str, str], name: str
) -> None:
    """Merge ``config.spec`` into *target*, then apply the flat keys of *mapping*.

    Dotted CRD keys (``objectStorage.bucket``) address nested fields.
    """
    _merge_spec_passthrough(target, config)
    _warn_collisions(config, mapping, name)
    for flat_key, crd_key in mapping.items():
        *parents, leaf = crd_key.split(".")
        node = target
        for part in parents:
            node = node[part]
        _set_field(node, config, flat_key, target_key=leaf)


class VeleroBase(k8s.Base):
    """Shared metadata and spec handling; subclasses set KIND and _FLAT_KEY_MAP."""

    KIND = ""
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = API_VERSION
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        _apply_flat_keys(self.root.spec, config, self._FLAT_KEY_MAP, self.kwargs.name)

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


class Backup(VeleroBase):
    KIND = "Backup"
    _FLAT_KEY_MAP = BACKUP_FLAT_KEY_MAP


class Schedule(VeleroBase):
    """Schedule; ``template`` takes Backup flat keys and its own ``spec``."""

    KIND = "Schedule"
    _FLAT_KEY_MAP = {
        "schedule": "schedule",
        "paused": "paused",
        "skip_immediately": "skipImmediately",
        "use_owner_references_in_backup": "useOwnerReferencesInBackup",
    }

    def body(self) -> None:
        super().body()
        template = _convert_to_dict(self.kwargs.config.get("template"))
        if template is not None:
            _apply_flat_keys(
                self.root.spec["template"],
                template,
                BACKUP_FLAT_KEY_MAP,
                f"{self.kwargs.name}.template",
            )
        # The CRD requires spec.template; an empty one backs up all namespaces.
        if "template" not in self.root.spec:
            self.root.spec["template"] = {}


class Restore(VeleroBase):
    """Restore; exactly one of backupName / scheduleName (controller rule)."""

    KIND = "Restore"
    _FLAT_KEY_MAP = {
        "backup_name": "backupName",
        "schedule_name": "scheduleName",
        "included_namespaces": "includedNamespaces",
        "excluded_namespaces": "excludedNamespaces",
        "namespace_mapping": "namespaceMapping",
        "restore_pvs": "restorePVs",
        "existing_resource_policy": "existingResourcePolicy",
        "preserve_node_ports": "preserveNodePorts",
    }

    def body(self) -> None:
        super().body()
        spec = self.root.spec
        if bool(spec.get("backupName")) == bool(spec.get("scheduleName")):
            raise ValueError(
                f"velero Restore '{self.kwargs.name}': set exactly one of "
                "backup_name or schedule_name (backupName/scheduleName in spec)"
            )


class BackupStorageLocation(VeleroBase):
    KIND = "BackupStorageLocation"
    _FLAT_KEY_MAP = {
        "provider": "provider",
        "bucket": "objectStorage.bucket",
        "prefix": "objectStorage.prefix",
        "ca_cert": "objectStorage.caCert",
        "ca_cert_ref": "objectStorage.caCertRef",
        "config": "config",
        "credential": "credential",
        "default": "default",
        "access_mode": "accessMode",
        "backup_sync_period": "backupSyncPeriod",
        "validation_frequency": "validationFrequency",
    }

    def body(self) -> None:
        super().body()
        # A single location becomes the default; the server's fallback to a
        # location named "default" is deprecated.
        if self.kwargs.get("single") and "default" not in self.root.spec:
            self.root.spec.default = True


class VolumeSnapshotLocation(VeleroBase):
    KIND = "VolumeSnapshotLocation"
    _FLAT_KEY_MAP = {
        "provider": "provider",
        "config": "config",
        "credential": "credential",
    }


#: inventory section -> (resource class, output key suffix)
SECTIONS: dict[str, tuple[type[VeleroBase], str]] = {
    "backups": (Backup, "backup"),
    "schedules": (Schedule, "schedule"),
    "restores": (Restore, "restore"),
    "backup_storage_locations": (BackupStorageLocation, "bsl"),
    "volume_snapshot_locations": (VolumeSnapshotLocation, "vsl"),
}


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point."""
    obj = BaseObj()
    generator_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("velero", {}) or {}
    )
    default_namespace = _default_namespace()
    for section, (resource_class, suffix) in SECTIONS.items():
        entries = generator_config.get(section) or {}
        for name, config in entries.items():
            config = _convert_to_dict(config) or {}
            namespace = config.get("namespace") or default_namespace
            obj.root[f"{namespace}/{name}-{suffix}"] = resource_class(
                name=name, config=config, single=len(entries) == 1
            )
    return obj


__all__ = [
    "Backup",
    "BackupStorageLocation",
    "Restore",
    "Schedule",
    "VolumeSnapshotLocation",
    "main",
]
