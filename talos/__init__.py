"""
Talos Machine Configuration Generator.

Generates Talos (v1alpha1) machine configuration files from Kapitan inventory.
Supports controlplane, worker, and init node types.

Targets Talos v1.14.5. The inventory keeps the v1alpha1 shape; each node
output is the v1alpha1 document reduced to its non-deprecated fields plus
the multi-document kinds that replace the rest (see multidoc.py).

Usage in Kapitan inventory:
    parameters:
      generators:
        talos:
          base:              # shared config deep-merged under every node
            machine:
              install:
                disk: /dev/sda
            cluster:
              clusterName: my-cluster
              controlPlane:
                endpoint: https://my-cluster.example.com:6443
          nodes:
            controlplane-1:
              type: controlplane
              hostname: controlplane-1   # -> machine.network.hostname
              ip: 192.0.2.10/24          # -> addresses on the single interface
              userdataSecret:            # optional: KubeVirt userdata Secret
                name: cp-1-userdata      #   emitted as extra output document
                namespace: infra         #   '<namespace>/<name>-secret'
              machine:
                network:
                  nameservers:
                    - 192.0.2.53
          patches:           # extra output documents (config patches)
            patch-all:
              machine:
                time:
                  servers: [pool.ntp.org]
          secrets: {}        # optional passthrough -> secrets output
          talosconfig: {}    # optional passthrough -> talosconfig output

Per-node configs are the shared ``base`` deep-merged with the node entry
(node wins; dicts merge recursively, lists replace). The ``hostname`` and
``ip`` shorthands override merged values and log a warning on collisions;
``ip`` requires exactly one configured interface - with several interfaces
set per-interface (or per-VLAN, via ``vlans`` keyed by vlanId) addresses
explicitly.

A node carrying ``userdataSecret`` (``name`` and ``namespace`` required)
additionally emits a Kubernetes Secret wrapping its rendered machine config
as ``stringData.userdata``, ready to mount as KubeVirt cloud-init userdata.
The key is stripped before the machine config is built and never appears in
the node output.

The legacy ``parameters.talos_nodes`` location keeps working but logs a
deprecation warning.

Multi-line strings (certs, machine files) are dumped literal-style by
Kapitan's PrettyDumper by default (``--yaml-multiline-string-style``,
default ``literal`` since Kapitan 0.36).
"""

from __future__ import annotations

import logging
from typing import Any, cast

import yaml

from . import multidoc

try:
    from kapitan.inputs.kadet import BaseObj, inventory

    inv = inventory()
except ImportError:
    # For testing outside Kapitan context
    inv = None  # type: ignore[assignment]

__version__ = "1.3.0"
__all__ = ["TalosNodeConfig", "generate_talos_config", "main", "inv"]

logger = logging.getLogger(__name__)


# What `talosctl gen config` uses at Talos v1.14.5: the Image Factory metal
# installer with the empty schematic (images.InstallerImage("metal")); the
# ghcr.io/siderolabs/installer image is no longer published from v1.14 (TAL-4).
DEFAULT_INSTALLER_IMAGE = "factory.talos.dev/metal-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.5@sha256:4104d57b40ade79b577a7a18224da505df4e1eb9c9bc1a74fe3afcc3e11b4ba7"
VALID_NODE_TYPES = frozenset({"controlplane", "worker", "init"})

# Talos list fields that may be written as dicts keyed by their natural key.
# The generator normalizes the dict form to the list form Talos expects.
# Keyed by (parent field, field) so unrelated user dicts that merely share a
# field name (e.g. a 'routes' map inside kubelet extraConfig) stay untouched.
TALOS_KEYED_LIST_POSITIONS = {
    ("apiServer", "admissionControl"): "name",
    ("network", "extraHostEntries"): "ip",
    ("kubelet", "extraMounts"): "destination",
    ("install", "extensions"): "image",
    ("machine", "files"): "path",
    ("cluster", "inlineManifests"): "name",
    ("network", "interfaces"): "interface",
    ("interfaces", "routes"): "network",
    ("interfaces", "vlans"): "vlanId",
    ("vlans", "routes"): "network",
    ("machine", "seccompProfiles"): "name",
}


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def convert_to_plain_dict(obj: Any) -> Any:
    """Convert OmegaConf or dict-like objects to plain Python dicts recursively."""
    if obj is None:
        return None
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        from omegaconf import OmegaConf

        return convert_to_plain_dict(OmegaConf.to_container(obj, resolve=True))
    if hasattr(obj, "items") and callable(obj.items):
        return {k: convert_to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)) or (
        hasattr(obj, "__iter__") and not isinstance(obj, str)
    ):
        return [convert_to_plain_dict(item) for item in obj]
    return obj


def _kernel_arg_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _normalize_extra_kernel_args(value: Any) -> Any:
    """Normalize ``extraKernelArgs`` given as a dict to the list form."""
    args = convert_to_plain_dict(value)
    if not isinstance(args, dict):
        if isinstance(args, list):
            return [_kernel_arg_value(item) for item in args]
        return args

    normalized = []
    for key, arg_value in args.items():
        if arg_value is None or arg_value is True:
            normalized.append(str(key))
        else:
            normalized.append(f"{key}={_kernel_arg_value(arg_value)}")
    return normalized


def _normalize_keyed_list(value: Any, key_field: str) -> Any:
    """Normalize a dict keyed by *key_field* values to the list form.

    Items are returned unrecursed; the caller re-normalizes the result
    with the proper parent context.
    """
    items = convert_to_plain_dict(value)
    if not isinstance(items, dict):
        return items

    normalized = []
    for item_key, item_value in items.items():
        item_config = convert_to_plain_dict(item_value)
        if not isinstance(item_config, dict):
            item_config = {"value": item_config}
        key_value: Any = str(item_key)
        # vlanId is numeric in the Talos schema; dict keys arrive as strings
        if key_field == "vlanId" and key_value.isdigit():
            key_value = int(key_value)
        item_config.setdefault(key_field, key_value)
        normalized.append(item_config)
    return normalized


def _normalize_talos_schema(value: Any, parent: str = "") -> Any:
    """Recursively normalize friendly inventory forms to Talos schema forms.

    *parent* is the enclosing field name; keyed-list normalization only
    applies at known (parent, field) schema positions so unrelated user
    dicts sharing a field name pass through untouched.
    """
    data = convert_to_plain_dict(value)
    if isinstance(data, list):
        return [_normalize_talos_schema(item, parent) for item in data]
    if not isinstance(data, dict):
        return data

    result: dict[str, Any] = {}
    for key, item in data.items():
        if parent == "install" and key == "extraKernelArgs":
            result[key] = _normalize_extra_kernel_args(item)
        elif (parent, key) in TALOS_KEYED_LIST_POSITIONS:
            normalized = _normalize_keyed_list(
                item, TALOS_KEYED_LIST_POSITIONS[(parent, key)]
            )
            result[key] = _normalize_talos_schema(normalized, key)
        else:
            result[key] = _normalize_talos_schema(item, key)
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict with *override* deep-merged over *base*.

    Dicts merge recursively; any other value (including lists) from
    *override* replaces the base value. Neither input is mutated.
    """
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_node_shorthands(name: str, config: dict, result: dict) -> None:
    """Apply node-level ``hostname``/``ip`` shorthands onto the built config.

    Shorthands win over values inherited from the shared base or set in
    the nested machine config; a warning is logged when they override a
    differing value.
    """
    hostname = config.get("hostname")
    if hostname:
        network = result["machine"].setdefault("network", {})
        existing = network.get("hostname")
        if existing and existing != hostname:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                "hostname",
                "machine.network.hostname",
                name,
            )
        network["hostname"] = hostname

    ip = config.get("ip")
    if ip:
        addresses = [str(a) for a in ip] if isinstance(ip, list) else [str(ip)]
        interfaces = result["machine"].get("network", {}).get("interfaces") or []
        if len(interfaces) != 1:
            raise ValueError(
                f"node '{name}': the 'ip' shorthand needs exactly one "
                f"machine.network.interfaces entry (found {len(interfaces)}); "
                "set per-interface addresses explicitly instead"
            )
        interface = interfaces[0]
        existing_addresses = interface.get("addresses")
        if existing_addresses and existing_addresses != addresses:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                "ip",
                "machine.network.interfaces[0].addresses",
                name,
            )
        interface["addresses"] = addresses


class _UserdataDumper(yaml.SafeDumper):
    """YAML dumper for userdata strings; keeps multiline scalars literal."""


def _represent_str(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_UserdataDumper.add_representer(str, _represent_str)


def _build_userdata_secret(
    node_name: str, secret_config: dict, rendered: list
) -> tuple[str, dict]:
    """Build a KubeVirt userdata Secret wrapping a rendered machine config.

    Returns the output key (``<namespace>/<name>-secret``) and the Secret document.
    The machine config is dumped with ``sort_keys=False`` and literal block
    style for multiline strings so certs and machine files stay readable.
    """
    name = secret_config.get("name")
    namespace = secret_config.get("namespace")
    if not name or not namespace:
        raise ValueError(
            f"node '{node_name}': userdataSecret needs both 'name' and 'namespace'"
        )
    userdata = yaml.dump_all(
        rendered, Dumper=_UserdataDumper, sort_keys=False, default_flow_style=False
    )
    return f"{namespace}/{name}-secret", {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"name": name},
        },
        "stringData": {"userdata": userdata},
    }


def _strip_worker_cluster_keys(result: dict[str, Any]) -> None:
    """Remove the cluster CA private key and etcd config from worker cluster sections."""
    if "ca" in result:
        result["ca"] = {k: v for k, v in result["ca"].items() if k != "key"}
    result.pop("etcd", None)


def _validate_node_type(node_type: str, node_name: str) -> None:
    """Validate the node type is one of the allowed Talos machine types."""
    if node_type not in VALID_NODE_TYPES:
        raise ValueError(
            f"Invalid node type '{node_type}' for node '{node_name}'. "
            f"Must be one of: {sorted(VALID_NODE_TYPES)}"
        )


class TalosNodeConfig:
    """Builder for Talos v1alpha1 machine configuration files.

    Generates configuration suitable for use with `talosctl apply-config`.
    Config is structured with top-level `machine` and `cluster` sections.

    Required kwargs: name, config
    """

    def __init__(self, name: str, config: dict):
        """Initialize the Talos node config builder.

        Args:
            name: Node name (used as output filename)
            config: Configuration dictionary from inventory
        """
        self.name = name
        self.config = convert_to_plain_dict(config)
        self.node_type = self.config.get("type", "worker")
        _validate_node_type(self.node_type, name)

    def build(self) -> dict:
        """Build the complete Talos machine configuration.

        Returns:
            Dictionary containing full Talos v1alpha1 configuration
        """
        result: dict[str, Any] = {
            "version": "v1alpha1",
            "debug": self.config.get("debug", False),
        }

        machine_config = self.config.get("machine", {})
        result["machine"] = self._build_machine_section(machine_config)

        cluster_config = self.config.get("cluster", {})
        if cluster_config:
            result["cluster"] = self._build_cluster_section(cluster_config)

        return result

    def _build_machine_section(self, machine: dict) -> dict:
        """Build the machine section of the Talos config.

        All user keys pass through; only ``type`` and ``install`` receive
        special handling. A whitelist here would
        silently drop fields like ``systemDiskEncryption`` or ``disks``.
        """
        result: dict[str, Any] = {
            "type": self.node_type,
        }

        for key, value in machine.items():
            if key in ("type", "install"):
                continue
            result[key] = value

        # Disk installation settings
        result["install"] = self._build_install(machine.get("install", {}))

        # Workers should not carry the machine CA private key.
        if self.node_type == "worker" and result.get("ca"):
            result["ca"] = {k: v for k, v in result["ca"].items() if k != "key"}

        return result

    def _build_install(self, install: dict) -> dict:
        """Build the machine.install subsection with sensible defaults."""
        result: dict[str, Any] = {}

        # Default the install disk only when no diskSelector is given —
        # disk and diskSelector are mutually exclusive in Talos.
        if "disk" in install:
            result["disk"] = install["disk"]
        elif "diskSelector" not in install:
            logger.warning(
                "machine.install.disk not set; defaulting to /dev/sda. This "
                "default is deprecated and will be removed - set install.disk "
                "or install.diskSelector explicitly."
            )
            result["disk"] = "/dev/sda"

        result["image"] = install.get("image", DEFAULT_INSTALLER_IMAGE)
        result.update({k: v for k, v in install.items() if k not in result})

        return result

    def _build_cluster_section(self, cluster: dict) -> dict:
        """Build the cluster section of the Talos config.

        All user keys pass through; worker nodes get sensitive keys stripped.
        """
        result: dict[str, Any] = dict(cluster)

        # Workers should not carry cluster CA private keys or etcd config.
        if self.node_type == "worker":
            _strip_worker_cluster_keys(result)

        return result


def generate_talos_config(name: str, config: dict) -> dict:
    """Generate a Talos machine configuration dictionary.

    Args:
        name: Node name
        config: Configuration dictionary from inventory

    Returns:
        Talos v1alpha1 machine configuration dictionary
    """
    builder = TalosNodeConfig(name, config)
    result = cast("dict", _normalize_talos_schema(builder.build()))
    _apply_node_shorthands(name, builder.config, result)
    return result


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for Kapitan kadet.

    Reads node configs from generators.talos.nodes (legacy: parameters.talos_nodes)
    and generates machine configuration files.

    Args:
        input_params: Optional input parameters (unused)

    Returns:
        BaseObj containing generated Talos machine configurations
    """
    from kapitan.inputs.kadet import BaseObj

    obj = BaseObj()

    talos_config = inv.parameters.get("generators", {}).get("talos", {}) or {}
    base_config = convert_to_plain_dict(talos_config.get("base") or {})
    talos_nodes = dict(talos_config.get("nodes") or {})

    legacy_nodes = inv.parameters.get("talos_nodes", {}) or {}
    if legacy_nodes:
        logger.warning(
            "parameters.talos_nodes is deprecated; move node configs to "
            "generators.talos.nodes"
        )
        for node_name, node_config in legacy_nodes.items():
            talos_nodes.setdefault(node_name, node_config)

    userdata_secrets: list[tuple[str, dict]] = []
    for node_name, node_config in talos_nodes.items():
        merged = _deep_merge(base_config, convert_to_plain_dict(node_config) or {})
        secret_config = merged.pop("userdataSecret", None)
        rendered = multidoc.split(node_name, generate_talos_config(node_name, merged))
        obj.root[node_name] = rendered
        if secret_config:
            userdata_secrets.append(
                _build_userdata_secret(node_name, secret_config, rendered)
            )

    for key, secret in userdata_secrets:
        _add_output_doc(obj, key, secret)

    for patch_name, patch in (talos_config.get("patches") or {}).items():
        _add_output_doc(obj, patch_name, _normalize_talos_schema(patch))

    for doc_key in ("secrets", "talosconfig"):
        doc = talos_config.get(doc_key)
        if doc:
            _add_output_doc(obj, doc_key, convert_to_plain_dict(doc))

    return obj


def _add_output_doc(obj: BaseObj, key: str, doc: Any) -> None:
    """Add an extra output document, warning if it collides with a node output."""
    if key in obj.root:
        logger.warning(
            "output '%s' already exists (node and patch/document share the "
            "name?); the later document wins",
            key,
        )
    obj.root[key] = doc
