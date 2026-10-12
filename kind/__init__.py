"""KIND Cluster Configuration Generator for Kapitan.

This module generates KIND (Kubernetes IN Docker) configuration files from
Kapitan inventory parameters. KIND is a tool for running local Kubernetes
clusters using Docker container "nodes".

Usage:
    1. Compile lib/kind with input_type kadet
    2. Define clusters under parameters.generators.kind.clusters
    3. Run kapitan compile

Example inventory:
    parameters:
      generators:
        kind:
          clusters:
            dev-cluster:
              nodes:
                - role: control-plane
                - role: worker
                - role: worker
              networking:
                api_server_port: 6443
"""

__version__ = "1.0.0"

import logging
from typing import Any, Optional

from kapitan.inputs.kadet import BaseObj, inventory


logger = logging.getLogger(__name__)

inv = inventory()


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


# Node images pre-built for kind v0.33.0, from its release notes
# (https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0). kind requires
# the @sha256 digest to get an image built for that release.
NODE_IMAGES = {
    "1.37.0": "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5",
    "1.36.4": "kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed",
    "1.35.8": "kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0",
    "1.34.11": "kindest/node:v1.34.11@sha256:44e222ee2132dab25ff87301682f89eb82c7880ea3a1bf543bfe9708fd08d67d",
}


# Valid enum values for validation
VALID_IP_FAMILIES = {"ipv4", "ipv6", "dual"}
VALID_KUBE_PROXY_MODES = {"iptables", "nftables", "ipvs", "none"}
VALID_NODE_ROLES = {"control-plane", "worker"}
VALID_MOUNT_PROPAGATIONS = {"None", "HostToContainer", "Bidirectional"}
VALID_PORT_PROTOCOLS = {"TCP", "UDP", "SCTP"}

# Modelled snake_case inventory keys per object, mapped to their KIND field.
# Other keys are dropped with a warning; upstream fields without a flat key go
# into the cluster's `spec` passthrough. The camelCase field names were the v1
# inventory keys and are rejected with the replacement. `kubernetes_version`
# and `spec` are generator inputs, not KIND fields.
CLUSTER_KEYS = {
    "kubernetes_version": "kubernetes_version",
    "spec": "spec",
    "feature_gates": "featureGates",
    "runtime_config": "runtimeConfig",
    "networking": "networking",
    "nodes": "nodes",
    "containerd_config_patches": "containerdConfigPatches",
    "containerd_config_patches_json6902": "containerdConfigPatchesJSON6902",
}
NETWORKING_KEYS = {
    "ip_family": "ipFamily",
    "api_server_address": "apiServerAddress",
    "api_server_port": "apiServerPort",
    "pod_subnet": "podSubnet",
    "service_subnet": "serviceSubnet",
    "disable_default_cni": "disableDefaultCNI",
    "kube_proxy_mode": "kubeProxyMode",
}
NODE_KEYS = {
    "role": "role",
    "image": "image",
    "kubernetes_version": "kubernetes_version",
    "extra_mounts": "extraMounts",
    "extra_port_mappings": "extraPortMappings",
    "labels": "labels",
    "kubeadm_config_patches": "kubeadmConfigPatches",
    "kubeadm_config_patches_json6902": "kubeadmConfigPatchesJSON6902",
}
MOUNT_KEYS = {
    "host_path": "hostPath",
    "container_path": "containerPath",
    "read_only": "readOnly",
    "selinux_relabel": "selinuxRelabel",
    "propagation": "propagation",
}
PORT_MAPPING_KEYS = {
    "container_port": "containerPort",
    "host_port": "hostPort",
    "listen_address": "listenAddress",
    "protocol": "protocol",
}


_FLAT_NAMES = {
    field: key for keys in (CLUSTER_KEYS, NETWORKING_KEYS) for key, field in keys.items()
}


class KindClusterConfig:
    """Builder for KIND cluster configuration files.

    This class constructs a valid KIND configuration YAML from inventory parameters,
    following the kind.x-k8s.io/v1alpha4 API specification.
    """

    def __init__(self, name: str, config: dict):
        """Initialize the KIND cluster config builder.

        Args:
            name: Name of the cluster
            config: Configuration dictionary from inventory
        """
        self.name = name
        self.config = _convert_to_dict(config)

    def _to_kind_fields(self, section: str, data: dict, key_map: dict) -> dict:
        """Map snake_case inventory keys to KIND fields.

        Raises on a v1 camelCase key; warns about and drops unknown keys.
        """
        replacements = {field: key for key, field in key_map.items() if key != field}
        for key in data:
            if key in replacements:
                raise ValueError(
                    f"Unsupported camelCase {section} key '{key}' for cluster "
                    f"'{self.name}', use '{replacements[key]}'"
                )
        unknown = sorted(set(data) - set(key_map))
        if unknown:
            logger.warning(
                "Ignoring unknown %s keys for cluster '%s': %s",
                section,
                self.name,
                ", ".join(unknown),
            )
        return {key_map[key]: value for key, value in data.items() if key in key_map}

    def build(self) -> dict:
        """Build the complete KIND configuration.

        Returns:
            Dictionary containing valid KIND configuration
        """
        result: dict[str, Any] = {
            "apiVersion": "kind.x-k8s.io/v1alpha4",
            "kind": "Cluster",
        }
        config = self._to_kind_fields("cluster", self.config, CLUSTER_KEYS)

        # Cluster name (optional, can be set via CLI)
        if self.name:
            result["name"] = self.name

        # Feature gates
        if "featureGates" in config:
            result["featureGates"] = config["featureGates"]

        # Runtime config
        if "runtimeConfig" in config:
            result["runtimeConfig"] = config["runtimeConfig"]

        # Networking
        if "networking" in config:
            result["networking"] = self._build_networking(config["networking"])

        # Nodes; with kubernetes_version and no nodes anywhere, kind's default
        # single control-plane node is written out to carry the image
        version = config.get("kubernetes_version")
        nodes = config.get("nodes")
        spec = _convert_to_dict(config.get("spec")) or {}
        if nodes is None and version is not None and "nodes" not in spec:
            nodes = [{"role": "control-plane"}]
        if nodes is not None:
            result["nodes"] = self._build_nodes(nodes, version)

        # Containerd config patches
        if "containerdConfigPatches" in config:
            result["containerdConfigPatches"] = config["containerdConfigPatches"]

        # Containerd config patch templates
        if "containerdConfigPatchesJSON6902" in config:
            result["containerdConfigPatchesJSON6902"] = config[
                "containerdConfigPatchesJSON6902"
            ]

        # spec passthrough first, flat keys on top
        merged = self._merge(spec, result, "")
        return {"apiVersion": result["apiVersion"], "kind": result["kind"], **merged}

    def _merge(self, base: dict, over: dict, path: str) -> dict:
        """Merge flat-key output *over* the spec passthrough *base*, warning per override."""
        out = dict(base)
        for key, value in over.items():
            where = f"{path}.{key}" if path else key
            if isinstance(out.get(key), dict) and isinstance(value, dict):
                out[key] = self._merge(out[key], value, where)
                continue
            if key in out and key not in ("apiVersion", "kind"):
                flat = ".".join(_FLAT_NAMES.get(part, part) for part in where.split("."))
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    flat,
                    where,
                    self.name,
                )
            out[key] = value
        return out

    def _build_networking(self, networking: dict) -> dict:
        """Build networking configuration section.

        Args:
            networking: Networking configuration from inventory

        Returns:
            Formatted networking configuration
        """
        result: dict[str, Any] = {}
        networking = self._to_kind_fields("networking", networking, NETWORKING_KEYS)

        # IP family
        if "ipFamily" in networking:
            ip_family = networking["ipFamily"]
            if ip_family not in VALID_IP_FAMILIES:
                raise ValueError(
                    f"Invalid ip_family '{ip_family}' for cluster '{self.name}'. "
                    f"Must be one of: {', '.join(sorted(VALID_IP_FAMILIES))}"
                )
            result["ipFamily"] = ip_family

        # API server settings
        if "apiServerAddress" in networking:
            result["apiServerAddress"] = networking["apiServerAddress"]
        if "apiServerPort" in networking:
            result["apiServerPort"] = int(networking["apiServerPort"])

        # Subnets
        if "podSubnet" in networking:
            result["podSubnet"] = networking["podSubnet"]
        if "serviceSubnet" in networking:
            result["serviceSubnet"] = networking["serviceSubnet"]

        # CNI settings
        if "disableDefaultCNI" in networking:
            result["disableDefaultCNI"] = bool(networking["disableDefaultCNI"])

        # kube-proxy mode
        if "kubeProxyMode" in networking:
            mode = networking["kubeProxyMode"]
            if mode not in VALID_KUBE_PROXY_MODES:
                raise ValueError(
                    f"Invalid kube_proxy_mode '{mode}' for cluster '{self.name}'. "
                    f"Must be one of: {', '.join(sorted(VALID_KUBE_PROXY_MODES))}"
                )
            result["kubeProxyMode"] = mode

        return result

    def _build_nodes(self, nodes: list, version: Any = None) -> list[dict[str, Any]]:
        """Build nodes configuration section.

        Args:
            nodes: List of node configurations from inventory
            version: Cluster-level kubernetes_version, the default for each node

        Returns:
            List of formatted node configurations
        """
        result = []
        for node in nodes:
            entry = self._build_node(node, version)
            result.append(entry)
        return result

    def _build_node(self, node: dict, version: Any = None) -> dict[str, Any]:
        """Build a single node configuration.

        Args:
            node: Node configuration from inventory

        Returns:
            Formatted node configuration
        """
        entry: dict[str, Any] = {}
        node = self._to_kind_fields("node", node, NODE_KEYS)

        # Role (required for multi-node clusters)
        if "role" in node:
            role = node["role"]
            if role not in VALID_NODE_ROLES:
                raise ValueError(
                    f"Invalid node role '{role}' for cluster '{self.name}'. "
                    f"Must be one of: {', '.join(sorted(VALID_NODE_ROLES))}"
                )
            entry["role"] = role

        # Image (for specific Kubernetes versions); kubernetes_version picks the
        # digest-pinned image of this kind release
        if "image" in node and "kubernetes_version" in node:
            raise ValueError(
                f"Node of cluster '{self.name}' sets both image and kubernetes_version"
            )
        if "image" in node:
            entry["image"] = node["image"]
        elif node.get("kubernetes_version", version) is not None:
            entry["image"] = self._node_image(node.get("kubernetes_version", version))

        # Extra mounts
        if "extraMounts" in node:
            entry["extraMounts"] = self._build_extra_mounts(node["extraMounts"])

        # Extra port mappings
        if "extraPortMappings" in node:
            entry["extraPortMappings"] = self._build_extra_port_mappings(
                node["extraPortMappings"]
            )

        # Extra labels
        if "labels" in node:
            entry["labels"] = node["labels"]

        # Kubeadm config patches
        if "kubeadmConfigPatches" in node:
            entry["kubeadmConfigPatches"] = node["kubeadmConfigPatches"]

        # Kubeadm config patches JSON6902
        if "kubeadmConfigPatchesJSON6902" in node:
            entry["kubeadmConfigPatchesJSON6902"] = node["kubeadmConfigPatchesJSON6902"]

        return entry

    def _node_image(self, version: Any) -> str:
        """Resolve "1.37", "1.37.0" or "v1.37.0" to the kind v0.33.0 node image."""
        wanted = str(version).lstrip("v")
        for full, image in NODE_IMAGES.items():
            if wanted in (full, full.rsplit(".", 1)[0]):
                return image
        raise ValueError(
            f"Unsupported kubernetes_version '{version}' for cluster '{self.name}'. "
            f"kind v0.33.0 ships node images for: {', '.join(NODE_IMAGES)}; "
            "set image for any other version"
        )

    def _build_extra_mounts(self, mounts: list) -> list[dict[str, Any]]:
        """Build extra mounts configuration.

        Args:
            mounts: List of mount configurations

        Returns:
            List of formatted mount configurations
        """
        result = []
        for mount in mounts:
            mount = self._to_kind_fields("extra_mounts", mount, MOUNT_KEYS)
            entry: dict[str, Any] = {
                "hostPath": mount["hostPath"],
                "containerPath": mount["containerPath"],
            }

            # Optional mount settings
            if "readOnly" in mount:
                entry["readOnly"] = bool(mount["readOnly"])
            if "selinuxRelabel" in mount:
                entry["selinuxRelabel"] = bool(mount["selinuxRelabel"])
            if "propagation" in mount:
                propagation = mount["propagation"]
                if propagation not in VALID_MOUNT_PROPAGATIONS:
                    raise ValueError(
                        f"Invalid mount propagation '{propagation}' for cluster "
                        f"'{self.name}'. Must be one of: "
                        f"{', '.join(sorted(VALID_MOUNT_PROPAGATIONS))}"
                    )
                entry["propagation"] = propagation

            result.append(entry)
        return result

    def _build_extra_port_mappings(self, mappings: list) -> list[dict[str, Any]]:
        """Build extra port mappings configuration.

        Args:
            mappings: List of port mapping configurations

        Returns:
            List of formatted port mapping configurations
        """
        result = []
        for mapping in mappings:
            mapping = self._to_kind_fields(
                "extra_port_mappings", mapping, PORT_MAPPING_KEYS
            )
            entry: dict[str, Any] = {
                "containerPort": int(mapping["containerPort"]),
            }

            # Host port (optional, defaults to containerPort)
            if "hostPort" in mapping:
                entry["hostPort"] = int(mapping["hostPort"])

            # Listen address
            if "listenAddress" in mapping:
                entry["listenAddress"] = mapping["listenAddress"]

            # Protocol
            if "protocol" in mapping:
                protocol = mapping["protocol"]
                if protocol not in VALID_PORT_PROTOCOLS:
                    raise ValueError(
                        f"Invalid port protocol '{protocol}' for cluster "
                        f"'{self.name}'. Must be one of: "
                        f"{', '.join(sorted(VALID_PORT_PROTOCOLS))}"
                    )
                entry["protocol"] = protocol

            result.append(entry)
        return result


def generate_kind_config(name: str, config: dict) -> dict:
    """Generate a KIND configuration dictionary.

    Args:
        name: Cluster name
        config: Configuration from inventory

    Returns:
        KIND configuration dictionary
    """
    builder = KindClusterConfig(name, config)
    return builder.build()


def main(input_params: Optional[dict] = None) -> BaseObj:
    """Main entry point for the kadet generator.

    Generates KIND cluster configuration files from inventory parameters.

    Args:
        input_params: Optional input parameters (unused, for compatibility)

    Returns:
        BaseObj containing generated KIND configuration files
    """
    obj = BaseObj()

    # Get KIND clusters configuration from inventory
    clusters_config = (
        inv.parameters.get("generators", {}).get("kind", {}).get("clusters", {})
    )

    if not clusters_config:
        return obj

    clusters_plain = _convert_to_dict(clusters_config)

    for cluster_name, cluster_config in clusters_plain.items():
        builder = KindClusterConfig(cluster_name, cluster_config)
        config = builder.build()

        # Store config dict directly - Kapitan will serialize to YAML
        obj.root[f"{cluster_name}"] = config

    return obj


__all__ = [
    "KindClusterConfig",
    "_convert_to_dict",
    "generate_kind_config",
    "inv",
    "main",
]
