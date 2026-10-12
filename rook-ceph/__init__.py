"""rook-ceph resource generators for Kapitan.

This module provides classes and functions for generating rook-ceph resources
using Kapitan's kadet input type. Supports CephCluster, CephBlockPool,
CephFilesystem, CephObjectStore, CephObjectStoreUser, CephNFS, CephRBDMirror,
and CephClient.

Design: common fields are modelled as flat inventory keys (reducing nesting
and repetition), while a ``spec`` passthrough dict preserves full access to
every CRD field.

Schema reference: ceph.rook.io/v1
See: https://rook.io/docs/rook/v1.21/CRDs/
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, CompileError, inventory

from . import k8s


logger = logging.getLogger(__name__)
inv = inventory()


try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()

__version__ = "1.0.0"


# =============================================================================
# Helpers
# =============================================================================


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


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set *target_key* on *target* from *config[source_key]* if present."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _convert_to_dict(value)


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge any user-supplied ``spec`` dict into *spec_target*.

    This is the escape hatch: anything not explicitly modelled can still be
    emitted by placing it under the ``spec`` key in inventory.
    """
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


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
# Base class
# =============================================================================


class RookCephBase(k8s.Base):
    """Base class for rook-ceph resources with common metadata helpers."""

    def _add_common_metadata(self, config: dict) -> None:
        """Populate metadata from *config*; main() resolves its namespace."""
        self.add_namespace(config["namespace"])
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))

    def _build_flat_spec(self, config: dict) -> Any:
        """Standard spec build: passthrough, collision warnings, flat keys.

        Flat keys with dotted CRD targets (e.g. ``storage.encryptedDevice``)
        are skipped here and handled by the resource class itself.
        """
        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for flat_key, crd_key in self._FLAT_KEY_MAP.items():
            if "." in crd_key:
                continue
            _set_field(spec, config, flat_key, target_key=crd_key)
        return spec


# =============================================================================
# CephCluster
# =============================================================================


class CephCluster(RookCephBase):
    """rook-ceph CephCluster resource.

    Explicitly modelled fields (flat inventory keys):
        ceph_version, data_dir_host_path, mon, mgr, osd, storage, network,
        resources, placement, dashboard, monitoring, external,
        remove_osds_if_out_and_safe_to_remove, cleanup_policy,
        disruption_management, security, health_check, log_collector,
        priority_class_names, upgrade_policy, csi,
        wait_timeout_for_healthy_osd_in_minutes

    Passthrough: anything under ``spec`` is merged into the generated spec.
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephCluster"
        super().new()

    _FLAT_KEY_MAP = {
        "ceph_version": "cephVersion",
        "data_dir_host_path": "dataDirHostPath",
        "mon": "mon",
        "mgr": "mgr",
        "osd": "osd",
        "storage": "storage",
        "network": "network",
        "resources": "resources",
        "placement": "placement",
        "dashboard": "dashboard",
        "monitoring": "monitoring",
        "external": "external",
        "remove_osds_if_out_and_safe_to_remove": "removeOSDsIfOutAndSafeToRemove",
        "cleanup_policy": "cleanupPolicy",
        "disruption_management": "disruptionManagement",
        "security": "security",
        "health_check": "healthCheck",
        "log_collector": "logCollector",
        "priority_class_names": "priorityClassNames",
        "upgrade_policy": "upgradePolicy",
        "csi": "csi",
        "wait_timeout_for_healthy_osd_in_minutes": "waitTimeoutForHealthyOSDInMinutes",
        "encrypted_device": "storage.config.encryptedDevice",
    }

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        spec = self._build_flat_spec(config)

        # -- Encryption helpers (nested under storage.config) -------------
        # Rook reads OSD settings from spec.storage.config and expects the
        # string "true"/"false" (dmcrypt); a boolean at
        # spec.storage.encryptedDevice is pruned by the CRD.
        encrypted_device = config.get("encrypted_device")
        if encrypted_device is not None:
            if isinstance(encrypted_device, bool):
                encrypted_device = "true" if encrypted_device else "false"
            spec.setdefault("storage", {}).setdefault("config", {})[
                "encryptedDevice"
            ] = str(encrypted_device)

        # Default from deploy/examples/cluster.yaml at v1.21.0: without
        # dataDirHostPath the daemons keep mon data in an emptyDir.
        spec.setdefault("dataDirHostPath", "/var/lib/rook")
        # The operator sets no image; an external cluster without one only
        # consumes the Ceph cluster.
        external = (spec.get("external") or {}).get("enable")
        if not external and not (spec.get("cephVersion") or {}).get("image"):
            raise CompileError(
                f"rook-ceph: cluster '{self.kwargs.name}' needs ceph_version.image "
                "(for Rook v1.21.0 for example quay.io/ceph/ceph:v20.2.4)"
            )


# =============================================================================
# CephBlockPool
# =============================================================================


class CephBlockPool(RookCephBase):
    """rook-ceph CephBlockPool resource.

    Explicitly modelled fields:
        failure_domain, replicated, erasure_coded, parameters, application

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "failure_domain": "failureDomain",
        "replicated": "replicated",
        "erasure_coded": "erasureCoded",
        "parameters": "parameters",
        "application": "application",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephBlockPool"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        self._build_flat_spec(config)


# =============================================================================
# CephFilesystem
# =============================================================================


class CephFilesystem(RookCephBase):
    """rook-ceph CephFilesystem resource.

    Explicitly modelled fields:
        metadata_pool, data_pools, metadata_server, status_check, mirroring

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "metadata_pool": "metadataPool",
        "data_pools": "dataPools",
        "metadata_server": "metadataServer",
        "status_check": "statusCheck",
        "mirroring": "mirroring",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephFilesystem"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        spec = self._build_flat_spec(config)
        # metadataServer.activeCount is required by the CRD; values from
        # deploy/examples/filesystem.yaml
        server = spec.setdefault("metadataServer", {})
        server.setdefault("activeCount", 1)
        server.setdefault("activeStandby", True)


# =============================================================================
# CephObjectStore
# =============================================================================


class CephObjectStore(RookCephBase):
    """rook-ceph CephObjectStore resource.

    Explicitly modelled fields:
        metadata_pool, data_pool, gateway, zone, hosting, auth, security

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "metadata_pool": "metadataPool",
        "data_pool": "dataPool",
        "gateway": "gateway",
        "zone": "zone",
        "hosting": "hosting",
        "auth": "auth",
        "security": "security",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephObjectStore"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        self._build_flat_spec(config)


# =============================================================================
# CephObjectStoreUser
# =============================================================================


class CephObjectStoreUser(RookCephBase):
    """rook-ceph CephObjectStoreUser resource.

    Explicitly modelled fields:
        store, display_name, capabilities, quotas

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "store": "store",
        "display_name": "displayName",
        "capabilities": "capabilities",
        "quotas": "quotas",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephObjectStoreUser"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        self._build_flat_spec(config)


# =============================================================================
# CephNFS
# =============================================================================


class CephNFS(RookCephBase):
    """rook-ceph CephNFS resource.

    Explicitly modelled fields:
        server, security

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "server": "server",
        "security": "security",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephNFS"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        spec = self._build_flat_spec(config)
        if config.get("rados") is not None:
            logger.warning(
                "'rados' is ignored: the Rook operator sets the .nfs pool and namespace itself"
            )
        # server.active is required by the CRD; deploy/examples/nfs.yaml
        spec.setdefault("server", {}).setdefault("active", 1)


# =============================================================================
# CephRBDMirror
# =============================================================================


class CephRBDMirror(RookCephBase):
    """rook-ceph CephRBDMirror resource.

    Explicitly modelled fields:
        count, peers, resources, placement, priority_class_name

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "count": "count",
        "peers": "peers",
        "resources": "resources",
        "placement": "placement",
        "priority_class_name": "priorityClassName",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephRBDMirror"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        spec = self._build_flat_spec(config)
        # count is required by the CRD; deploy/examples/rbdmirror.yaml
        spec.setdefault("count", 1)


# =============================================================================
# CephClient
# =============================================================================


class CephClient(RookCephBase):
    """rook-ceph CephClient resource.

    Explicitly modelled fields:
        caps, name (also metadata.name), client_name (Ceph client name,
        wins over name so both can differ)

    Passthrough: anything under ``spec``.
    """

    _FLAT_KEY_MAP = {
        "caps": "caps",
        "name": "name",
        "client_name": "name",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "ceph.rook.io/v1"
        self.kwargs.kind = "CephClient"
        super().new()

    def body(self) -> None:
        super().body()
        config = _convert_to_dict(self.kwargs.config)

        self._add_common_metadata(config)
        self._build_flat_spec(config)


# =============================================================================
# Main Entry Point
# =============================================================================


def main(input_params: dict | None = None) -> BaseObj:
    """Generate rook-ceph resources from inventory.

    Reads from ``parameters.generators.rook-ceph``:

    - clusters: CephCluster configurations
    - block_pools: CephBlockPool configurations
    - filesystems: CephFilesystem configurations
    - object_stores: CephObjectStore configurations
    - object_store_users: CephObjectStoreUser configurations
    - nfs: CephNFS configurations
    - rbd_mirrors: CephRBDMirror configurations
    - clients: CephClient configurations

    Args:
        input_params: Input parameters from Kapitan compile configuration.

    Returns:
        BaseObj containing all generated rook-ceph resources.
    """
    obj = BaseObj()

    rook_config = _convert_to_dict(
        inv.parameters.get("generators", {}).get("rook-ceph", {}) or {}
    )
    default_ns = rook_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )

    # Generate CephClusters
    clusters = rook_config.get("clusters", {})
    for name, config in clusters.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        cluster_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{cluster_name}-cephcluster"] = CephCluster(
            name=cluster_name, config=config
        )

    # Generate CephBlockPools
    block_pools = rook_config.get("block_pools", {})
    for name, config in block_pools.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        pool_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{pool_name}-blockpool"] = CephBlockPool(
            name=pool_name, config=config
        )

    # Generate CephFilesystems
    filesystems = rook_config.get("filesystems", {})
    for name, config in filesystems.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        fs_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{fs_name}-cephfs"] = CephFilesystem(
            name=fs_name, config=config
        )

    # Generate CephObjectStores
    object_stores = rook_config.get("object_stores", {})
    for name, config in object_stores.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        store_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{store_name}-objectstore"] = CephObjectStore(
            name=store_name, config=config
        )

    # Generate CephObjectStoreUsers
    object_store_users = rook_config.get("object_store_users", {})
    for name, config in object_store_users.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        user_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{user_name}-objectuser"] = CephObjectStoreUser(
            name=user_name, config=config
        )

    # Generate CephNFS
    nfs = rook_config.get("nfs", {})
    for name, config in nfs.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        nfs_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{nfs_name}-nfs"] = CephNFS(
            name=nfs_name, config=config
        )

    # Generate CephRBDMirrors
    rbd_mirrors = rook_config.get("rbd_mirrors", {})
    for name, config in rbd_mirrors.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        mirror_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{mirror_name}-rbdmirror"] = CephRBDMirror(
            name=mirror_name, config=config
        )

    # Generate CephClients
    clients = rook_config.get("clients", {})
    for name, config in clients.items():
        config = {"namespace": default_ns, **(_convert_to_dict(config) or {})}
        client_name = config.get("name", name)
        obj.root[f"{config['namespace']}/{client_name}-client"] = CephClient(
            name=client_name, config=config
        )

    logger.info(
        "rook-ceph generated resources: "
        "clusters=%d block_pools=%d filesystems=%d object_stores=%d "
        "object_store_users=%d nfs=%d rbd_mirrors=%d clients=%d",
        len(clusters),
        len(block_pools),
        len(filesystems),
        len(object_stores),
        len(object_store_users),
        len(nfs),
        len(rbd_mirrors),
        len(clients),
    )

    return obj


__all__ = [
    "CephCluster",
    "CephBlockPool",
    "CephFilesystem",
    "CephObjectStore",
    "CephObjectStoreUser",
    "CephNFS",
    "CephRBDMirror",
    "CephClient",
    "RookCephBase",
    "main",
]
