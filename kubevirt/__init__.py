"""Kapitan generator for KubeVirt CRDs.

Transforms YAML inventory into KubeVirt and CDI custom resource manifests.

Inventory contract:
  parameters.generators.kubevirt:
    virtual_machines:              → VirtualMachine (kubevirt.io/v1)
    virtual_machine_instances:     → VirtualMachineInstance (kubevirt.io/v1)
    virtual_machine_instance_migrations: → VirtualMachineInstanceMigration (kubevirt.io/v1)
    virtual_machine_instance_replica_sets: → VirtualMachineInstanceReplicaSet (kubevirt.io/v1)
    virtual_machine_pools:         → VirtualMachinePool (pool.kubevirt.io/v1beta1)
    virtual_machine_clones:        → VirtualMachineClone (clone.kubevirt.io/v1beta1)
    virtual_machine_snapshots:     → VirtualMachineSnapshot (snapshot.kubevirt.io/v1beta1)
    virtual_machine_restores:      → VirtualMachineRestore (snapshot.kubevirt.io/v1beta1)
    kubevirt_operators:            → KubeVirt (kubevirt.io/v1)
    data_volumes:                  → DataVolume (cdi.kubevirt.io/v1beta1)
    data_sources:                  → DataSource (cdi.kubevirt.io/v1beta1)
    object_transfers:              → ObjectTransfer (cdi.kubevirt.io/v1beta1)
    csi:                           → KubeVirt CSI driver, infra or tenant side (csi.py)

Smart defaults for VM-like resources:
  - ``image: quay.io/...`` → auto-builds containerDisk volume + virtio disk
  - ``disks: [{name: data, size: 10Gi}]`` → auto-builds dataVolumeTemplates,
    dataVolume volumes, and virtio disks
  - ``interfaces`` / ``networks`` → default to pod network with masquerade
  - ``instancetype`` / ``preference`` → accepts string or dict
  - ``cloudinit`` → auto-builds cloudInitNoCloud volume
  - ``run_strategy`` → required (or ``running`` / ``spec.runStrategy``)

Precedence: generator defaults < ``spec`` < flat keys. ``spec_strategy:
replace`` drops the generator defaults.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from kapitan.inputs.kadet import BaseObj, inventory

from . import csi, k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.4.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


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


VALID_SPEC_STRATEGIES = frozenset(["replace", "merge"])


def _deep_merge(base: dict, override: dict) -> dict:
    """Return base with override deep-merged on top (override wins on leaves)."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dig(data: Any, path: str) -> Any:
    """Return the value at a dotted path, or None."""
    for part in path.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _combine_spec(
    name: str,
    config: dict,
    flat: dict[str, Any],
    flat_paths: dict[str, tuple[str, ...]],
) -> tuple[dict[str, Any], bool]:
    """Deep-merge the flat-key result over ``spec``; flat keys win.

    Returns the merged spec and whether generator defaults apply, which they
    do unless ``spec_strategy: replace`` accompanies an explicit ``spec``.
    """
    spec = cast("dict[str, Any]", _convert_to_dict(config.get("spec")) or {})
    strategy = config.get("spec_strategy", "merge")
    if strategy not in VALID_SPEC_STRATEGIES:
        raise ValueError(
            f"kubevirt '{name}': invalid spec_strategy {strategy!r}; "
            f"must be one of {sorted(VALID_SPEC_STRATEGIES)}"
        )
    for flat_key, paths in flat_paths.items():
        if config.get(flat_key) is None:
            continue
        for path in paths:
            if _dig(flat, path) is not None and _dig(spec, path) is not None:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    flat_key,
                    path,
                    name,
                )
    apply_defaults = not ("spec" in config and strategy == "replace")
    return _deep_merge(spec, flat), apply_defaults


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


def _default_namespace() -> str:
    """Namespace fallback chain: generators.kubevirt.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("kubevirt", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


class KubevirtBase(k8s.Base):
    """Base class shared by all KubeVirt and CDI resource classes."""

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", _default_namespace())

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# ---------------------------------------------------------------------------
# Smart builders for VM-like resources
# ---------------------------------------------------------------------------


def _build_disks(config: dict) -> list[dict[str, Any]]:
    """Build ``domain.devices.disks`` from friendly config.

    Handles ``image`` (containerDisk) and ``disks`` (dataVolume / blank).
    """
    disks: list[dict[str, Any]] = []

    if config.get("image"):
        disks.append(
            {
                "name": "containerdisk",
                "disk": {"bus": config.get("disk_bus", "virtio")},
            }
        )

    for disk in config.get("disks", []):
        disk_name = disk["name"]
        disk_type = disk.get("type", "disk")
        if disk_type == "cdrom":
            # KubeVirt rejects virtio for CD-ROMs and defaults their bus itself.
            device: dict[str, Any] = {
                "cdrom": {"readonly": disk.get("readonly", True)}
            }
            if "bus" in disk:
                device["cdrom"]["bus"] = disk["bus"]
        else:
            bus = disk.get("bus", config.get("disk_bus", "virtio"))
            device = {disk_type: {"bus": bus}}
        disks.append({"name": disk_name, **device})

    # Every cloud-init volume needs a matching disk or the VM is rejected.
    # Names match _build_cloudinit_volumes: inline -> cloudinitdisk,
    # secretRef -> cloudinit.
    if config.get("cloudinit"):
        disks.append(
            {
                "name": "cloudinitdisk",
                "disk": {"bus": config.get("disk_bus", "virtio")},
            }
        )

    if config.get("cloudinit_secret_ref"):
        disks.append(
            {
                "name": "cloudinit",
                "disk": {"bus": config.get("disk_bus", "virtio")},
            }
        )

    return disks


def _build_cloudinit_volumes(config: dict) -> list[dict[str, Any]]:
    """Build cloudInitNoCloud volumes from inline userData or secretRef."""
    volumes: list[dict[str, Any]] = []
    if config.get("cloudinit"):
        volumes.append(
            {
                "name": "cloudinitdisk",
                "cloudInitNoCloud": {"userData": config["cloudinit"]},
            }
        )
    secret_ref = config.get("cloudinit_secret_ref")
    if secret_ref:
        # String shorthand for the upstream LocalObjectReference ({"name": ...})
        if isinstance(secret_ref, str):
            secret_ref = {"name": secret_ref}
        volumes.append(
            {
                "name": "cloudinit",
                "cloudInitNoCloud": {"secretRef": _convert_to_dict(secret_ref)},
            }
        )
    return volumes


def _build_volumes(config: dict, vm_name: str) -> list[dict[str, Any]]:
    """Build ``volumes`` that reference disks and interfaces."""
    volumes: list[dict[str, Any]] = []

    if config.get("image"):
        volumes.append(
            {
                "name": "containerdisk",
                "containerDisk": {"image": config["image"]},
            }
        )

    for disk in config.get("disks", []):
        disk_name = disk["name"]
        volume: dict[str, Any] = {"name": disk_name}
        if "size" in disk:
            dv_name = disk.get("dvt_name", f"{vm_name}-{disk_name}")
            volume["dataVolume"] = {"name": dv_name}
        elif "source" in disk:
            volume["dataVolume"] = {"name": disk_name}
        elif "blank" in disk:
            volume["emptyDisk"] = {"capacity": disk["blank"]}
        elif "ephemeral" in disk:
            volume["ephemeral"] = _convert_to_dict(disk["ephemeral"])
        volumes.append(volume)

    volumes.extend(_build_cloudinit_volumes(config))
    return volumes


def _build_data_volume_templates(config: dict, vm_name: str) -> list[dict[str, Any]]:
    """Build ``dataVolumeTemplates`` from disks that declare ``size``."""
    dvts: list[dict[str, Any]] = []
    for disk in config.get("disks", []):
        if "size" not in disk:
            continue
        dvt_name = disk.get("dvt_name", f"{vm_name}-{disk['name']}")
        dvt: dict[str, Any] = {
            "metadata": {"name": dvt_name},
            "spec": {},
        }
        if "source" in disk:
            dvt["spec"]["source"] = _convert_to_dict(disk["source"])
        elif "blank" in disk:
            dvt["spec"]["source"] = {"blank": {}}
        elif "pvc" in disk:
            dvt["spec"]["source"] = {"pvc": _convert_to_dict(disk["pvc"])}
        else:
            dvt["spec"]["source"] = {"blank": {}}
        storage = disk.get("storage", {})
        if not storage:
            storage = {"resources": {"requests": {"storage": disk["size"]}}}
        dvt["spec"]["storage"] = _convert_to_dict(storage)
        dvts.append(dvt)
    return dvts


def _build_interfaces(config: dict) -> list[dict[str, Any]] | None:
    """Build ``domain.devices.interfaces`` from the flat key."""
    if config.get("interfaces"):
        return cast("list[dict[str, Any]]", _convert_to_dict(config["interfaces"]))
    return None


def _build_networks(config: dict) -> list[dict[str, Any]] | None:
    """Build ``networks`` from the flat key."""
    if config.get("networks"):
        return cast("list[dict[str, Any]]", _convert_to_dict(config["networks"]))
    return None


def _apply_vmi_defaults(vmi_spec: dict[str, Any]) -> None:
    """Fill the VMI-level generator defaults the inventory left unset."""
    domain = vmi_spec.setdefault("domain", {})
    domain.setdefault("devices", {}).setdefault(
        "interfaces", [{"name": "default", "masquerade": {}}]
    )
    vmi_spec.setdefault("networks", [{"name": "default", "pod": {}}])


# Maximum scheduler weight — spread pool VMs across hosts as strongly as a
# soft (preferred) anti-affinity rule allows.
_POOL_ANTI_AFFINITY_WEIGHT = 100


def _default_pool_pod_anti_affinity(instance: str) -> dict[str, Any]:
    """Return default podAntiAffinity for a VirtualMachinePool.

    Matches the ``app.kubernetes.io/instance`` label the pool defaults put on
    the VMI template; virt-launcher pods carry the VMI labels.
    """
    return {
        "podAntiAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "weight": _POOL_ANTI_AFFINITY_WEIGHT,
                    "podAffinityTerm": {
                        "labelSelector": {
                            "matchExpressions": [
                                {
                                    "key": "app.kubernetes.io/instance",
                                    "operator": "In",
                                    "values": [instance],
                                }
                            ]
                        },
                        "topologyKey": "kubernetes.io/hostname",
                    },
                }
            ]
        }
    }


def _apply_disk_bus_defaults(devices: dict[str, Any]) -> None:
    """Default disk and LUN bus to virtio when not explicitly set.

    CD-ROMs are left to KubeVirt, which rejects virtio for them.
    """
    for disk in devices.get("disks", []):
        for device_key in ("disk", "lun"):
            if device_key in disk:
                disk[device_key].setdefault("bus", "virtio")


def _apply_vm_pool_defaults(vmt: dict, pool_name: str, config: dict) -> None:
    """Apply pool defaults to a VirtualMachinePool template where unset."""
    vmt_spec = vmt.setdefault("spec", {})

    vmi_template = vmt_spec.setdefault("template", {})
    vmi_metadata = vmi_template.setdefault("metadata", {})
    labels = vmi_metadata.setdefault("labels", {})

    instance = config.get("name") or pool_name
    labels.setdefault("app.kubernetes.io/instance", instance)
    labels.setdefault("app.kubernetes.io/managed-by", "kapitan")

    vmi_spec = vmi_template.setdefault("spec", {})
    _apply_vmi_defaults(vmi_spec)
    domain = vmi_spec["domain"]
    # An instancetype owns CPU and memory; KubeVirt rejects both set.
    if "instancetype" not in vmt_spec:
        domain.setdefault("cpu", {"cores": 2})
        domain.setdefault("memory", {"guest": "2Gi"})

    _apply_disk_bus_defaults(domain["devices"])

    if "affinity" not in vmi_spec:
        vmi_spec["affinity"] = _default_pool_pod_anti_affinity(instance)


def _build_domain(config: dict) -> dict[str, Any]:
    """Build the ``domain`` block from friendly config."""
    domain: dict[str, Any] = {}
    devices: dict[str, Any] = {}

    disks = _build_disks(config)
    if disks:
        devices["disks"] = disks

    interfaces = _build_interfaces(config)
    if interfaces:
        devices["interfaces"] = interfaces

    if devices:
        domain["devices"] = devices

    if "machine" in config:
        domain["machine"] = _convert_to_dict(config["machine"])
    elif "machine_type" in config:
        domain["machine"] = {"type": config["machine_type"]}

    if "resources" in config:
        domain["resources"] = _convert_to_dict(config["resources"])

    if "cpu" in config:
        domain["cpu"] = _convert_to_dict(config["cpu"])

    if "memory" in config:
        memory = config["memory"]
        if isinstance(memory, str):
            domain["memory"] = {"guest": memory}
        else:
            domain["memory"] = _convert_to_dict(memory)

    return domain


def _build_run_strategy(config: dict) -> dict[str, Any]:
    """Return ``runStrategy`` or ``running`` entry (mutually exclusive)."""
    if "run_strategy" in config:
        return {"runStrategy": config["run_strategy"]}
    if "running" in config:
        return {"running": config["running"]}
    return {}


def _build_vm_template_metadata(config: dict) -> dict[str, Any]:
    """Build the template ``metadata`` from labels, annotations and overrides."""
    metadata: dict[str, Any] = {}
    if config.get("labels"):
        metadata["labels"] = _convert_to_dict(config["labels"])
    if config.get("annotations"):
        metadata["annotations"] = _convert_to_dict(config["annotations"])
    if "template_metadata" in config:
        metadata.update(_convert_to_dict(config["template_metadata"]))
    return metadata


def _build_vmi_flat(name: str, config: dict) -> dict[str, Any]:
    """Build a VMI ``spec`` from the flat keys only."""
    spec: dict[str, Any] = {}
    domain = _build_domain(config)
    if domain:
        spec["domain"] = domain

    volumes = _build_volumes(config, name)
    if volumes:
        spec["volumes"] = volumes

    networks = _build_networks(config)
    if networks:
        spec["networks"] = networks
    return spec


def _build_vm_template(name: str, config: dict) -> dict[str, Any]:
    """Build the ``template`` block for a VM spec from the flat keys."""
    template: dict[str, Any] = {}
    if (
        "template_metadata" in config
        or config.get("labels")
        or config.get("annotations")
    ):
        template["metadata"] = _build_vm_template_metadata(config)

    template_spec = _build_vmi_flat(name, config)

    if "tolerations" in config:
        template_spec["tolerations"] = _convert_to_dict(config["tolerations"])

    if "affinity" in config:
        template_spec["affinity"] = _convert_to_dict(config["affinity"])

    if template_spec:
        template["spec"] = template_spec

    return template


def _build_vm_flat(name: str, config: dict) -> dict[str, Any]:
    """Build a VM ``spec`` from the flat keys only."""
    spec: dict[str, Any] = {}
    spec.update(_build_run_strategy(config))

    if "instancetype" in config:
        spec["instancetype"] = _normalize_name_ref(config["instancetype"])
    if "preference" in config:
        spec["preference"] = _normalize_name_ref(config["preference"])

    dvts = _build_data_volume_templates(config, name)
    if dvts:
        spec["dataVolumeTemplates"] = dvts

    template = _build_vm_template(name, config)
    if template:
        spec["template"] = template
    return spec


# Flat key -> VMI spec paths it sets (for the override warning).
_VMI_FLAT_PATHS: dict[str, tuple[str, ...]] = {
    "image": ("domain.devices.disks", "volumes"),
    "disks": ("domain.devices.disks", "volumes"),
    "cloudinit": ("domain.devices.disks", "volumes"),
    "cloudinit_secret_ref": ("domain.devices.disks", "volumes"),
    "interfaces": ("domain.devices.interfaces",),
    "networks": ("networks",),
    "machine": ("domain.machine",),
    "machine_type": ("domain.machine",),
    "resources": ("domain.resources",),
    "cpu": ("domain.cpu",),
    "memory": ("domain.memory",),
}


def _prefixed(prefix: str, paths: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    return {key: tuple(prefix + p for p in value) for key, value in paths.items()}


_VM_FLAT_PATHS: dict[str, tuple[str, ...]] = {
    **_prefixed("template.spec.", _VMI_FLAT_PATHS),
    "disks": (
        "dataVolumeTemplates",
        "template.spec.domain.devices.disks",
        "template.spec.volumes",
    ),
    "run_strategy": ("runStrategy",),
    "running": ("running",),
    "instancetype": ("instancetype",),
    "preference": ("preference",),
    "tolerations": ("template.spec.tolerations",),
    "affinity": ("template.spec.affinity",),
    "template_metadata": ("template.metadata",),
}


def _require_run_strategy(vm_spec: dict[str, Any], kind: str, resource: str) -> None:
    """KubeVirt admission rejects a VM without a run strategy; fail at compile."""
    if "runStrategy" not in vm_spec and "running" not in vm_spec:
        raise ValueError(
            f"kubevirt {kind} '{resource}': no run strategy; set run_strategy "
            "(Always, RerunOnFailure, Once, Manual or Halted) or spec.runStrategy"
        )


def _build_vm_spec(name: str, config: dict) -> dict[str, Any]:
    """Build a VM spec: generator defaults < ``spec`` < flat keys."""
    spec, apply_defaults = _combine_spec(
        name, config, _build_vm_flat(name, config), _VM_FLAT_PATHS
    )
    if apply_defaults:
        template = spec.setdefault("template", {})
        _apply_vmi_defaults(template.setdefault("spec", {}))
    _require_run_strategy(spec, "VirtualMachine", name)
    return spec


# Flat keys that can be promoted from pool-level config into a VM spec.
_VM_FLAT_KEYS = {
    "disks",
    "interfaces",
    "networks",
    "image",
    "cloudinit",
    "cloudinit_secret_ref",
    "cpu",
    "memory",
    "resources",
    "machine_type",
    "machine",
    "instancetype",
    "preference",
    "run_strategy",
    "running",
    "tolerations",
    "affinity",
    "disk_bus",
    "template_metadata",
}


def _normalize_name_ref(value: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize a string name or dict to a ``{name: ...}`` reference."""
    if isinstance(value, str):
        return {"name": value}
    return cast("dict[str, Any]", _convert_to_dict(value))


def _normalize_ref(
    ref: str | dict[str, Any],
    default_group: str = "kubevirt.io",
    default_kind: str = "VirtualMachine",
) -> dict[str, Any]:
    """Normalize a resource reference to a dict with apiGroup/kind defaults."""
    result = _normalize_name_ref(ref)
    if "apiGroup" not in result:
        result["apiGroup"] = default_group
    if "kind" not in result:
        result["kind"] = default_kind
    return result


def _build_vmi_spec(name: str, config: dict) -> dict[str, Any]:
    """Build a VMI spec: generator defaults < ``spec`` < flat keys."""
    _warn_ignored_disk_sizes(name, config)
    spec, apply_defaults = _combine_spec(
        name, config, _build_vmi_flat(name, config), _VMI_FLAT_PATHS
    )
    if apply_defaults:
        _apply_vmi_defaults(spec)
    return spec


def _warn_ignored_disk_sizes(name: str, config: dict) -> None:
    for disk in config.get("disks", []):
        if "size" in disk:
            logger.warning(
                "kubevirt '%s': disk '%s' size %s is ignored: only a "
                "VirtualMachine has dataVolumeTemplates; the volume references "
                "DataVolume '%s', which must exist",
                name,
                disk["name"],
                disk["size"],
                disk.get("dvt_name", f"{name}-{disk['name']}"),
            )


def _simple_spec(
    name: str, config: dict, flat: dict[str, Any], flat_paths: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """``spec`` with the flat keys merged on top, for kinds without defaults."""
    return _combine_spec(name, config, flat, flat_paths)[0]


# ---------------------------------------------------------------------------
# kubevirt.io/v1 resources
# ---------------------------------------------------------------------------


class VirtualMachine(KubevirtBase):
    """KubeVirt VirtualMachine resource."""

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kubevirt.io/v1"
        self.kwargs.kind = "VirtualMachine"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        self.root.spec = _build_vm_spec(self.kwargs.name, config)


class VirtualMachineInstance(KubevirtBase):
    """KubeVirt VirtualMachineInstance resource."""

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kubevirt.io/v1"
        self.kwargs.kind = "VirtualMachineInstance"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        self.root.spec = _build_vmi_spec(self.kwargs.name, config)


class VirtualMachineInstanceMigration(KubevirtBase):
    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kubevirt.io/v1"
        self.kwargs.kind = "VirtualMachineInstanceMigration"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "vmi_name" in config:
            flat["vmiName"] = config["vmi_name"]
        self.root.spec = _simple_spec(
            self.kwargs.name, config, flat, {"vmi_name": ("vmiName",)}
        )


_VMIRS_FLAT_PATHS: dict[str, tuple[str, ...]] = {
    **_prefixed("template.spec.", _VMI_FLAT_PATHS),
    "replicas": ("replicas",),
    "selector": ("selector",),
    "template_metadata": ("template.metadata",),
}


class VirtualMachineInstanceReplicaSet(KubevirtBase):
    """KubeVirt VirtualMachineInstanceReplicaSet resource."""

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kubevirt.io/v1"
        self.kwargs.kind = "VirtualMachineInstanceReplicaSet"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        name = self.kwargs.name
        self._add_common_metadata(config)
        _warn_ignored_disk_sizes(name, config)

        flat: dict[str, Any] = {}
        if "replicas" in config:
            flat["replicas"] = config["replicas"]
        if config.get("selector"):
            flat["selector"] = _convert_to_dict(config["selector"])
        template: dict[str, Any] = {}
        if "template_metadata" in config:
            template["metadata"] = _convert_to_dict(config["template_metadata"])
        template_spec = _build_vmi_flat(name, config)
        if template_spec:
            template["spec"] = template_spec
        if template:
            flat["template"] = template

        spec, apply_defaults = _combine_spec(name, config, flat, _VMIRS_FLAT_PATHS)
        if apply_defaults:
            spec.setdefault(
                "selector", {"matchLabels": {"app.kubernetes.io/instance": name}}
            )
            template = spec.setdefault("template", {})
            _apply_vmi_defaults(template.setdefault("spec", {}))
            # KubeVirt rejects a VMIRS whose selector does not match the
            # template labels; inject the selector's matchLabels.
            match_labels = spec["selector"].get("matchLabels", {})
            if match_labels:
                template_labels = template.setdefault("metadata", {}).setdefault(
                    "labels", {}
                )
                for key, value in match_labels.items():
                    template_labels.setdefault(key, value)
        self.root.spec = spec


class KubeVirt(KubevirtBase):
    """KubeVirt operator configuration; lives in the operator's namespace."""

    def _resource_namespace(self, config: dict) -> Any:
        # Namespace of the upstream release manifests (kubevirt-cr.yaml).
        return config.get("namespace", "kubevirt")

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kubevirt.io/v1"
        self.kwargs.kind = "KubeVirt"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        # The CRD requires spec, and none of its fields.
        self.root.spec = _convert_to_dict(config.get("spec")) or {}


# ---------------------------------------------------------------------------
# pool.kubevirt.io/v1beta1 resources
# ---------------------------------------------------------------------------


def _ensure_pool_selector(spec: dict[str, Any], name: str) -> None:
    """Ensure a VirtualMachinePool ``spec`` has a valid ``selector``.

    Derives the selector from ``virtualMachineTemplate.metadata.labels``,
    falling back to VMI-template labels, then to a default instance label.
    """
    if "selector" in spec:
        return
    vmt = spec.get("virtualMachineTemplate", {})
    vm_meta_labels = vmt.get("metadata", {}).get("labels", {})
    vmi_template_labels = (
        vmt.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    )
    if vm_meta_labels:
        spec["selector"] = {"matchLabels": dict(vm_meta_labels)}
    elif vmi_template_labels:
        vmt.setdefault("metadata", {})["labels"] = dict(vmi_template_labels)
        spec["selector"] = {"matchLabels": dict(vmi_template_labels)}
    else:
        spec["selector"] = {"matchLabels": {"app.kubernetes.io/instance": name}}


_POOL_FLAT_PATHS: dict[str, tuple[str, ...]] = {
    **_prefixed("virtualMachineTemplate.spec.", _VM_FLAT_PATHS),
    "replicas": ("replicas",),
    "selector": ("selector",),
    "virtual_machine_template": ("virtualMachineTemplate",),
}


def _build_pool_spec(name: str, config: dict) -> dict[str, Any]:
    """Build a VirtualMachinePool spec: generator defaults < ``spec`` < flat keys."""
    flat: dict[str, Any] = {}
    if "replicas" in config:
        flat["replicas"] = config["replicas"]
    if config.get("selector"):
        flat["selector"] = _convert_to_dict(config["selector"])

    vm_template = config.get("virtual_machine_template")
    if vm_template:
        flat["virtualMachineTemplate"] = _convert_to_dict(vm_template)
    else:
        vm_config = {
            key: config[key]
            for key in (*_VM_FLAT_KEYS, "labels", "annotations")
            if key in config
        }
        vm_spec = _build_vm_flat(name, vm_config)
        if vm_spec:
            flat["virtualMachineTemplate"] = {"spec": vm_spec}

    spec, apply_defaults = _combine_spec(name, config, flat, _POOL_FLAT_PATHS)
    vmt = spec.setdefault("virtualMachineTemplate", {})
    if apply_defaults:
        spec.setdefault("replicas", 1)
        _apply_vm_pool_defaults(vmt, name, config)
    _require_run_strategy(vmt.get("spec", {}), "VirtualMachinePool", name)

    vm_meta_labels = vmt.get("metadata", {}).get("labels", {})
    vmi_template_labels = (
        vmt.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    )
    if not vm_meta_labels and vmi_template_labels:
        vmt.setdefault("metadata", {})["labels"] = dict(vmi_template_labels)
    _ensure_pool_selector(spec, name)
    return spec


class VirtualMachinePool(KubevirtBase):
    """KubeVirt VirtualMachinePool resource.

    Defines a pool of VirtualMachines that are auto-scaled.
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "pool.kubevirt.io/v1beta1"
        self.kwargs.kind = "VirtualMachinePool"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        # In flat mode the pool metadata itself gets no labels/annotations.
        flat_mode = "virtual_machine_template" not in config
        metadata_config = (
            {k: v for k, v in config.items() if k not in ("annotations", "labels")}
            if flat_mode
            else config
        )
        self._add_common_metadata(metadata_config)
        self.root.spec = _build_pool_spec(self.kwargs.name, config)


# ---------------------------------------------------------------------------
# clone.kubevirt.io/v1beta1 resources
# ---------------------------------------------------------------------------


class VirtualMachineClone(KubevirtBase):
    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "clone.kubevirt.io/v1beta1"
        self.kwargs.kind = "VirtualMachineClone"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "source" in config:
            flat["source"] = _normalize_ref(config["source"])
        if "target" in config:
            flat["target"] = _normalize_ref(config["target"])
        self.root.spec = _simple_spec(
            self.kwargs.name,
            config,
            flat,
            {"source": ("source",), "target": ("target",)},
        )


# ---------------------------------------------------------------------------
# snapshot.kubevirt.io/v1beta1 resources
# ---------------------------------------------------------------------------


class VirtualMachineSnapshot(KubevirtBase):
    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "snapshot.kubevirt.io/v1beta1"
        self.kwargs.kind = "VirtualMachineSnapshot"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "source" in config:
            flat["source"] = _normalize_ref(config["source"])
        self.root.spec = _simple_spec(
            self.kwargs.name, config, flat, {"source": ("source",)}
        )


class VirtualMachineRestore(KubevirtBase):
    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "snapshot.kubevirt.io/v1beta1"
        self.kwargs.kind = "VirtualMachineRestore"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "target" in config:
            flat["target"] = _normalize_ref(config["target"])
        if "snapshot_name" in config:
            flat["virtualMachineSnapshotName"] = config["snapshot_name"]
        self.root.spec = _simple_spec(
            self.kwargs.name,
            config,
            flat,
            {
                "target": ("target",),
                "snapshot_name": ("virtualMachineSnapshotName",),
            },
        )


# ---------------------------------------------------------------------------
# cdi.kubevirt.io/v1beta1 resources
# ---------------------------------------------------------------------------


class DataVolume(KubevirtBase):
    """CDI DataVolume resource."""

    _FLAT_PATHS = {
        "source": ("source",),
        "storage": ("storage",),
        "size": ("storage.resources.requests.storage",),
        "pvc": ("pvc",),
        "content_type": ("contentType",),
        "preallocation": ("preallocation",),
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "cdi.kubevirt.io/v1beta1"
        self.kwargs.kind = "DataVolume"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "source" in config:
            flat["source"] = _convert_to_dict(config["source"])
        if "storage" in config:
            flat["storage"] = _convert_to_dict(config["storage"])
        elif "size" in config:
            flat["storage"] = {"resources": {"requests": {"storage": config["size"]}}}
        if "pvc" in config:
            flat["pvc"] = _convert_to_dict(config["pvc"])
        if "content_type" in config:
            flat["contentType"] = config["content_type"]
        if "preallocation" in config:
            flat["preallocation"] = config["preallocation"]
        self.root.spec = _simple_spec(self.kwargs.name, config, flat, self._FLAT_PATHS)


class DataSource(KubevirtBase):
    """CDI DataSource resource."""

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "cdi.kubevirt.io/v1beta1"
        self.kwargs.kind = "DataSource"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        flat: dict[str, Any] = {}
        if "pvc_name" in config:
            pvc_ref: dict[str, Any] = {"name": config["pvc_name"]}
            if "pvc_namespace" in config:
                pvc_ref["namespace"] = config["pvc_namespace"]
            flat["source"] = {"pvc": pvc_ref}
        spec = _simple_spec(
            self.kwargs.name,
            config,
            flat,
            {
                "pvc_name": ("source.pvc.name",),
                "pvc_namespace": ("source.pvc.namespace",),
            },
        )
        pvc = _dig(spec, "source.pvc")
        if isinstance(pvc, dict):
            # The CRD requires source.pvc.namespace; default to our own.
            pvc.setdefault("namespace", self._resource_namespace(config))
        self.root.spec = spec


def _normalize_transfer_source(
    ref: str | dict[str, Any], default_namespace: str
) -> dict[str, Any]:
    """Normalize an ObjectTransfer source to ``{kind, name, namespace}``.

    The CDI TransferSource schema requires kind, name and namespace and
    forbids apiGroup (unlike the clone/snapshot object references).
    """
    if isinstance(ref, str):
        return {"kind": "DataVolume", "name": ref, "namespace": default_namespace}
    result = cast("dict[str, Any]", _convert_to_dict(ref))
    result.setdefault("kind", "DataVolume")
    result.setdefault("namespace", default_namespace)
    return result


def _normalize_transfer_target(ref: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize an ObjectTransfer target to ``{name[, namespace]}``."""
    if isinstance(ref, str):
        return {"name": ref}
    return cast("dict[str, Any]", _convert_to_dict(ref))


class ObjectTransfer(KubevirtBase):
    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "cdi.kubevirt.io/v1beta1"
        self.kwargs.kind = "ObjectTransfer"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        # Cluster-scoped; ``namespace`` only defaults the source namespace.
        self._add_common_metadata(config, include_namespace=False)
        default_namespace = config.get("namespace", _default_namespace())
        flat: dict[str, Any] = {}
        if "source" in config:
            flat["source"] = _normalize_transfer_source(
                config["source"], default_namespace
            )
        if "target" in config:
            flat["target"] = _normalize_transfer_target(config["target"])
        self.root.spec = _simple_spec(
            self.kwargs.name,
            config,
            flat,
            {"source": ("source",), "target": ("target",)},
        )


# ---------------------------------------------------------------------------
# main() — entry point called by Kapitan
# ---------------------------------------------------------------------------

RESOURCE_MAP: dict[str, tuple[type[KubevirtBase], str]] = {
    "virtual_machines": (VirtualMachine, "vm"),
    "virtual_machine_instances": (VirtualMachineInstance, "vmi"),
    "virtual_machine_instance_migrations": (VirtualMachineInstanceMigration, "vmim"),
    "virtual_machine_instance_replica_sets": (
        VirtualMachineInstanceReplicaSet,
        "vmirs",
    ),
    "virtual_machine_pools": (VirtualMachinePool, "vmpool"),
    "virtual_machine_clones": (VirtualMachineClone, "vmclone"),
    "virtual_machine_snapshots": (VirtualMachineSnapshot, "vmsnapshot"),
    "virtual_machine_restores": (VirtualMachineRestore, "vmrestore"),
    "kubevirt_operators": (KubeVirt, "kv"),
    "data_volumes": (DataVolume, "dv"),
    "data_sources": (DataSource, "ds"),
    "object_transfers": (ObjectTransfer, "ot"),
}

__all__ = [
    "main",
    "inv",
    "k8s",
    "__version__",
    "_convert_to_dict",
    "VirtualMachine",
    "VirtualMachineInstance",
    "VirtualMachineInstanceMigration",
    "VirtualMachineInstanceReplicaSet",
    "VirtualMachinePool",
    "VirtualMachineClone",
    "VirtualMachineSnapshot",
    "VirtualMachineRestore",
    "KubeVirt",
    "DataVolume",
    "DataSource",
    "ObjectTransfer",
    "KubevirtBase",
    "RESOURCE_MAP",
    "_build_vm_spec",
    "_build_vmi_spec",
    "_build_domain",
    "_build_disks",
    "_build_volumes",
    "_build_interfaces",
    "_build_networks",
    "_build_data_volume_templates",
    "_combine_spec",
    "_normalize_name_ref",
    "_normalize_ref",
    "_build_run_strategy",
    "_build_vm_template",
    "_build_cloudinit_volumes",
    "_default_pool_pod_anti_affinity",
    "_apply_disk_bus_defaults",
    "_ensure_pool_selector",
    "_build_pool_spec",
]


def main(input_params: dict | None = None) -> BaseObj:
    obj = BaseObj()
    generator_config = inv.parameters.get("generators", {}).get("kubevirt", {}) or {}
    generator_config = _convert_to_dict(generator_config)
    default_namespace = _default_namespace()

    for inventory_key, (resource_cls, suffix) in RESOURCE_MAP.items():
        for name, config in generator_config.get(inventory_key, {}).items():
            config = _convert_to_dict(config) or {}
            # ObjectTransfer is cluster-scoped; the KubeVirt CR keeps its
            # historical un-prefixed output key.
            if resource_cls in (KubeVirt, ObjectTransfer):
                obj.root[f"{name}-{suffix}"] = resource_cls(name=name, config=config)
            else:
                namespace = config.get("namespace", default_namespace)
                obj.root[f"{namespace}/{name}-{suffix}"] = resource_cls(
                    name=name, config=config
                )
    if "csi" in generator_config:
        csi.render(obj, generator_config["csi"] or {}, default_namespace)

    return obj
