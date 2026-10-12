"""IronCore generator for Kapitan.

Generates IronCore cloud-native IaaS resources:
- Machine: Compute instances with networking and block storage
- Volume: Block storage volumes with optional encryption and data sources
- Network: Virtual networks with optional peering
- NetworkInterface: Network attachments (IPs, prefixes, VirtualIP)
- VirtualIP: Floating / public IP addresses
- LoadBalancer: L4 load balancers (Public or Internal)
- NATGateway: Network address translation (Public)
- NetworkPolicy: Ingress / egress network policies

API groups:
  compute.ironcore.dev/v1alpha1
  storage.ironcore.dev/v1alpha1
  networking.ironcore.dev/v1alpha1

See: https://github.com/ironcore-dev/ironcore
"""

__version__ = "1.0.0"

import ipaddress
import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid enum values
# ---------------------------------------------------------------------------

VALID_POWER_STATES = frozenset({"On", "Off"})
VALID_IP_FAMILIES = frozenset({"IPv4", "IPv6"})
VALID_LB_TYPES = frozenset({"Public", "Internal"})
VALID_NAT_TYPES = frozenset({"Public"})
VALID_VIP_TYPES = frozenset({"Public"})
VALID_POLICY_TYPES = frozenset({"Ingress", "Egress"})
VALID_PROTOCOLS = frozenset({"TCP", "UDP", "SCTP"})

__all__ = [
    "IronCoreNetwork",
    "IronCoreNetworkInterface",
    "IronCoreVirtualIP",
    "IronCoreVolume",
    "IronCoreMachine",
    "IronCoreLoadBalancer",
    "IronCoreNATGateway",
    "IronCoreNetworkPolicy",
    "main",
    "k8s",
    "inv",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES: tuple[type, ...] = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj/kadet/OmegaConf objects to plain dicts."""
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


def _get_flat(config: dict, snake_key: str, camel_key: str) -> Any:
    """Read a flat config key: snake_case (repo convention) wins, camelCase
    spelling stays supported for backward compatibility."""
    value = config.get(snake_key)
    if value is None and camel_key != snake_key:
        value = config.get(camel_key)
    return value


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge user-provided `spec` dict into the resource spec verbatim."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: Any, flat_key_map: dict[str, str], name: str) -> None:
    """Warn when a flat abstraction key would overwrite a value from `spec`."""
    spec_override = config.get("spec") if hasattr(config, "get") else None
    if not spec_override:
        return
    spec_dict = _convert_to_dict(spec_override) or {}
    for flat_key, crd_key in flat_key_map.items():
        if _get_flat(config, flat_key, crd_key) is not None and crd_key in spec_dict:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


def _validate_enum(value: str, valid_values: frozenset, field_name: str) -> None:
    """Raise ValueError if *value* is not in *valid_values*."""
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            f"Must be one of: {', '.join(sorted(valid_values))}"
        )


def _local_object_reference(ref: Any) -> Any:
    """A bare string names the referenced object; a dict passes through unchanged."""
    return {"name": ref} if isinstance(ref, str) else ref


def _value_source(entry: Any) -> dict:
    """IPSource/PrefixSource: a plain string is ``{value: <string>}``, a dict passes through."""
    if isinstance(entry, str):
        return {"value": entry}
    return dict(entry)


def _ip_families(ips: list) -> list:
    """IP family per IP source, in order: the family of a ``value``, else the
    ``ipFamily`` of an ephemeral prefix template."""
    families = []
    for ip in ips:
        if "value" in ip:
            families.append(f"IPv{ipaddress.ip_address(ip['value']).version}")
            continue
        family = ip.get("ephemeral", {}).get("prefixTemplate", {}).get("spec", {}).get("ipFamily")
        if family is None:
            raise ValueError(
                f"Cannot derive ipFamilies for ip source {ip}: set ip_families "
                "or ephemeral.prefixTemplate.spec.ipFamily"
            )
        families.append(family)
    return families


# ---------------------------------------------------------------------------
# Base IronCore Resource
# ---------------------------------------------------------------------------


class IronCoreBase(k8s.Base):
    """Base class for all IronCore resources."""

    def _add_common_metadata(self, config: dict) -> None:
        self.add_namespace(config["namespace"])
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# ---------------------------------------------------------------------------
# networking.ironcore.dev/v1alpha1
# ---------------------------------------------------------------------------


class IronCoreNetwork(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 Network resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "peerings": "peerings",
        "provider_id": "providerID",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "Network"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        provider_id = _get_flat(config, "provider_id", "providerID")
        if provider_id is not None:
            spec["providerID"] = provider_id

        peerings = config.get("peerings")
        if peerings is not None:
            spec["peerings"] = [self._build_peering(p) for p in peerings]

        self.root.spec = spec

    def _build_peering(self, peering: dict) -> dict:
        result = dict(peering)
        result["networkRef"] = _local_object_reference(peering["networkRef"])
        return result


class IronCoreNetworkInterface(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 NetworkInterface resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "network_ref": "networkRef",
        "ip_families": "ipFamilies",
        "ips": "ips",
        "prefixes": "prefixes",
        "virtual_ip": "virtualIP",
        "provider_id": "providerID",
        "attributes": "attributes",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "NetworkInterface"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        network_ref = _get_flat(config, "network_ref", "networkRef")
        if network_ref is not None:
            spec["networkRef"] = _local_object_reference(network_ref)

        ips = config.get("ips")
        if ips is not None:
            spec["ips"] = [_value_source(ip) for ip in ips]

        ip_families = _get_flat(config, "ip_families", "ipFamilies")
        if ip_families is not None:
            spec["ipFamilies"] = ip_families
        elif "ipFamilies" not in spec and spec.get("ips"):
            spec["ipFamilies"] = _ip_families(spec["ips"])

        prefixes = config.get("prefixes")
        if prefixes is not None:
            spec["prefixes"] = [_value_source(p) for p in prefixes]

        virtual_ip = _get_flat(config, "virtual_ip", "virtualIP")
        if virtual_ip is not None:
            spec["virtualIP"] = self._build_virtual_ip_source(virtual_ip)

        provider_id = _get_flat(config, "provider_id", "providerID")
        if provider_id is not None:
            spec["providerID"] = provider_id

        attributes = config.get("attributes")
        if attributes is not None:
            spec["attributes"] = attributes

        self.root.spec = spec

    def _build_virtual_ip_source(self, vip_config: dict) -> dict:
        if "virtualIPRef" in vip_config:
            return {"virtualIPRef": _local_object_reference(vip_config["virtualIPRef"])}
        return vip_config


class IronCoreVirtualIP(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 VirtualIP resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "type": "type",
        "ip_family": "ipFamily",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "VirtualIP"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        vip_type = config.get("type")
        if vip_type is not None:
            _validate_enum(vip_type, VALID_VIP_TYPES, "VirtualIP type")
            spec["type"] = vip_type
        elif "type" not in spec:
            spec["type"] = "Public"

        ip_family = _get_flat(config, "ip_family", "ipFamily")
        if ip_family is not None:
            _validate_enum(ip_family, VALID_IP_FAMILIES, "VirtualIP ipFamily")
            spec["ipFamily"] = ip_family

        self.root.spec = spec


class IronCoreLoadBalancer(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 LoadBalancer resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "type": "type",
        "ip_families": "ipFamilies",
        "network_ref": "networkRef",
        "ips": "ips",
        "network_interface_selector": "networkInterfaceSelector",
        "ports": "ports",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "LoadBalancer"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        lb_type = config.get("type")
        if lb_type is not None:
            _validate_enum(lb_type, VALID_LB_TYPES, "LoadBalancer type")
            spec["type"] = lb_type

        ips = config.get("ips")
        if ips is not None:
            spec["ips"] = [_value_source(ip) for ip in ips]

        ip_families = _get_flat(config, "ip_families", "ipFamilies")
        if ip_families is not None:
            for family in ip_families:
                _validate_enum(family, VALID_IP_FAMILIES, "LoadBalancer ipFamily")
            spec["ipFamilies"] = ip_families
        elif "ipFamilies" not in spec and spec.get("ips"):
            spec["ipFamilies"] = _ip_families(spec["ips"])

        network_ref = _get_flat(config, "network_ref", "networkRef")
        if network_ref is not None:
            spec["networkRef"] = _local_object_reference(network_ref)

        nic_selector = _get_flat(
            config, "network_interface_selector", "networkInterfaceSelector"
        )
        if nic_selector is not None:
            spec["networkInterfaceSelector"] = nic_selector

        ports = config.get("ports")
        if ports is not None:
            spec["ports"] = [self._build_port(p) for p in ports]

        self.root.spec = spec

    def _build_port(self, port_config: dict) -> dict:
        if "protocol" in port_config:
            _validate_enum(port_config["protocol"], VALID_PROTOCOLS, "port protocol")
        return dict(port_config)


class IronCoreNATGateway(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 NATGateway resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "type": "type",
        "ip_family": "ipFamily",
        "network_ref": "networkRef",
        "ports_per_network_interface": "portsPerNetworkInterface",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "NATGateway"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        nat_type = config.get("type")
        if nat_type is not None:
            _validate_enum(nat_type, VALID_NAT_TYPES, "NATGateway type")
            spec["type"] = nat_type
        elif "type" not in spec:
            spec["type"] = "Public"

        ip_family = _get_flat(config, "ip_family", "ipFamily")
        if ip_family is not None:
            _validate_enum(ip_family, VALID_IP_FAMILIES, "NATGateway ipFamily")
            spec["ipFamily"] = ip_family

        network_ref = _get_flat(config, "network_ref", "networkRef")
        if network_ref is not None:
            spec["networkRef"] = _local_object_reference(network_ref)

        ports_per_nic = _get_flat(
            config, "ports_per_network_interface", "portsPerNetworkInterface"
        )
        if ports_per_nic is not None:
            spec["portsPerNetworkInterface"] = ports_per_nic

        self.root.spec = spec


class IronCoreNetworkPolicy(IronCoreBase):
    """Generates a networking.ironcore.dev/v1alpha1 NetworkPolicy resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "network_ref": "networkRef",
        "network_interface_selector": "networkInterfaceSelector",
        "ingress": "ingress",
        "egress": "egress",
        "policy_types": "policyTypes",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "networking.ironcore.dev/v1alpha1"
        self.kwargs.kind = "NetworkPolicy"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        network_ref = _get_flat(config, "network_ref", "networkRef")
        if network_ref is not None:
            spec["networkRef"] = _local_object_reference(network_ref)

        nic_selector = _get_flat(
            config, "network_interface_selector", "networkInterfaceSelector"
        )
        if nic_selector is not None:
            spec["networkInterfaceSelector"] = nic_selector

        ingress = config.get("ingress")
        if ingress is not None:
            spec["ingress"] = ingress

        egress = config.get("egress")
        if egress is not None:
            spec["egress"] = egress

        policy_types = _get_flat(config, "policy_types", "policyTypes")
        if policy_types is not None:
            for pt in policy_types:
                _validate_enum(pt, VALID_POLICY_TYPES, "policyType")
            spec["policyTypes"] = policy_types

        self.root.spec = spec


# ---------------------------------------------------------------------------
# storage.ironcore.dev/v1alpha1
# ---------------------------------------------------------------------------


class IronCoreVolume(IronCoreBase):
    """Generates a storage.ironcore.dev/v1alpha1 Volume resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "volume_class_ref": "volumeClassRef",
        "volume_pool_ref": "volumePoolRef",
        "volume_pool_selector": "volumePoolSelector",
        "resources": "resources",
        "data_source": "dataSource",
        "encryption": "encryption",
        "unclaimable": "unclaimable",
        "tolerations": "tolerations",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "storage.ironcore.dev/v1alpha1"
        self.kwargs.kind = "Volume"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        volume_class_ref = _get_flat(config, "volume_class_ref", "volumeClassRef")
        if volume_class_ref is not None:
            spec["volumeClassRef"] = _local_object_reference(volume_class_ref)

        volume_pool_ref = _get_flat(config, "volume_pool_ref", "volumePoolRef")
        if volume_pool_ref is not None:
            spec["volumePoolRef"] = _local_object_reference(volume_pool_ref)

        pool_selector = _get_flat(config, "volume_pool_selector", "volumePoolSelector")
        if pool_selector is not None:
            spec["volumePoolSelector"] = pool_selector

        resources = config.get("resources")
        if resources is not None:
            spec["resources"] = resources

        data_source = _get_flat(config, "data_source", "dataSource")
        if data_source is not None:
            spec["dataSource"] = self._build_data_source(data_source)

        encryption = config.get("encryption")
        if encryption is not None:
            if isinstance(encryption, str):
                spec["encryption"] = {"secretRef": _local_object_reference(encryption)}
            elif "secretRef" in encryption:
                spec["encryption"] = {"secretRef": _local_object_reference(encryption["secretRef"])}
            else:
                spec["encryption"] = _convert_to_dict(encryption)

        if config.get("unclaimable"):
            spec["unclaimable"] = True

        tolerations = config.get("tolerations")
        if tolerations is not None:
            spec["tolerations"] = tolerations

        self.root.spec = spec

    def _build_data_source(self, data_source: dict) -> dict:
        result: dict = {}
        snapshot_ref = data_source.get("volumeSnapshotRef")
        if snapshot_ref:
            result["volumeSnapshotRef"] = _local_object_reference(snapshot_ref)
        os_image = data_source.get("osImage")
        if os_image:
            # OSDataSource is an object; a plain string is shorthand for image
            if isinstance(os_image, str):
                os_image = {"image": os_image}
            result["osImage"] = os_image
        return result


# ---------------------------------------------------------------------------
# compute.ironcore.dev/v1alpha1
# ---------------------------------------------------------------------------


class IronCoreMachine(IronCoreBase):
    """Generates a compute.ironcore.dev/v1alpha1 Machine resource.

    Required kwargs: name, config
    """

    _FIELD_MAP = {
        "machine_class_ref": "machineClassRef",
        "machine_pool_ref": "machinePoolRef",
        "machine_pool_selector": "machinePoolSelector",
        "power": "power",
        "network_interfaces": "networkInterfaces",
        "volumes": "volumes",
        "ignition_ref": "ignitionRef",
        "efi_vars": "efiVars",
        "tolerations": "tolerations",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "compute.ironcore.dev/v1alpha1"
        self.kwargs.kind = "Machine"
        super().new()

    def body(self) -> None:
        super().body()
        config: dict = _convert_to_dict(self.kwargs.config)
        self._add_common_metadata(config)

        spec: dict = {}
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FIELD_MAP, self.name)

        machine_class_ref = _get_flat(config, "machine_class_ref", "machineClassRef")
        if machine_class_ref is not None:
            spec["machineClassRef"] = _local_object_reference(machine_class_ref)

        pool_ref = _get_flat(config, "machine_pool_ref", "machinePoolRef")
        if pool_ref is not None:
            spec["machinePoolRef"] = _local_object_reference(pool_ref)

        pool_selector = _get_flat(
            config, "machine_pool_selector", "machinePoolSelector"
        )
        if pool_selector is not None:
            spec["machinePoolSelector"] = pool_selector

        power = config.get("power")
        if power is not None:
            # YAML 1.1 parses bare On/Off as booleans — convert back to strings
            if isinstance(power, bool):
                power = "On" if power else "Off"
            _validate_enum(power, VALID_POWER_STATES, "Machine power")
            spec["power"] = power

        nics = _get_flat(config, "network_interfaces", "networkInterfaces")
        if nics is not None:
            spec["networkInterfaces"] = [self._build_nic_attachment(n) for n in nics]

        volumes = config.get("volumes")
        if volumes is not None:
            spec["volumes"] = [self._build_volume_attachment(v) for v in volumes]

        ignition_ref = _get_flat(config, "ignition_ref", "ignitionRef")
        if ignition_ref is not None:
            spec["ignitionRef"] = _local_object_reference(ignition_ref)

        efi_vars = _get_flat(config, "efi_vars", "efiVars")
        if efi_vars is not None:
            spec["efiVars"] = efi_vars

        tolerations = config.get("tolerations")
        if tolerations is not None:
            spec["tolerations"] = tolerations

        self.root.spec = spec

    def _build_nic_attachment(self, nic: dict) -> dict:
        result = dict(nic)
        if "networkInterfaceRef" in nic:
            result["networkInterfaceRef"] = _local_object_reference(nic["networkInterfaceRef"])
        return result

    def _build_volume_attachment(self, volume: dict) -> dict:
        result = dict(volume)
        if "volumeRef" in volume:
            result["volumeRef"] = _local_object_reference(volume["volumeRef"])
        return result


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def main(input_params: dict) -> BaseObj:
    """Kapitan kadet entry point.

    Reads ironcore config from ``generators.ironcore`` inventory and produces
    Kubernetes resources.

    Inventory schema:
        parameters:
          generators:
            ironcore:
              namespace: default
              networks: {}
              network_interfaces: {}
              virtual_ips: {}
              volumes: {}
              machines: {}
              load_balancers: {}
              nat_gateways: {}
              network_policies: {}
    """
    obj = BaseObj()

    ironcore_config: dict = _convert_to_dict(
        inv.parameters.get("generators", {}).get("ironcore", {}) or {}
    )
    namespace: str = ironcore_config.get("namespace") or inv.parameters.get(
        "namespace", "default"
    )

    def _inject_namespace(config: dict) -> dict:
        """Inject top-level namespace into resource config if not overridden."""
        if "namespace" not in config:
            config = dict(config)
            config["namespace"] = namespace
        return config

    # Networks
    for name, config in ironcore_config.get("networks", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-network"] = IronCoreNetwork(
            name=name, config=config
        )

    # NetworkInterfaces
    for name, config in ironcore_config.get("network_interfaces", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-nic"] = IronCoreNetworkInterface(
            name=name, config=config
        )

    # VirtualIPs
    for name, config in ironcore_config.get("virtual_ips", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-vip"] = IronCoreVirtualIP(
            name=name, config=config
        )

    # Volumes
    for name, config in ironcore_config.get("volumes", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-volume"] = IronCoreVolume(
            name=name, config=config
        )

    # Machines
    for name, config in ironcore_config.get("machines", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-machine"] = IronCoreMachine(
            name=name, config=config
        )

    # LoadBalancers
    for name, config in ironcore_config.get("load_balancers", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-lb"] = IronCoreLoadBalancer(
            name=name, config=config
        )

    # NATGateways
    for name, config in ironcore_config.get("nat_gateways", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-natgw"] = IronCoreNATGateway(
            name=name, config=config
        )

    # NetworkPolicies
    for name, config in ironcore_config.get("network_policies", {}).items():
        config = _inject_namespace(config)
        obj.root[f"{config['namespace']}/{name}-netpol"] = IronCoreNetworkPolicy(
            name=name, config=config
        )

    return obj
