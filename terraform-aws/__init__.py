"""Terraform AWS generator: VPC and S3 bucket bundles as Terraform JSON.

Reads parameters.generators.terraform-aws; see README.md for the contract.
"""

import ipaddress
import json
import re

from kapitan.inputs.kadet import BaseObj, inventory

PROVIDER = {"source": "hashicorp/aws", "version": "6.69.1"}
NAT_MODES = ("none", "single", "per_az", "regional")

VPC_DEFAULTS = {
    "subnet_newbits": 8,
    "public_offset": 0,
    "private_offset": 100,
    "public_subnets": True,
    "nat": "none",
    "enable_dns_hostnames": True,
    "enable_dns_support": True,
    "lock_default_sg": True,
    "tags": {},
}
BUCKET_DEFAULTS = {
    "versioning": True,
    "kms_key_arn": None,
    "deny_insecure_transport": True,
    "force_destroy": False,
    "tags": {},
}


def _spec(kind, key, raw, required, defaults):
    """Inventory entry merged over defaults, after checking keys and types."""
    where = f"terraform-aws {kind} '{key}'"
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", key):
        raise ValueError(f"{where}: key must match [a-z][a-z0-9_-]*")
    raw = dict(raw or {})
    missing = [k for k in required if raw.get(k) in (None, "", [])]
    if missing:
        raise ValueError(f"{where}: missing required {', '.join(missing)}")
    unknown = sorted(set(raw) - set(required) - set(defaults))
    if unknown:
        raise ValueError(f"{where}: unknown keys {', '.join(unknown)}")
    for k, default in defaults.items():
        if default is not None and k in raw and not isinstance(raw[k], type(default)):
            raise ValueError(f"{where}: {k} must be a {type(default).__name__}")
    return {**defaults, **raw}


def _put(seen, doc, address, body):
    """Store body at doc[address...]; one Terraform address may exist only once."""
    if address in seen:
        raise ValueError(
            f"terraform-aws: {'.'.join(address[1:])} would be generated twice; "
            "rename one of the inventory keys"
        )
    seen.add(address)
    node = doc
    for part in address[:-1]:
        node = node.setdefault(part, {})
    node[address[-1]] = body


def _vpc(key, raw, seen):
    s = _spec("vpc", key, raw, ("cidr", "azs"), VPC_DEFAULTS)
    where = f"terraform-aws vpc '{key}'"
    n = key.replace("-", "_")
    nat, public = s["nat"], s["public_subnets"]
    if not isinstance(s["azs"], list):
        raise ValueError(f"{where}: azs must be a list of availability zone names")
    azs = [str(az) for az in s["azs"]]
    if nat not in NAT_MODES:
        raise ValueError(f"{where}: nat must be one of {', '.join(NAT_MODES)}")
    if nat in ("single", "per_az") and not public:
        raise ValueError(f"{where}: nat {nat} needs public_subnets: true (or use nat: regional)")

    try:
        net = ipaddress.IPv4Network(str(s["cidr"]))
    except ValueError as exc:
        raise ValueError(f"{where}: cidr is not an IPv4 network: {exc}") from None
    if not 16 <= net.prefixlen <= 28:
        raise ValueError(f"{where}: AWS allows VPC CIDRs from /16 to /28, got {net}")
    prefix = net.prefixlen + s["subnet_newbits"]
    if not net.prefixlen < prefix <= 28:
        raise ValueError(f"{where}: subnet_newbits gives /{prefix}, it must give /{net.prefixlen + 1} to /28")
    count = 2 ** (prefix - net.prefixlen)
    offsets = {"public": s["public_offset"]} if public else {}
    offsets["private"] = s["private_offset"]
    for tier, offset in offsets.items():
        if offset < 0 or offset + len(azs) > count:
            raise ValueError(
                f"{where}: {tier} subnets {offset}..{offset + len(azs) - 1} do not fit, "
                f"{net} has {count} /{prefix} subnets"
            )
    if public and abs(s["public_offset"] - s["private_offset"]) < len(azs):
        raise ValueError(f"{where}: public and private subnet CIDRs overlap; move private_offset")

    doc = {}

    def add(rtype, name, body):
        _put(seen, doc, ("resource", rtype, name), body)
        return f"${{{rtype}.{name}.id}}"

    def tags(name, **extra):
        return {**s["tags"], "Name": name, **extra}

    vpc_id = add("aws_vpc", n, {
        "cidr_block": str(net),
        "enable_dns_hostnames": s["enable_dns_hostnames"],
        "enable_dns_support": s["enable_dns_support"],
        "tags": tags(key),
    })
    # A regional NAT gateway routes through the VPC's internet gateway without public subnets.
    igw = f"aws_internet_gateway.{n}"
    if public or nat == "regional":
        add("aws_internet_gateway", n, {"vpc_id": vpc_id, "tags": tags(key)})

    size = 2 ** (32 - prefix)
    subnets = {"public": []}
    for tier, offset in offsets.items():
        subnets[tier] = [
            add("aws_subnet", f"{n}_{tier}_{i}", {
                "vpc_id": vpc_id,
                "availability_zone": az,
                "cidr_block": str(ipaddress.IPv4Network((int(net.network_address) + (offset + i) * size, prefix))),
                "map_public_ip_on_launch": False,
                "tags": tags(f"{key}-{tier}-{az}", Tier=tier),
            })
            for i, az in enumerate(azs)
        ]

    if public:
        table = add("aws_route_table", f"{n}_public", {"vpc_id": vpc_id, "tags": tags(f"{key}-public")})
        add("aws_route", f"{n}_public_internet", {
            "route_table_id": table,
            "destination_cidr_block": "0.0.0.0/0",
            "gateway_id": f"${{{igw}.id}}",
        })
        for i, subnet in enumerate(subnets["public"]):
            add("aws_route_table_association", f"{n}_public_{i}", {"subnet_id": subnet, "route_table_id": table})

    nats = []
    if nat == "regional":
        nats.append(add("aws_nat_gateway", f"{n}_regional", {
            "availability_mode": "regional",
            "connectivity_type": "public",
            "vpc_id": vpc_id,
            "tags": tags(key),
            "depends_on": [igw],
        }))
    elif nat != "none":
        for i, az in enumerate(azs[:1] if nat == "single" else azs):
            eip = add("aws_eip", f"{n}_nat_{i}", {"domain": "vpc", "tags": tags(f"{key}-{az}"), "depends_on": [igw]})
            nats.append(add("aws_nat_gateway", f"{n}_{i}", {
                "allocation_id": eip,
                "subnet_id": subnets["public"][i],
                "tags": tags(f"{key}-{az}"),
                "depends_on": [igw],
            }))

    groups = [(f"_{i}", f"-{az}") for i, az in enumerate(azs)] if nat == "per_az" else [("", "")]
    tables = []
    for j, (suffix, label) in enumerate(groups):
        table = add("aws_route_table", f"{n}_private{suffix}", {"vpc_id": vpc_id, "tags": tags(f"{key}-private{label}")})
        if nats:
            add("aws_route", f"{n}_private_nat{suffix}", {
                "route_table_id": table,
                "destination_cidr_block": "0.0.0.0/0",
                "nat_gateway_id": nats[j],
            })
        tables.append(table)
    for i, subnet in enumerate(subnets["private"]):
        add("aws_route_table_association", f"{n}_private_{i}", {
            "subnet_id": subnet,
            "route_table_id": tables[i if nat == "per_az" else 0],
        })

    if s["lock_default_sg"]:
        add("aws_default_security_group", n, {"vpc_id": vpc_id, "tags": tags(f"{key}-default")})

    for name, value in (("vpc_id", vpc_id), ("public_subnet_ids", subnets["public"]),
                        ("private_subnet_ids", subnets["private"])):
        _put(seen, doc, ("output", f"{n}_{name}"), {"value": value})
    return doc


def _bucket(key, raw, seen):
    s = _spec("s3_bucket", key, raw, ("bucket",), BUCKET_DEFAULTS)
    n = key.replace("-", "_")
    name = str(s["bucket"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", name):
        raise ValueError(f"terraform-aws s3_bucket '{key}': {name!r} is not a valid S3 bucket name")

    doc = {}

    def add(rtype, body):
        _put(seen, doc, ("resource", rtype, n), body)

    bucket, arn = f"${{aws_s3_bucket.{n}.id}}", f"${{aws_s3_bucket.{n}.arn}}"
    add("aws_s3_bucket", {"bucket": name, "force_destroy": s["force_destroy"], "tags": dict(s["tags"])})
    add("aws_s3_bucket_public_access_block", {
        "bucket": bucket,
        "block_public_acls": True,
        "block_public_policy": True,
        "ignore_public_acls": True,
        "restrict_public_buckets": True,
    })
    add("aws_s3_bucket_ownership_controls", {"bucket": bucket, "rule": {"object_ownership": "BucketOwnerEnforced"}})
    if s["versioning"]:
        add("aws_s3_bucket_versioning", {"bucket": bucket, "versioning_configuration": {"status": "Enabled"}})
    rule = {"apply_server_side_encryption_by_default": {"sse_algorithm": "AES256"}}
    if s["kms_key_arn"]:
        rule = {
            "apply_server_side_encryption_by_default": {
                "sse_algorithm": "aws:kms",
                "kms_master_key_id": str(s["kms_key_arn"]),
            },
            "bucket_key_enabled": True,
        }
    add("aws_s3_bucket_server_side_encryption_configuration", {"bucket": bucket, "rule": rule})
    if s["deny_insecure_transport"]:
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "DenyInsecureTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [arn, f"{arn}/*"],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            }],
        }
        add("aws_s3_bucket_policy", {
            "bucket": bucket,
            "policy": json.dumps(policy, sort_keys=True),
            "depends_on": [f"aws_s3_bucket_public_access_block.{n}"],
        })

    _put(seen, doc, ("output", f"{n}_bucket_id"), {"value": bucket})
    _put(seen, doc, ("output", f"{n}_bucket_arn"), {"value": arn})
    return doc


def main(input_params=None):
    config = inventory().parameters.get("generators", {}).get("terraform-aws") or {}
    unknown = sorted(set(config) - {"region", "default_tags", "vpc", "s3_bucket"})
    if unknown:
        raise ValueError(f"terraform-aws: unknown keys {', '.join(unknown)}")
    if not config.get("region"):
        raise ValueError("terraform-aws: region is required")

    provider = {"region": str(config["region"])}
    if config.get("default_tags"):
        provider["default_tags"] = {"tags": dict(config["default_tags"])}
    out = BaseObj()
    out.root["providers.tf"] = {
        "terraform": {"required_version": ">= 1.5.0", "required_providers": {"aws": PROVIDER}},
        "provider": {"aws": provider},
    }
    seen = set()
    vpcs, buckets = config.get("vpc") or {}, config.get("s3_bucket") or {}
    for key in sorted(vpcs):
        out.root[f"network-{key}.tf"] = _vpc(key, vpcs[key], seen)
    for key in sorted(buckets):
        out.root[f"bucket-{key}.tf"] = _bucket(key, buckets[key], seen)
    return out
