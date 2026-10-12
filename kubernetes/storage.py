"""Kubernetes storage resources: PersistentVolume, PersistentVolumeClaim.

This module provides classes for generating Kubernetes storage and namespace
resources. Includes support for persistent volumes, claims, and namespace
configuration.
"""

import logging

from . import k8s
from .utils import _convert_to_dict, get_namespace


logger = logging.getLogger(__name__)


def _apply_spec(resource, config, defaults, flat_keys):
    """Generator defaults < spec passthrough < flat keys, warning on overrides.

    flat_keys maps a flat key to its dotted path below spec; falsy flat values
    count as unset.
    """
    spec = _convert_to_dict(config.get("spec")) or {}
    resource.root.spec.update(defaults)
    resource.root.spec.update(spec)
    for key, path in flat_keys.items():
        value = config.get(key)
        if not value:
            continue
        *parents, leaf = path.split(".")
        given, target = spec, resource.root.spec
        for part in parents:
            given = given.get(part) if isinstance(given, dict) else None
            target = target.setdefault(part, {})
        if isinstance(given, dict) and leaf in given:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                key,
                path,
                resource.root.metadata.name,
            )
        target[leaf] = value


class PersistentVolume(k8s.Base):
    """Kubernetes PersistentVolume resource.

    Generates a PersistentVolume manifest for cluster-level storage.

    Required kwargs:
        volume: Volume configuration dictionary with capacity, access modes, etc.
        name: PV name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("volume")
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "PersistentVolume"
        super().new()

    def body(self) -> None:
        """Build the PersistentVolume."""
        super().body()
        # PersistentVolume is cluster-scoped: no metadata.namespace
        # Retain matches the upstream default for manually created PVs;
        # Recycle is deprecated.
        _apply_spec(
            self,
            self.kwargs.volume,
            {
                "capacity": {},
                "accessModes": ["ReadWriteOnce"],
                "persistentVolumeReclaimPolicy": "Retain",
            },
            {
                "capacity": "capacity",
                "volume_mode": "volumeMode",
                "access_modes": "accessModes",
                "reclaim_policy": "persistentVolumeReclaimPolicy",
                "storage_class_name": "storageClassName",
                "mount_options": "mountOptions",
            },
        )


class PersistentVolumeClaim(k8s.Base):
    """Kubernetes PersistentVolumeClaim resource.

    Generates a PersistentVolumeClaim manifest for requesting storage.
    Can optionally create a bound PersistentVolume.

    Required kwargs:
        volume_claim: Volume claim configuration dictionary.
        name: PVC name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("volume_claim")
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "PersistentVolumeClaim"
        super().new()

    def body(self) -> None:
        """Build the PersistentVolumeClaim."""
        super().body()
        volume_claim = self.kwargs.volume_claim
        # claim -> component -> parameters.namespace, like the `vol` output key
        namespace = volume_claim.get("namespace") or get_namespace(
            self.kwargs.get("component")
        )
        if namespace:
            self.add_namespace(namespace)
        _apply_spec(
            self,
            volume_claim,
            {"accessModes": ["ReadWriteOnce"]},
            {
                "access_modes": "accessModes",
                "storage": "resources.requests.storage",
                "volume_mode": "volumeMode",
                "storage_class": "storageClassName",
            },
        )

    def bind_persistent_volume(self) -> "PersistentVolume":
        """Create a PersistentVolume bound to this claim.

        Returns:
            A PersistentVolume instance configured to match this claim.
        """
        volume_claim = self.kwargs.volume_claim
        volume = {}
        # access_modes is a list, not a dict - use directly with a default
        volume["access_modes"] = volume_claim.get("access_modes", ["ReadWriteOnce"])
        volume["capacity"] = volume_claim.get("pv_capacity", {})
        volume["volume_mode"] = volume_claim.get("volume_mode")
        volume["storage_class_name"] = volume_claim.get("storage_class_name")

        pv_name = volume_claim.get("pv_name") or self.name
        volume = PersistentVolume(name=pv_name, volume=volume)
        self.root.spec.volumeName = pv_name
        return volume
