"""Terraform JSON for Open Telekom Cloud: VPC networks with NAT egress and
KMS-encrypted OBS buckets. See README.md for the inventory contract.
"""

import ipaddress
import itertools
import json
import re

from kapitan.inputs.kadet import BaseObj, inventory

NAME = "terraform-opentelekomcloud"
PROVIDER = {"source": "opentelekomcloud/opentelekomcloud", "version": "1.37.10"}
AUTH_URL = "https://iam.eu-de.otc.t-systems.com/v3"
DNS = ["100.125.4.25", "100.125.129.199"]
NAT_SPECS = ("0", "1", "2", "3", "4")
BUCKET_NAME = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")
LIFECYCLE = {
    "noncurrent_expiration_days": ("noncurrent_version_expiration", 90),
    "abort_multipart_days": ("abort_incomplete_multipart_upload", 7),
}


def _fail(where, message):
    raise ValueError(f"{NAME}: {where}: {message}")


def _ident(key):
    name = re.sub(r"[^a-z0-9_]", "_", str(key).lower())
    return name if re.match(r"[a-z_]", name) else f"_{name}"


def _put(doc, seen, origin, path, body):
    if path in seen:
        _fail(origin, f"{'.'.join(path)} is already used by {seen[path]}; rename one of them")
    seen[path] = origin
    node = doc
    for part in path[:-1]:
        node = node.setdefault(part, {})
    node[path[-1]] = body


def _cidr(value, where):
    try:
        return ipaddress.IPv4Network(value)
    except ValueError as err:
        _fail(where, err)


def _subnet_cidrs(vpc, subnets, origin):
    cidrs = {}
    for position, key in enumerate(sorted(subnets)):
        spec, where = subnets[key] or {}, f"{origin}.subnets.{key}"
        if spec.get("cidr"):
            cidr = _cidr(spec["cidr"], where)
            if not cidr.subnet_of(vpc) or cidr.prefixlen > 28:
                _fail(where, f"{cidr} must lie inside {vpc} and be /28 or shorter")
        else:
            newbits = spec.get("newbits", 8)
            prefix = vpc.prefixlen + newbits
            if newbits < 0 or prefix > 28:
                _fail(where, f"newbits {newbits} gives /{prefix}, allowed is /{vpc.prefixlen} to /28")
            index = spec.get("index", position)
            if not 0 <= index < 2**newbits:
                _fail(where, f"index {index} does not fit, {vpc} holds {2**newbits} /{prefix} subnets")
            start = int(vpc.network_address) + index * 2 ** (32 - prefix)
            cidr = ipaddress.IPv4Network((start, prefix))
        cidrs[key] = cidr
    for (a, ca), (b, cb) in itertools.combinations(cidrs.items(), 2):
        if ca.overlaps(cb):
            _fail(origin, f"subnets {a} ({ca}) and {b} ({cb}) overlap")
    return cidrs


def _network(doc, seen, net, key, spec):
    origin = f"network.{key}"
    if not spec.get("cidr"):
        _fail(origin, "cidr is required")
    if not spec.get("subnets"):
        _fail(origin, "subnets needs at least one entry")
    vpc = _cidr(spec["cidr"], f"{origin}.cidr")
    subnets = spec["subnets"]
    cidrs = _subnet_cidrs(vpc, subnets, origin)
    tags = {str(k): str(v) for k, v in (spec.get("tags") or {}).items()}
    dns = [str(d) for d in spec.get("dns", DNS)]
    vpc_id = f"${{opentelekomcloud_vpc_v1.{net}.id}}"

    _put(doc, seen, origin, ("resource", "opentelekomcloud_vpc_v1", net),
         {"name": str(key), "cidr": str(vpc), "tags": tags})
    subnet_ids = {}
    for sub, cidr in cidrs.items():
        name = _ident(f"{key}_{sub}")
        body = {
            "name": f"{key}-{sub}",
            "cidr": str(cidr),
            "gateway_ip": str(cidr.network_address + 1),
            "vpc_id": vpc_id,
            "dhcp_enable": True,
            "tags": tags,
        }
        body.update(zip(("primary_dns", "secondary_dns"), dns))
        if len(dns) > 2:
            body["dns_list"] = dns
        _put(doc, seen, f"{origin}.subnets.{sub}", ("resource", "opentelekomcloud_vpc_subnet_v1", name), body)
        subnet_ids[sub] = f"${{opentelekomcloud_vpc_subnet_v1.{name}.id}}"
    _put(doc, seen, origin, ("output", f"{net}_vpc_id"), {"value": vpc_id})
    _put(doc, seen, origin, ("output", f"{net}_subnet_ids"), {"value": subnet_ids})

    nat = {"enabled": True, "spec": "0", "bandwidth_mbit": 100, "subnet": min(subnets), **(spec.get("nat") or {})}
    if not nat["enabled"]:
        return
    if str(nat["spec"]) not in NAT_SPECS:
        _fail(f"{origin}.nat.spec", f"{nat['spec']!r} is not one of {', '.join(NAT_SPECS)}")
    bandwidth = nat["bandwidth_mbit"]
    if not isinstance(bandwidth, int) or not 1 <= bandwidth <= 300:
        _fail(f"{origin}.nat.bandwidth_mbit", f"{bandwidth!r} is outside 1..300")
    if nat["subnet"] not in subnets:
        _fail(f"{origin}.nat.subnet", f"{nat['subnet']!r} is not one of the subnets")

    nat_id = f"${{opentelekomcloud_nat_gateway_v2.{net}.id}}"
    eip = f"opentelekomcloud_vpc_eip_v1.{net}_nat"
    _put(doc, seen, f"{origin}.nat", ("resource", "opentelekomcloud_nat_gateway_v2", net), {
        "name": f"{key}-nat",
        "spec": str(nat["spec"]),
        "router_id": vpc_id,
        "internal_network_id": subnet_ids[nat["subnet"]],
        "tags": tags,
    })
    _put(doc, seen, f"{origin}.nat", ("resource", "opentelekomcloud_vpc_eip_v1", f"{net}_nat"), {
        "publicip": {"type": "5_bgp", "name": f"{key}-nat"},
        "bandwidth": {"name": f"{key}-nat", "size": bandwidth, "share_type": "PER"},
        "tags": tags,
    })
    for sub in cidrs:
        if (subnets[sub] or {}).get("egress", True):
            _put(doc, seen, f"{origin}.subnets.{sub}", ("resource", "opentelekomcloud_nat_snat_rule_v2", _ident(f"{key}_{sub}")), {
                "nat_gateway_id": nat_id,
                "floating_ip_id": f"${{{eip}.id}}",
                "network_id": subnet_ids[sub],
                "source_type": 0,
            })
    _put(doc, seen, origin, ("output", f"{net}_eip_address"), {"value": f"${{{eip}.publicip[0].ip_address}}"})


def _bucket(doc, seen, ident, key, spec):
    origin = f"bucket.{key}"
    name = str(spec.get("bucket", key))
    if (not BUCKET_NAME.fullmatch(name) or any(s in name for s in ("..", ".-", "-."))
            or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", name)):
        _fail(f"{origin}.bucket", f"{name!r} is not a valid OBS bucket name: 3-63 lowercase letters, digits, "
              "'-' and '.', starting and ending with a letter or digit, no '..', '.-' or '-.', not an IP address")
    tags = {str(k): str(v) for k, v in (spec.get("tags") or {}).items()}
    kms = {"create_key": True, "pending_days": 7, "key_id": None, **(spec.get("kms") or {})}

    sse = {"algorithm": "kms"}
    if kms["key_id"]:
        sse["kms_key_id"] = str(kms["key_id"])
    elif kms["create_key"]:
        days = kms["pending_days"]
        if not isinstance(days, int) or not 7 <= days <= 1096:
            _fail(f"{origin}.kms.pending_days", f"{days!r} is outside 7..1096")
        _put(doc, seen, f"{origin}.kms", ("resource", "opentelekomcloud_kms_key_v1", ident), {
            "key_alias": f"{name.replace('.', '-')}-obs",
            "key_description": f"OBS server-side encryption for bucket {name}",
            "pending_days": str(days),
            "is_enabled": True,
            "tags": tags,
        })
        sse["kms_key_id"] = f"${{opentelekomcloud_kms_key_v1.{ident}.id}}"

    body = {
        "bucket": name,
        "acl": "private",
        "versioning": spec.get("versioning", True),
        "force_destroy": spec.get("force_destroy", False),
        "server_side_encryption": sse,
        "tags": tags,
    }
    rule = {"name": "default", "enabled": True}
    for field, (block, default) in LIFECYCLE.items():
        days = spec.get(field, default)
        if days is None:
            continue
        if not isinstance(days, int) or days < 1:
            _fail(f"{origin}.{field}", f"{days!r} must be a positive number of days or null")
        rule[block] = {"days": days}
    if len(rule) > 2:
        body["lifecycle_rule"] = rule
    _put(doc, seen, origin, ("resource", "opentelekomcloud_obs_bucket", ident), body)
    _put(doc, seen, origin, ("output", f"{ident}_bucket_name"), {"value": f"${{opentelekomcloud_obs_bucket.{ident}.bucket}}"})
    if "kms_key_id" in sse:
        _put(doc, seen, origin, ("output", f"{ident}_kms_key_id"), {"value": sse["kms_key_id"]})


def main(input_params=None):
    config = json.loads(json.dumps(inventory().parameters.get("generators", {}).get(NAME) or {}))
    if not config.get("tenant_name"):
        _fail("tenant_name", "is required, e.g. eu-de_myproject")
    tenant = str(config["tenant_name"])
    provider = {"auth_url": config.get("auth_url", AUTH_URL), "tenant_name": tenant}
    if config.get("region"):
        provider["region"] = config["region"]

    files, seen = {}, {}
    for kind, render in (("network", _network), ("bucket", _bucket)):
        entries = config.get(kind) or {}
        for key in sorted(entries):
            doc, ident = {}, _ident(key)
            render(doc, seen, ident, key, entries[key] or {})
            files[f"{kind}-{ident}.tf"] = doc

    # OBS accepts only keys of the base project, so a sub-project tenant creates them there.
    providers = [provider]
    keys = [k for doc in files.values() for k in doc.get("resource", {}).get("opentelekomcloud_kms_key_v1", {}).values()]
    if keys and "_" in tenant:
        providers.append({**provider, "alias": "base", "tenant_name": tenant.split("_", 1)[0]})
        for key in keys:
            key["provider"] = "opentelekomcloud.base"

    out = BaseObj()
    out.root["providers.tf"] = {
        "terraform": {"required_version": ">= 1.5.0", "required_providers": {"opentelekomcloud": PROVIDER}},
        "provider": {"opentelekomcloud": providers},
    }
    for name, doc in files.items():
        out.root[name] = doc
    return out
