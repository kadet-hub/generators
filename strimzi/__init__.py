"""Strimzi resource generator for Kapitan.

Renders kafka.strimzi.io/v1 Kafka, KafkaNodePool, KafkaTopic and KafkaUser;
see README.md for the inventory contract.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

__version__ = "1.0.1"

API_VERSION = "kafka.strimzi.io/v1"
CLUSTER_LABEL = "strimzi.io/cluster"

# packaging/examples/security/tls-auth/kafka.yaml at 1.3.0
DEFAULT_LISTENER = {
    "name": "tls",
    "port": 9093,
    "type": "internal",
    "tls": True,
    "authentication": {"type": "tls"},
}

_DNS_SUBDOMAIN = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*")


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


def _merge(base: Any, override: Any) -> Any:
    """Deep merge: dicts merge key by key, any other value replaces."""
    if not (isinstance(base, dict) and isinstance(override, dict)):
        return override
    result = dict(base)
    for key, value in override.items():
        result[key] = _merge(result.get(key), value)
    return result


def _get(tree: Any, path: str) -> Any:
    for part in path.split("."):
        tree = tree.get(part) if isinstance(tree, dict) else None
    return tree


def _set(tree: dict, path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for part in parents:
        tree = tree.setdefault(part, {})
    tree[last] = _merge(tree.get(last), value)


def _spec(name: str, config: dict, defaults: dict, flat: dict) -> dict:
    """defaults < ``spec`` < flat keys; flat is {key: (spec path, shorthand)}."""
    passthrough = config.get("spec") or {}
    spec = _merge(defaults, passthrough)
    for key, (path, expand) in flat.items():
        if config.get(key) is None:
            continue
        if _get(passthrough, path) is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                key,
                path,
                name,
            )
        _set(spec, path, expand(config[key]))
    return copy.deepcopy(spec)


def _same(value: Any) -> Any:
    return value


def _typed(value: Any) -> Any:
    """``tls`` -> ``{type: tls}``; a dict passes through."""
    return {"type": value} if isinstance(value, str) else value


def _storage(value: Any) -> Any:
    """A size string -> one persistent JBOD volume that also holds the KRaft metadata."""
    if not isinstance(value, str):
        return value
    # packaging/examples/kafka/kafka-persistent.yaml at 1.3.0
    volume = {"id": 0, "type": "persistent-claim", "size": value, "kraftMetadata": "shared"}
    return {"type": "jbod", "volumes": [volume]}


_ACL_RESOURCES = {"topic": "topic", "group": "group", "transactional_id": "transactionalId"}


def _acl(acl: dict) -> dict:
    """``topic: x`` / ``group: x`` / ``transactional_id: x`` / ``cluster: true`` -> ``resource``."""
    if "resource" in acl:
        return acl
    named = [k for k in _ACL_RESOURCES if acl.get(k) is not None] + (["cluster"] if acl.get("cluster") else [])
    if len(named) != 1:
        raise ValueError(f"ACL {acl}: set exactly one of topic, group, transactional_id, cluster")
    result = {k: v for k, v in acl.items() if k not in (*_ACL_RESOURCES, "cluster", "pattern_type")}
    resource: dict[str, Any] = {}
    for key, kind in _ACL_RESOURCES.items():
        if acl.get(key) is not None:
            resource = {"type": kind, "name": acl[key]}
    if acl.get("cluster"):
        resource = {"type": "cluster"}
    if acl.get("pattern_type") is not None:
        resource["patternType"] = acl["pattern_type"]
    result["resource"] = resource
    return result


def _acls(value: Any) -> dict:
    return {"type": "simple", "acls": [_acl(a) for a in value]}


def _replication(brokers: int) -> dict:
    """Replication settings of upstream's examples, capped at the broker count."""
    factor = min(3, brokers)
    min_isr = max(1, factor - 1)
    return {
        "default.replication.factor": factor,
        "min.insync.replicas": min_isr,
        "offsets.topic.replication.factor": factor,
        "transaction.state.log.replication.factor": factor,
        "transaction.state.log.min.isr": min_isr,
    }


KAFKA_FLAT = {
    "version": ("kafka.version", _same),
    "metadata_version": ("kafka.metadataVersion", _same),
    "listeners": ("kafka.listeners", _same),
    "config": ("kafka.config", _same),
    "authorization": ("kafka.authorization", _typed),
}
NODE_POOL_FLAT = {
    "roles": ("roles", _same),
    "replicas": ("replicas", _same),
    "storage": ("storage", _storage),
    "resources": ("resources", _same),
}
TOPIC_FLAT = {
    "topic_name": ("topicName", _same),
    "partitions": ("partitions", _same),
    "replicas": ("replicas", _same),
    "config": ("config", _same),
}
USER_FLAT = {
    "authentication": ("authentication", _typed),
    "acls": ("authorization", _acls),
    "quotas": ("quotas", _same),
}


class StrimziResource(k8s.Base):
    """One Strimzi custom resource. Required kwargs: kind, name, namespace, config, spec."""

    def new(self) -> None:
        self.need("config")
        self.need("namespace")
        self.need("spec")
        self.kwargs.apiVersion = API_VERSION
        super().new()

    def body(self) -> None:
        super().body()
        # Strimzi copies CR labels onto pods, Services and Secrets; a name label
        # breaks there for names over 63 characters.
        del self.root.metadata["labels"]
        config = self.kwargs.config
        self.add_namespace(self.kwargs.namespace)
        if self.kwargs.get("cluster"):
            self.add_label(CLUSTER_LABEL, self.kwargs.cluster)
        labels = config.get("labels") or {}
        reserved = [k for k in labels if k.startswith("strimzi.io/") and k != CLUSTER_LABEL]
        if reserved:
            # operator-common/.../model/Labels.java at 1.3.0 rejects them
            raise ValueError(f"{self.kwargs.kind} '{self.kwargs.name}': labels {reserved} are reserved by Strimzi")
        self.add_labels(labels)
        self.add_annotations(config.get("annotations") or {})
        self.root.spec = self.kwargs.spec


def _topic_names(key: str) -> tuple[str, str | None]:
    """(metadata.name, spec.topicName) for a topic entry key."""
    if len(key) <= 253 and _DNS_SUBDOMAIN.fullmatch(key):
        return key, None
    name = re.sub(r"[^a-z0-9]+", "-", key.lower())[:200].strip("-") or "topic"
    return f"{name}-{hashlib.sha256(key.encode()).hexdigest()[:8]}", key


def _put(obj: BaseObj, key: str, resource: StrimziResource) -> None:
    if key in obj.root:
        raise ValueError(f"two entries render the same output '{key}'")
    obj.root[key] = resource


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.strimzi."""
    obj = BaseObj()
    gen = _convert_to_dict(inv.parameters.get("generators", {}).get("strimzi", {}) or {})
    default_namespace = str(gen.get("namespace") or inv.parameters.get("namespace", "default"))
    kafkas = gen.get("kafkas") or {}
    namespaces = {}
    pools: set[tuple[str, str]] = set()

    for name, config in kafkas.items():
        config = dict(config or {})
        namespace = config.get("namespace") or default_namespace
        namespaces[name] = namespace
        no_authorization = config.get("authorization") == "none"
        if no_authorization:
            config.pop("authorization")
        entity_operator = config.pop("entity_operator", None)
        if entity_operator not in (None, True, False):
            raise ValueError(f"Kafka '{name}': entity_operator must be true or false")
        brokers = 0
        for pool, pool_config in (config.get("node_pools") or {}).items():
            pool_config = pool_config or {}
            if (namespace, pool) in pools:
                raise ValueError(f"KafkaNodePool '{pool}' is defined twice in namespace '{namespace}'")
            pools.add((namespace, pool))
            spec = _spec(pool, pool_config, {"replicas": 3}, NODE_POOL_FLAT)
            if "broker" in (spec.get("roles") or []):
                brokers += spec.get("replicas") or 0
            _put(obj, f"{namespace}/{name}-{pool}-kafkanodepool", StrimziResource(
                kind="KafkaNodePool", name=pool, namespace=namespace, cluster=name, config=pool_config, spec=spec
            ))
        defaults: dict[str, Any] = {
            "kafka": {"listeners": [DEFAULT_LISTENER], "authorization": {"type": "simple"}},
            "entityOperator": {"topicOperator": {}, "userOperator": {}},
        }
        if brokers:
            defaults["kafka"]["config"] = _replication(brokers)
        spec = _spec(name, config, defaults, KAFKA_FLAT)
        for removed, path in ((no_authorization, "kafka.authorization"), (entity_operator is False, "entityOperator")):
            if not removed:
                continue
            if _get(config.get("spec") or {}, path) is not None:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    "authorization" if path == "kafka.authorization" else "entity_operator",
                    path,
                    name,
                )
            *parents, last = path.split(".")
            parent = spec
            for part in parents:
                parent = parent[part]
            parent.pop(last, None)
        _put(obj, f"{namespace}/{name}-kafka", StrimziResource(
            kind="Kafka", name=name, namespace=namespace, config=config, spec=spec
        ))

    for section, kind, flat in (("topics", "KafkaTopic", TOPIC_FLAT), ("users", "KafkaUser", USER_FLAT)):
        for key, config in (gen.get(section) or {}).items():
            config = config or {}
            cluster = config.get("cluster") or gen.get("cluster") or (next(iter(kafkas)) if len(kafkas) == 1 else None)
            if not cluster:
                raise ValueError(f"{kind} '{key}': set cluster, generators.strimzi.cluster or define exactly one Kafka")
            if kafkas and cluster not in kafkas:
                raise ValueError(f"{kind} '{key}': cluster '{cluster}' is not one of the Kafka entries {list(kafkas)}")
            namespace = config.get("namespace") or namespaces.get(cluster) or default_namespace
            name, topic_name = _topic_names(key) if kind == "KafkaTopic" else (key, None)
            defaults = {"topicName": topic_name} if topic_name else {}
            _put(obj, f"{namespace}/{name}-{kind.lower()}", StrimziResource(
                kind=kind,
                name=name,
                namespace=namespace,
                cluster=cluster,
                config=config,
                spec=_spec(name, config, defaults, flat),
            ))
    return obj
