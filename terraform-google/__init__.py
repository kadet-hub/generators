"""Google Cloud VPC networks and Cloud Storage buckets as Terraform JSON.

Reads parameters.generators.terraform-google; see README.md for the
inventory contract.
"""

import ipaddress
import re

from kapitan.inputs.kadet import BaseObj, inventory

PROVIDER = {"source": "hashicorp/google", "version": "8.7.0"}
IAP_RANGE = "35.235.240.0/20"
HEALTH_CHECK_RANGE = "35.191.0.0/16"
FLOW_LOGS = {
    "enabled": True,
    "aggregation_interval": "INTERVAL_5_SEC",
    "flow_sampling": 0.5,
    "metadata": "INCLUDE_ALL_METADATA",
}
NAT = {"enabled": True, "source_ranges": "ALL_SUBNETWORKS_ALL_IP_RANGES", "log_filter": "ERRORS_ONLY"}
NAT_SOURCE_RANGES = ("ALL_SUBNETWORKS_ALL_IP_RANGES", "ALL_SUBNETWORKS_ALL_PRIMARY_IP_RANGES")
FIREWALL = {"iap_ssh": True, "health_checks": False, "internal": True}
BUCKET = {
    "storage_class": "STANDARD",
    "uniform_bucket_level_access": True,
    "public_access_prevention": "enforced",
    "versioning": True,
    "soft_delete_retention_seconds": 604800,
    "force_destroy": False,
    "labels": {},
    "lifecycle_rules": [],
    "iam": {},
}
# The provider drops a zero condition unless its send_*_if_zero flag is set.
ZERO_FLAGS = {
    "age": "send_age_if_zero",
    "days_since_custom_time": "send_days_since_custom_time_if_zero",
    "days_since_noncurrent_time": "send_days_since_noncurrent_time_if_zero",
    "num_newer_versions": "send_num_newer_versions_if_zero",
}


def _fail(where, reason):
    return ValueError(f"terraform-google: {where}: {reason}")


def _tf_name(seen, kind, *parts):
    """Terraform label from inventory keys: [a-z0-9_], unique per kind."""
    name = re.sub(r"[^a-z0-9_]", "_", "_".join(parts).lower())
    if not name or name[0].isdigit():
        name = "_" + name
    if (kind, name) in seen:
        raise _fail("/".join(parts), f"{kind}.{name} is already derived from another inventory key; rename one")
    seen.add((kind, name))
    return name


def _cidr(where, value):
    try:
        return ipaddress.IPv4Network(value)
    except ValueError as e:
        raise _fail(where, f"invalid CIDR: {e}") from None


def _network(seen, name, spec):
    subnets = spec.get("subnets") or {}
    if not subnets:
        raise _fail(f"network {name}", "subnets is required")
    project = {"project": spec["project"]} if spec.get("project") else {}
    net = _tf_name(seen, "google_compute_network", name)
    net_id = f"${{google_compute_network.{net}.id}}"
    network = {
        "name": name,
        "auto_create_subnetworks": False,
        "routing_mode": spec.get("routing_mode", "GLOBAL"),
        "delete_default_routes_on_create": spec.get("delete_default_routes_on_create", False),
        **project,
    }
    if spec.get("mtu") is not None:
        network["mtu"] = spec["mtu"]
    resources = {"google_compute_network": {net: network}}

    ranges, subnet_ids = [], {}
    for sname in sorted(subnets):
        s = subnets[sname] or {}
        where = f"network {name} subnet {sname}"
        for key in ("region", "cidr"):
            if not s.get(key):
                raise _fail(where, f"{key} is required")
        primary = _cidr(where, s["cidr"])
        ranges.append((f"subnet {sname}", primary))
        secondary = dict(s.get("secondary_ranges") or {})
        gke = s.get("gke")
        if gke:
            for role in ("pods", "services"):
                if not gke.get(role):
                    raise _fail(where, f"gke.{role} is required")
                if f"{sname}-{role}" in secondary:
                    raise _fail(where, f"secondary range {sname}-{role} is also set by gke.{role}")
                secondary[f"{sname}-{role}"] = gke[role]
        secondary = {r: _cidr(f"{where} secondary range {r}", c) for r, c in secondary.items()}
        ranges += [(f"secondary range {r} of subnet {sname}", c) for r, c in secondary.items()]

        subnet = {
            "name": sname,
            "region": s["region"],
            "network": net_id,
            "ip_cidr_range": str(primary),
            "private_ip_google_access": s.get("private_google_access", True),
            **project,
        }
        flow_logs = {**FLOW_LOGS, **(s.get("flow_logs") or {})}
        if flow_logs["enabled"]:
            subnet["log_config"] = {k: flow_logs[k] for k in ("aggregation_interval", "flow_sampling", "metadata")}
        if secondary:
            subnet["secondary_ip_range"] = [
                {"range_name": r, "ip_cidr_range": str(secondary[r])} for r in sorted(secondary)
            ]
        tf = _tf_name(seen, "google_compute_subnetwork", name, sname)
        resources.setdefault("google_compute_subnetwork", {})[tf] = subnet
        subnet_ids[sname] = f"${{google_compute_subnetwork.{tf}.id}}"

    for i, (label, cidr) in enumerate(ranges):
        for other_label, other in ranges[i + 1 :]:
            if cidr.overlaps(other):
                raise _fail(f"network {name}", f"{label} {cidr} overlaps {other_label} {other}")

    nat = {**NAT, **(spec.get("nat") or {})}
    if nat["enabled"]:
        if nat["source_ranges"] not in NAT_SOURCE_RANGES:
            raise _fail(f"network {name}", f"nat.source_ranges must be one of {', '.join(NAT_SOURCE_RANGES)}")
        for region in sorted({s["region"] for s in subnets.values()}):
            router = _tf_name(seen, "google_compute_router", name, region)
            resources.setdefault("google_compute_router", {})[router] = {
                "name": f"{name}-{region}",
                "region": region,
                "network": net_id,
                **project,
            }
            router_nat = {
                "name": f"{name}-{region}",
                "router": f"${{google_compute_router.{router}.name}}",
                "region": region,
                "nat_ip_allocate_option": "AUTO_ONLY",
                "source_subnetwork_ip_ranges_to_nat": nat["source_ranges"],
                **project,
            }
            if nat["log_filter"]:
                router_nat["log_config"] = {"enable": True, "filter": nat["log_filter"]}
            nat_tf = _tf_name(seen, "google_compute_router_nat", name, region)
            resources.setdefault("google_compute_router_nat", {})[nat_tf] = router_nat

    firewall = {**FIREWALL, **(spec.get("firewall") or {})}
    rules = {
        "iap_ssh": ("allow-iap-ssh", [IAP_RANGE], [{"protocol": "tcp", "ports": ["22"]}]),
        "health_checks": ("allow-health-checks", [HEALTH_CHECK_RANGE], [{"protocol": "tcp"}]),
        "internal": ("allow-internal", [str(c) for c in sorted({c for _, c in ranges})], [{"protocol": "all"}]),
    }
    for key, (suffix, source_ranges, allow) in rules.items():
        if firewall[key]:
            tf = _tf_name(seen, "google_compute_firewall", name, suffix)
            resources.setdefault("google_compute_firewall", {})[tf] = {
                "name": f"{name}-{suffix}",
                "network": net_id,
                "direction": "INGRESS",
                "priority": 1000,
                "source_ranges": source_ranges,
                "allow": allow,
                "log_config": {"metadata": "INCLUDE_ALL_METADATA"},
                **project,
            }

    outputs = {
        _tf_name(seen, "output", "network", name, "id"): {"value": net_id},
        _tf_name(seen, "output", "network", name, "self_link"): {"value": f"${{google_compute_network.{net}.self_link}}"},
        _tf_name(seen, "output", "network", name, "subnet_ids"): {"value": subnet_ids},
    }
    return {"resource": resources, "output": outputs}


def _bucket(seen, key, spec):
    b = {**BUCKET, **spec}
    if not b.get("location"):
        raise _fail(f"bucket {key}", "location is required")
    tf = _tf_name(seen, "google_storage_bucket", key)
    bucket = {
        "name": b.get("name") or key,
        "location": b["location"],
        "storage_class": b["storage_class"],
        "uniform_bucket_level_access": b["uniform_bucket_level_access"],
        "public_access_prevention": b["public_access_prevention"],
        "force_destroy": b["force_destroy"],
        "versioning": {"enabled": b["versioning"]},
        "soft_delete_policy": {"retention_duration_seconds": b["soft_delete_retention_seconds"]},
    }
    if b["labels"]:
        bucket["labels"] = b["labels"]
    rules = []
    for i, rule in enumerate(b["lifecycle_rules"]):
        if not (rule.get("action") or {}).get("type"):
            raise _fail(f"bucket {key} lifecycle_rules[{i}]", "action.type is required")
        condition = dict(rule.get("condition") or {})
        for field, flag in ZERO_FLAGS.items():
            if condition.get(field) == 0:
                condition[flag] = True
        rules.append({"action": rule["action"], "condition": condition})
    if rules:
        bucket["lifecycle_rule"] = rules
    resources = {"google_storage_bucket": {tf: bucket}}

    for role in sorted(b["iam"]):
        for member in sorted(set(b["iam"][role])):
            member_tf = _tf_name(seen, "google_storage_bucket_iam_member", key, role.removeprefix("roles/"), member)
            resources.setdefault("google_storage_bucket_iam_member", {})[member_tf] = {
                "bucket": f"${{google_storage_bucket.{tf}.name}}",
                "role": role,
                "member": member,
            }

    outputs = {
        _tf_name(seen, "output", "bucket", key, "name"): {"value": f"${{google_storage_bucket.{tf}.name}}"},
        _tf_name(seen, "output", "bucket", key, "url"): {"value": f"${{google_storage_bucket.{tf}.url}}"},
    }
    return {"resource": resources, "output": outputs}


def main(input_params=None):
    config = inventory().parameters.get("generators", {}).get("terraform-google") or {}
    if not config.get("project"):
        raise _fail("generators.terraform-google", "project is required")
    provider = {"project": config["project"]}
    for key in ("region", "default_labels"):
        if config.get(key):
            provider[key] = config[key]

    out = BaseObj()
    out.root["providers.tf"] = {
        "terraform": {"required_version": ">= 1.5.0", "required_providers": {"google": PROVIDER}},
        "provider": {"google": provider},
    }
    seen = set()
    networks = config.get("network") or {}
    for name in sorted(networks):
        out.root[f"network-{name}.tf"] = _network(seen, name, networks[name] or {})
    buckets = config.get("buckets") or {}
    for key in sorted(buckets):
        out.root[f"bucket-{key}.tf"] = _bucket(seen, key, buckets[key] or {})
    return out
