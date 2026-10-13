"""RabbitMQ Operator generator for Kapitan.

Generates RabbitMQ Operator CRDs including Cluster, Queue, Policy, Exchange,
Binding, User, Permission, Vhost, Federation, and Shovel resources.
Also supports ConfigMaps and Secrets for RabbitMQ configuration.
"""

__version__ = "1.0.1"

import base64
import hashlib
import logging
import os
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory
from kapitan.inputs.kadet import search_paths as _kadet_search_paths
from kapitan.utils import render_jinja2_file

from . import k8s


def j2(filename, ctx):
    """Render a Jinja2 template file against the current compile item's search paths."""
    return render_jinja2_file(
        filename, ctx, search_paths=_kadet_search_paths.get(["."])
    )


inv = inventory()
logger = logging.getLogger(__name__)

# Kinds whose CRD requires spec.name (the object name inside RabbitMQ).
_NAMED_KINDS = {"Queue", "Exchange", "Policy", "Vhost", "Federation", "Shovel"}


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert OmegaConf / BaseObj objects to plain Python dicts."""
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


def _get_rabbitmq_config() -> dict:
    """Get rabbitmq config from inventory with safe defaults."""
    config = inv.parameters.get("generators", {}).get("rabbitmq", {})
    return _convert_to_dict(config) or {}


def _get_namespace() -> str:
    """Get namespace from generators.rabbitmq.namespace, fallback to parameters.namespace."""
    rabbitmq_config = _get_rabbitmq_config()
    return str(
        rabbitmq_config.get("namespace", inv.parameters.get("namespace", "default"))
    )


def _ref(value: Any) -> Any:
    """A bare string names the referenced object: ``x`` -> ``{name: x}``."""
    return {"name": value} if isinstance(value, str) else _convert_to_dict(value)


class RabbitmqObject(k8s.Base):
    """RabbitMQ Operator CRD resource. Required kwargs: name, kind.

    spec precedence: generator defaults < ``spec`` < ``cluster_reference``.
    """

    def new(self):
        self.need("name")
        self.kwargs.apiVersion = "rabbitmq.com/v1beta1"
        super().new()

    def body(self):
        super().body()
        rabbitmq_obj = self.kwargs.get("rabbitmq_obj", {})
        self.add_namespace(rabbitmq_obj.get("namespace") or _get_namespace())

        self.add_annotations(rabbitmq_obj.get("annotations", {}))
        self.add_labels(rabbitmq_obj.get("labels", {}))

        kind = self.kwargs.kind
        spec: dict[str, Any] = {}
        if kind in _NAMED_KINDS:
            spec["name"] = self.kwargs.name
        default_ref = _get_rabbitmq_config().get("cluster_reference")
        if kind != "RabbitmqCluster" and default_ref is not None:
            spec["rabbitmqClusterReference"] = _ref(default_ref)
        passthrough = _convert_to_dict(rabbitmq_obj.get("spec")) or {}
        spec.update(passthrough)
        cluster_reference = rabbitmq_obj.get("cluster_reference")
        if kind != "RabbitmqCluster" and cluster_reference is not None:
            if "rabbitmqClusterReference" in passthrough:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    "cluster_reference",
                    "rabbitmqClusterReference",
                    self.kwargs.name,
                )
            spec["rabbitmqClusterReference"] = _ref(cluster_reference)
        if spec:
            self.root.spec = spec


# The following classes are required to generate Secrets + ConfigMaps
class SharedConfig:
    """Shared class for both Secrets and ConfigMaps.

    Contains common functionality for both classes.
    """

    @staticmethod
    def encode_string(unencoded_string):
        """Base64 encode a string."""
        return base64.b64encode(unencoded_string.encode("ascii")).decode("ascii")

    def setup_metadata(self):
        self.add_namespace(self.config.get("namespace") or _get_namespace())
        self.add_annotations(self.config.get("annotations", {}))
        self.add_labels(self.config.get("labels", {}))

        self.items = self.config["items"]
        manifest = inv.parameters.get("generators", {}).get("manifest", {}) or {}
        default_config = manifest.get("default_config", {}) or {}
        all_globals = default_config.get("globals", {}) or {}
        kind = "config_maps" if isinstance(self, ConfigMap) else "secrets"
        globals = all_globals.get(kind, {}) or {}
        self.add_annotations(globals.get("annotations", {}))
        self.add_labels(globals.get("labels", {}))

    def add_directory(self, directory, encode=False):
        rabbitmq_config = _get_rabbitmq_config()
        stringdata = rabbitmq_config.get("use_tesoro", False)
        if directory and os.path.isdir(directory):
            # Sorted: listing order feeds the versioning hash and must not
            # depend on the filesystem.
            for filename in sorted(os.listdir(directory)):
                with open(f"{directory}/{filename}") as f:
                    file_content = f.read()
                    self.add_item(
                        filename,
                        file_content,
                        request_encode=encode,
                        stringdata=stringdata,
                    )

    def add_data(self, data):
        rabbitmq_config = _get_rabbitmq_config()
        stringdata = rabbitmq_config.get("use_tesoro", False)

        for key, spec in data.items():
            encode = spec.get("b64_encode", False)

            if "value" in spec:
                value = spec.get("value")
            if "template" in spec:
                value = j2(spec.template, spec.get("values", {}))
            if "file" in spec:
                with open(spec.file) as f:
                    value = f.read()

            self.add_item(key, value, request_encode=encode, stringdata=stringdata)

    def add_string_data(self, string_data, encode=False):
        stringdata = True

        for key, spec in string_data.items():
            if "value" in spec:
                value = spec.get("value")
            if "template" in spec:
                value = j2(spec.template, spec.get("values", {}))
            if "file" in spec:
                with open(spec.file) as f:
                    value = f.read()

            self.add_item(key, value, request_encode=encode, stringdata=stringdata)

    def versioning(self, enabled=False):
        if enabled:
            self.hash = hashlib.sha256(str(self.root.to_dict()).encode()).hexdigest()[
                :8
            ]
            self.root.metadata.name += f"-{self.hash}"


class ConfigMap(k8s.Base, SharedConfig):
    def new(self):
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "ConfigMap"
        super().new()

    def body(self):
        super().body()

    def add_item(self, key, value, request_encode=False, stringdata=False):
        encode = request_encode

        self.root["data"][key] = self.encode_string(value) if encode else value


class ComponentConfig(ConfigMap, SharedConfig):
    def new(self):
        super().new()
        self.need("config")

    def body(self):
        super().body()
        self.config = self.kwargs.config

        self.setup_metadata()
        self.add_data(self.config.get("data", {}))
        self.add_directory(self.config.get("directory"), encode=False)
        self.versioning(self.config.get("versioned", False))


class Secret(k8s.Base):
    def new(self):
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "Secret"
        super().new()

    def body(self):
        super().body()

    def add_item(self, key, value, request_encode=False, stringdata=False):
        encode = not stringdata and request_encode
        field = "stringData" if stringdata else "data"
        self.root[field][key] = self.encode_string(value) if encode else value


class ComponentSecret(Secret, SharedConfig):
    def new(self):
        super().new()
        self.need("config")

    def body(self):
        super().body()
        self.config = self.kwargs.config
        self.root.type = self.config.get("type", "Opaque")

        self.setup_metadata()
        if self.config.get("data"):
            self.add_data(self.config.get("data", {}))
        if self.config.get("string_data"):
            self.add_string_data(self.config.get("string_data"))
        self.add_directory(self.config.get("directory"), encode=True)
        self.versioning(self.config.get("versioned", False))


def generate_rabbitmq_obj(kind, input_params):
    obj = BaseObj()

    rabbitmq_config = _get_rabbitmq_config()
    rabbitmq_obj_list = rabbitmq_config.get(kind.lower(), {})
    namespace = _get_namespace()

    for name in rabbitmq_obj_list.keys():
        resource_config = rabbitmq_obj_list[name] or {}
        rabbitmq_obj = RabbitmqObject(
            kind=kind, name=name, rabbitmq_obj=resource_config
        )
        resource_namespace = resource_config.get("namespace") or namespace

        obj.root[f"{resource_namespace}/{name}-{kind.lower()}"] = rabbitmq_obj

    return obj


def generate_rabbitmq_resources(input_params):
    obj = BaseObj()
    rabbitmq_config = _get_rabbitmq_config()
    resources_list = rabbitmq_config.get("rabbitmq_resources", {})
    if not resources_list:
        return obj
    user_list = {}
    permission_list = {}
    vhost_list = {}

    # Construct a suitable data structure for the classes generating the CRDs
    namespace = _get_namespace()

    for name, user in (resources_list.get("users") or {}).items():
        user = user or {}
        user_namespace = user.get("namespace") or namespace

        for permission_name, permission in (user.get("permissions") or {}).items():
            permission = permission or {}
            # The User above is emitted from this entry, so reference it: with
            # generated credentials its RabbitMQ username is random.
            spec: dict[str, Any] = {"permissions": {}}
            if permission.get("user") is not None:
                spec["user"] = permission["user"]
            else:
                spec["userReference"] = _ref(
                    permission.get("user_reference") or name
                )
            if "vhost" in permission:
                spec["vhost"] = permission["vhost"]
            for permission_key in (
                "read_permission",
                "write_permission",
                "configure_permission",
            ):
                if permission_key in permission:
                    spec["permissions"][permission_key.replace("_permission", "")] = (
                        permission[permission_key]
                    )
            permission_list[permission_name] = {
                "spec": spec,
                "namespace": user_namespace,
                "cluster_reference": user.get("cluster_reference"),
            }

        user_spec: dict[str, Any] = {}
        if user.get("secret_name") is not None:
            # importCredentialsSecret is a LocalObjectReference; a string is
            # shorthand for {name: ...}
            secret = user["secret_name"]
            user_spec["importCredentialsSecret"] = (
                {"name": secret} if isinstance(secret, str) else secret
            )
        if user.get("user_tags") is not None:
            user_spec["tags"] = user["user_tags"]
        user_list[name] = {
            "spec": user_spec,
            "namespace": user_namespace,
            "cluster_reference": user.get("cluster_reference"),
        }

    for name, vhost in (resources_list.get("vhosts") or {}).items():
        vhost = vhost or {}
        vhost_list[name] = {
            "spec": {"name": name},
            "namespace": vhost.get("namespace") or namespace,
            "cluster_reference": vhost.get("cluster_reference"),
        }

    for name, rabbitmq_obj in permission_list.items():
        rabbitmq_resources = RabbitmqObject(
            kind="Permission",
            name=name,
            rabbitmq_obj=rabbitmq_obj,
        )
        obj.root[f"{rabbitmq_obj['namespace']}/{name}-permission"] = rabbitmq_resources

    for name, rabbitmq_obj in user_list.items():
        rabbitmq_resources = RabbitmqObject(
            kind="User", name=name, rabbitmq_obj=rabbitmq_obj
        )
        obj.root[f"{rabbitmq_obj['namespace']}/{name}-user"] = rabbitmq_resources

    for name, rabbitmq_obj in vhost_list.items():
        rabbitmq_resources = RabbitmqObject(
            kind="Vhost", name=name, rabbitmq_obj=rabbitmq_obj
        )
        obj.root[f"{rabbitmq_obj['namespace']}/{name}-vhost"] = rabbitmq_resources

    return obj


# This function renderes an Shared-ConfigMaps + Secrets
def generate_resource_manifests(input_params):
    """Generate ConfigMaps and Secrets for RabbitMQ configuration."""
    obj = BaseObj()
    rabbitmq_config = _get_rabbitmq_config()
    namespace = _get_namespace()

    for secret_name, secret_spec in rabbitmq_config.get("secrets", {}).items():
        name = secret_spec.get("name", secret_name)
        secret = ComponentSecret(name=name, config=secret_spec)
        obj.root[f"{secret_spec.get('namespace') or namespace}/{name}-secret"] = secret

    for config_name, config_spec in rabbitmq_config.get("configs", {}).items():
        name = config_spec.get("name", config_name)
        config = ComponentConfig(name=name, config=config_spec)
        obj.root[f"{config_spec.get('namespace') or namespace}/{name}-cm"] = config
    return obj


def main(input_params):
    """Generate RabbitMQ resources from inventory.

    Reads from parameters.generators.rabbitmq:
    - namespace: Target namespace (defaults to parameters.namespace)
    - cluster_reference: Default rabbitmqClusterReference of topology kinds
    - rabbitmqcluster, queue, policy, exchange, binding, etc.: Resource configurations
    - secrets: Secret configurations
    - configs: ConfigMap configurations
    - use_tesoro: Enable Tesoro stringData mode
    """
    all_manifests = BaseObj()

    # Generate standard RabbitMQ CRDs
    kinds = [
        "RabbitmqCluster",
        "Queue",
        "Policy",
        "Exchange",
        "Binding",
        "User",
        "Permission",
        "Vhost",
        "Federation",
        "Shovel",
    ]
    for kind in kinds:
        manifest = generate_rabbitmq_obj(kind, input_params)
        all_manifests.root.update(manifest.root)

    # Generate RabbitMQ resources (users, permissions, vhosts)
    rabbitmq_resources_manifests = generate_rabbitmq_resources(input_params)
    all_manifests.root.update(rabbitmq_resources_manifests.root)

    # Generate ConfigMaps and Secrets
    resource_manifests = generate_resource_manifests(input_params)
    all_manifests.root.update(resource_manifests.root)

    return all_manifests


__all__ = [
    "RabbitmqObject",
    "ConfigMap",
    "ComponentConfig",
    "Secret",
    "ComponentSecret",
    "main",
    "k8s",
    "inv",
]
