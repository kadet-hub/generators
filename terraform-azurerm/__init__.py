"""Terraform JSON for Azure (hashicorp/azurerm): network and storage bundles.

Reads parameters.generators.terraform-azurerm; see README.md for the
inventory contract.
"""

import ipaddress
import re

from kapitan.inputs.kadet import BaseObj, inventory

PROVIDER_VERSION = "5.10.0"

# azurerm_network_security_group.security_rule is an attribute in JSON
# syntax, so every rule needs every key; absent ones are sent as null.
RULE_KEYS = (
    "name",
    "description",
    "priority",
    "direction",
    "access",
    "protocol",
    "source_port_range",
    "source_port_ranges",
    "destination_port_range",
    "destination_port_ranges",
    "source_address_prefix",
    "source_address_prefixes",
    "source_application_security_group_ids",
    "destination_address_prefix",
    "destination_address_prefixes",
    "destination_application_security_group_ids",
)
RULE_REQUIRED = ("name", "priority", "direction", "access", "protocol")
SMALLEST_SUBNET = 29
RFC1918 = tuple(ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _get(spec, key, default):
    value = spec.get(key)
    return default if value is None else value


def _require(spec, key, where):
    if not spec.get(key):
        raise ValueError(f"{where}: {key} is required")
    return spec[key]


def _tf_name(key, where, prefix=""):
    """Terraform resource name: the inventory key in [a-z0-9_], behind prefix."""
    name = prefix + re.sub(r"[^a-z0-9_]", "_", str(key).lower())
    if not re.match(r"[a-z_]", name):
        raise ValueError(f"{where}: {key!r} must start with a letter")
    return name


def _put(seen, doc, rtype, name, body):
    if (rtype, name) in seen:
        raise ValueError(f"{rtype}.{name} is derived twice: inventory names collide after mapping to [a-z0-9_]")
    seen.add((rtype, name))
    doc.setdefault("resource", {}).setdefault(rtype, {})[name] = body


def _suffix(spec, where):
    """<workload>-<environment>-<location_short>-<instance> (Cloud Adoption Framework)."""
    workload, environment, location = (
        str(_require(spec, key, where)) for key in ("workload", "environment", "location")
    )
    location_short = str(_get(spec, "location_short", location))
    return f"{workload}-{environment}-{location_short}-{_get(spec, 'instance', '001')}"


def _block(prefix, space, taken, where):
    try:
        block = ipaddress.IPv4Network(str(prefix))
    except ValueError as err:
        raise ValueError(f"{where}: prefix must be an IPv4 CIDR: {err}") from None
    if block.prefixlen > SMALLEST_SUBNET:
        raise ValueError(f"{where}: {block} is smaller than /{SMALLEST_SUBNET}, the smallest subnet Azure allows")
    if not block.subnet_of(space):
        raise ValueError(f"{where}: {block} is outside address_space {space}")
    for other, used in taken.items():
        if block.overlaps(used):
            raise ValueError(f"{where}: {block} overlaps subnet {other} ({used})")
    return block


def _allocate(space, subnets, where):
    """Explicit prefixes first, then per subnet in inventory order the first free aligned block."""
    taken = {}
    for name, sub in subnets.items():
        if (sub or {}).get("prefix") is not None:
            taken[name] = _block(sub["prefix"], space, taken, f"{where} subnet {name}")
    for name, sub in subnets.items():
        if name in taken:
            continue
        swhere = f"{where} subnet {name}"
        newbits = (sub or {}).get("newbits")
        if not isinstance(newbits, int) or newbits < 1:
            raise ValueError(f"{swhere}: newbits (a positive integer) or prefix is required")
        size = space.prefixlen + newbits
        if size > SMALLEST_SUBNET:
            raise ValueError(f"{swhere}: /{size} is smaller than /{SMALLEST_SUBNET}, the smallest subnet Azure allows")
        free = (b for b in space.subnets(new_prefix=size) if not any(b.overlaps(t) for t in taken.values()))
        taken[name] = next(free, None)
        if taken[name] is None:
            raise ValueError(f"{swhere}: no free /{size} left in {space}")
    return taken


def _rule(rule, where):
    missing = [key for key in RULE_REQUIRED if rule.get(key) is None]
    if missing:
        raise ValueError(f"{where}: security rule {rule.get('name')!r} misses {', '.join(missing)}")
    unknown = sorted(set(rule) - set(RULE_KEYS))
    if unknown:
        raise ValueError(f"{where}: security rule {rule['name']!r} has unknown keys {', '.join(unknown)}")
    return {key: rule.get(key) for key in RULE_KEYS}


def _ip_rule(rule, where):
    """A public IPv4 address, or a CIDR up to /30 (the storage firewall rejects /31 and /32)."""
    text = str(rule)
    try:
        net = ipaddress.IPv4Network(text)
    except ValueError as err:
        raise ValueError(f"{where}: ip_rules entry {text} must be an IPv4 address or CIDR: {err}") from None
    if "/" in text and net.prefixlen > 30:
        raise ValueError(f"{where}: ip_rules entry {text}: /31 and /32 are not allowed, give a single address without prefix")
    if any(net.overlaps(private) for private in RFC1918):
        raise ValueError(f"{where}: ip_rules entry {text} includes RFC 1918 private addresses")
    return text


def _network(key, spec, seen, storage_subnets):
    where = f"network {key}"
    net = _tf_name(key, where)
    suffix = _suffix(spec, where)
    location, tags = spec["location"], _get(spec, "tags", {})
    try:
        space = ipaddress.IPv4Network(str(_require(spec, "address_space", where)))
    except ValueError as err:
        raise ValueError(f"{where}: address_space must be one IPv4 CIDR: {err}") from None
    subnets = _require(spec, "subnets", where)
    prefixes = _allocate(space, subnets, where)
    rg = f"${{azurerm_resource_group.{net}.name}}"
    doc = {}
    _put(seen, doc, "azurerm_resource_group", net, {"name": f"rg-{suffix}", "location": location, "tags": tags})
    _put(seen, doc, "azurerm_virtual_network", net, {
        "name": f"vnet-{suffix}",
        "resource_group_name": rg,
        "location": location,
        "address_space": [str(space)],
        "tags": tags,
    })
    subnet_ids = {}
    for name in sorted(subnets):
        sub, swhere = subnets[name] or {}, f"{where} subnet {name}"
        sn = _tf_name(name, swhere, f"{net}_")
        subnet = {
            "name": f"snet-{name}-{suffix}",
            "resource_group_name": rg,
            "virtual_network_name": f"${{azurerm_virtual_network.{net}.name}}",
            "address_prefixes": [str(prefixes[name])],
            "default_outbound_access_enabled": _get(sub, "default_outbound_access_enabled", False),
            "private_endpoint_network_policies": _get(sub, "private_endpoint_network_policies", "Enabled"),
        }
        if name in storage_subnets:
            subnet["service_endpoint"] = [{"service": "Microsoft.Storage"}]
        _put(seen, doc, "azurerm_subnet", sn, subnet)
        subnet_ids[name] = f"${{azurerm_subnet.{sn}.id}}"
        rules = _get(sub, "security_rules", [])
        if not _get(sub, "nsg", True):
            if rules:
                raise ValueError(f"{swhere}: security_rules need nsg: true")
            continue
        _put(seen, doc, "azurerm_network_security_group", sn, {
            "name": f"nsg-{name}-{suffix}",
            "resource_group_name": rg,
            "location": location,
            "security_rule": [_rule(rule, swhere) for rule in rules],
            "tags": tags,
        })
        _put(seen, doc, "azurerm_subnet_network_security_group_association", sn, {
            "subnet_id": f"${{azurerm_subnet.{sn}.id}}",
            "network_security_group_id": f"${{azurerm_network_security_group.{sn}.id}}",
        })
    doc["output"] = {
        f"{net}_resource_group_name": {"value": rg},
        f"{net}_virtual_network_id": {"value": f"${{azurerm_virtual_network.{net}.id}}"},
        f"{net}_subnet_ids": {"value": subnet_ids},
    }
    return net, subnet_ids, doc


def _storage(key, spec, networks, seen):
    where = f"storage {key}"
    st = _tf_name(key, where)
    name = re.sub(r"[^a-z0-9]", "", f"st{_suffix(spec, where)}".lower())
    if not 3 <= len(name) <= 24:
        raise ValueError(
            f"{where}: storage account name {name} has {len(name)} characters, Azure allows 3 to 24;"
            " shorten workload, environment, location_short or instance"
        )
    if ("storage account", name) in seen:
        raise ValueError(f"{where}: storage account name {name} is already derived for another entry")
    seen.add(("storage account", name))
    network, rg = spec.get("resource_group"), spec.get("resource_group_name")
    allowed, subnet_ids = _get(spec, "allowed_subnets", []), []
    if (network is None) == (rg is None):
        raise ValueError(f"{where}: set exactly one of resource_group (a network key) or resource_group_name")
    if network is None and allowed:
        raise ValueError(f"{where}: allowed_subnets needs resource_group (a network key), not resource_group_name")
    if network is not None:
        if network not in networks:
            raise ValueError(f"{where}: resource_group {network!r} is not a key under network")
        net, ids = networks[network]
        rg = f"${{azurerm_resource_group.{net}.name}}"
        unknown = [str(name) for name in allowed if name not in ids]
        if unknown:
            raise ValueError(f"{where}: allowed_subnets {', '.join(unknown)} are not subnets of network {network}")
        subnet_ids = [ids[name] for name in allowed]
    doc = {}
    _put(seen, doc, "azurerm_storage_account", st, {
        "name": name,
        "resource_group_name": rg,
        "location": spec["location"],
        "account_tier": "Standard",
        "account_kind": "StorageV2",
        "account_replication_type": _get(spec, "account_replication_type", "ZRS"),
        "https_traffic_only_enabled": True,
        "min_tls_version": "TLS1_2",
        "allow_nested_items_to_be_public": False,
        "shared_access_key_enabled": _get(spec, "shared_access_key_enabled", False),
        "default_to_oauth_authentication": True,
        "cross_tenant_replication_enabled": False,
        "local_user_enabled": False,
        "public_network_access": _get(spec, "public_network_access", "Disabled"),
        "infrastructure_encryption_enabled": _get(spec, "infrastructure_encryption_enabled", False),
        "network_rules": {
            "default_action": "Deny",
            "bypass": ["AzureServices"],
            "ip_rules": [_ip_rule(rule, where) for rule in _get(spec, "ip_rules", [])],
            "virtual_network_subnet_ids": subnet_ids,
        },
        "blob_properties": {
            "versioning_enabled": _get(spec, "versioning_enabled", True),
            "delete_retention_policy": {"days": _get(spec, "delete_retention_days", 7)},
            "container_delete_retention_policy": {"days": _get(spec, "container_delete_retention_days", 7)},
        },
        "tags": _get(spec, "tags", {}),
    })
    for container in sorted(_get(spec, "containers", [])):
        _put(seen, doc, "azurerm_storage_container", _tf_name(container, where, f"{st}_"), {
            "name": container,
            "storage_account_id": f"${{azurerm_storage_account.{st}.id}}",
            "container_access_type": "private",
        })
    doc["output"] = {
        f"{st}_storage_account_id": {"value": f"${{azurerm_storage_account.{st}.id}}"},
        f"{st}_storage_account_name": {"value": f"${{azurerm_storage_account.{st}.name}}"},
    }
    return st, doc


def main(input_params=None):
    config = (inventory().parameters.get("generators") or {}).get("terraform-azurerm") or {}
    networks, storage = _get(config, "network", {}), _get(config, "storage", {})
    endpoints = {}
    for spec in storage.values():
        endpoints.setdefault((spec or {}).get("resource_group"), set()).update(_get(spec or {}, "allowed_subnets", []))
    out, seen, names = BaseObj(), set(), {}
    for key in sorted(networks):
        net, subnet_ids, doc = _network(key, networks[key] or {}, seen, endpoints.get(key, set()))
        names[key] = net, subnet_ids
        out.root[f"network-{net}.tf"] = doc
    for key in sorted(storage):
        st, doc = _storage(key, storage[key] or {}, names, seen)
        out.root[f"storage-{st}.tf"] = doc
    provider = {"features": {}}
    if any(not _get(spec or {}, "shared_access_key_enabled", False) for spec in storage.values()):
        provider["storage_use_azuread"] = True
    out.root["providers.tf"] = {
        "terraform": {
            "required_version": ">= 1.5.0",
            "required_providers": {"azurerm": {"source": "hashicorp/azurerm", "version": PROVIDER_VERSION}},
        },
        "provider": {"azurerm": provider},
    }
    return out
