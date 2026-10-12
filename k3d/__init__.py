"""K3d Cluster Configuration Generator for Kapitan.

This module generates k3d configuration files from Kapitan inventory parameters.
K3d is a lightweight wrapper to run k3s (Rancher Lab's minimal Kubernetes distribution)
in Docker, making it easy to create local Kubernetes clusters for development.

Usage:
    1. Fetch the generator to lib/k3d and compile it with input_type kadet
    2. Define clusters under parameters.generators.k3d.clusters
    3. Run kapitan compile

Example inventory:
    parameters:
      generators:
        k3d:
          clusters:
            dev-cluster:
              servers: 1
              agents: 2
              ports:
                - port: "8080:80"
                  nodeFilters: ["loadbalancer"]
"""

__version__ = "1.0.0"

import logging
from typing import Any, Optional

from kapitan.inputs.kadet import BaseObj, inventory


inv = inventory()
logger = logging.getLogger(__name__)


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


# Node-filtered lists whose items accept the generic `value` alias
_LIST_VALUE_KEYS = {"volumes": "volume", "ports": "port", "env": "envVar"}


def _dropped_keys(src: Any, out: Any, path: str = "") -> list[str]:
    """Return the paths of inventory keys the builder did not copy into the output."""
    if isinstance(src, list) and isinstance(out, list):
        return [
            key
            for i, (item, built) in enumerate(zip(src, out))
            for key in _dropped_keys(item, built, f"{path}[{i}]")
        ]
    if not (isinstance(src, dict) and isinstance(out, dict)):
        return []
    value_key = _LIST_VALUE_KEYS.get(path.split("[", maxsplit=1)[0])
    dropped = []
    for key, value in src.items():
        child = f"{path}.{key}" if path else key
        if key in out:
            dropped += _dropped_keys(value, out[key], child)
        elif key != "value" or value_key is None or value_key in src:
            dropped.append(child)
    return dropped


class K3dClusterConfig:
    """Builder for k3d cluster configuration files.

    This class constructs a valid k3d configuration YAML from inventory parameters,
    following the k3d.io/v1alpha5 API specification.
    """

    def __init__(self, name: str, config: dict):
        """Initialize the K3d cluster config builder.

        Args:
            name: Name of the cluster
            config: Configuration dictionary from inventory
        """
        self.name = name
        self.config = _convert_to_dict(config)

    def build(self) -> dict:
        """Build the complete k3d configuration.

        Returns:
            Dictionary containing valid k3d configuration
        """
        result: dict[str, Any] = {
            "apiVersion": "k3d.io/v1alpha5",
            "kind": "Simple",
            "metadata": {"name": self.name},
        }

        # Basic cluster settings
        if "servers" in self.config:
            result["servers"] = self.config["servers"]
        if "agents" in self.config:
            result["agents"] = self.config["agents"]
        if "image" in self.config:
            result["image"] = self.config["image"]
        if "network" in self.config:
            result["network"] = self.config["network"]
        if "subnet" in self.config:
            result["subnet"] = self.config["subnet"]
        if "token" in self.config:
            result["token"] = self.config["token"]

        # Kubernetes API exposure
        if "kubeAPI" in self.config:
            result["kubeAPI"] = self._build_kube_api(self.config["kubeAPI"])

        # Volumes
        if "volumes" in self.config:
            result["volumes"] = self._build_node_filtered_list(
                self.config["volumes"], "volume"
            )

        # Ports
        if "ports" in self.config:
            result["ports"] = self._build_node_filtered_list(
                self.config["ports"], "port"
            )

        # Environment variables
        if "env" in self.config:
            result["env"] = self._build_node_filtered_list(self.config["env"], "envVar")

        # Files to copy into nodes
        if "files" in self.config:
            result["files"] = self._build_files(self.config["files"])

        # Registries
        if "registries" in self.config:
            result["registries"] = self._build_registries(self.config["registries"])

        # Host aliases
        if "hostAliases" in self.config:
            result["hostAliases"] = self._build_host_aliases(self.config["hostAliases"])

        # Options
        if "options" in self.config:
            result["options"] = self._build_options(self.config["options"])

        return result

    def _build_kube_api(self, kube_api: dict) -> dict:
        """Build kubeAPI configuration section."""
        result = {}
        for key in ["host", "hostIP", "hostPort"]:
            if key in kube_api:
                result[key] = str(kube_api[key])
        return result

    def _build_node_filtered_list(
        self, items: list, value_key: str
    ) -> list[dict[str, Any]]:
        """Build a list of items with optional node filters.

        Args:
            items: List of items (can be dicts or simple values)
            value_key: The key name for the value (e.g., 'volume', 'port', 'envVar')

        Returns:
            List of properly formatted items with node filters
        """
        result = []
        for item in items:
            if isinstance(item, dict):
                entry: dict[str, Any] = {}
                if value_key in item:
                    entry[value_key] = str(item[value_key])
                elif "value" in item:
                    entry[value_key] = str(item["value"])
                if "nodeFilters" in item:
                    entry["nodeFilters"] = item["nodeFilters"]
                result.append(entry)
            else:
                # Simple value without node filter
                result.append({value_key: str(item)})
        return result

    def _build_files(self, files: list) -> list[dict[str, Any]]:
        """Build files configuration section."""
        result = []
        for file_item in files:
            entry: dict[str, Any] = {
                "source": file_item["source"],
                "destination": file_item["destination"],
            }
            if "description" in file_item:
                entry["description"] = file_item["description"]
            if "nodeFilters" in file_item:
                entry["nodeFilters"] = file_item["nodeFilters"]
            result.append(entry)
        return result

    def _build_registries(self, registries: dict) -> dict:
        """Build registries configuration section."""
        result: dict[str, Any] = {}

        if "create" in registries:
            create_config = registries["create"]
            result["create"] = {}
            for key in [
                "name",
                "host",
                "hostPort",
                "image",
                "volumes",
                "enforcePortMatch",
            ]:
                if key in create_config:
                    result["create"][key] = create_config[key]
            if "proxy" in create_config:
                result["create"]["proxy"] = {}
                for key in ["remoteURL", "username", "password"]:
                    if key in create_config["proxy"]:
                        result["create"]["proxy"][key] = create_config["proxy"][key]

        if "use" in registries:
            result["use"] = registries["use"]

        if "config" in registries:
            result["config"] = registries["config"]

        return result

    def _build_host_aliases(self, host_aliases: list) -> list[dict[str, Any]]:
        """Build hostAliases configuration section."""
        result = []
        for alias in host_aliases:
            entry: dict[str, Any] = {"ip": alias["ip"]}
            if "hostnames" in alias:
                entry["hostnames"] = alias["hostnames"]
            result.append(entry)
        return result

    def _build_options(self, options: dict) -> dict:
        """Build options configuration section."""
        result: dict[str, Any] = {}

        if "k3d" in options:
            result["k3d"] = self._build_k3d_options(options["k3d"])

        if "k3s" in options:
            result["k3s"] = self._build_k3s_options(options["k3s"])

        if "kubeconfig" in options:
            result["kubeconfig"] = {}
            for key in ["updateDefaultKubeconfig", "switchCurrentContext"]:
                if key in options["kubeconfig"]:
                    result["kubeconfig"][key] = options["kubeconfig"][key]

        if "runtime" in options:
            result["runtime"] = self._build_runtime_options(options["runtime"])

        return result

    def _build_k3d_options(self, k3d_opts: dict) -> dict:
        """Build k3d-specific options."""
        result: dict[str, Any] = {}
        for key in [
            "wait",
            "timeout",
            "disableLoadbalancer",
            "disableImageVolume",
            "disableRollback",
        ]:
            if key in k3d_opts:
                result[key] = k3d_opts[key]

        if "loadbalancer" in k3d_opts:
            result["loadbalancer"] = {}
            if "configOverrides" in k3d_opts["loadbalancer"]:
                result["loadbalancer"]["configOverrides"] = k3d_opts["loadbalancer"][
                    "configOverrides"
                ]

        return result

    def _build_k3s_options(self, k3s_opts: dict) -> dict:
        """Build k3s-specific options."""
        result: dict[str, Any] = {}

        if "extraArgs" in k3s_opts:
            result["extraArgs"] = []
            for arg in k3s_opts["extraArgs"]:
                entry: dict[str, Any] = {"arg": arg["arg"]}
                if "nodeFilters" in arg:
                    entry["nodeFilters"] = arg["nodeFilters"]
                result["extraArgs"].append(entry)

        if "nodeLabels" in k3s_opts:
            result["nodeLabels"] = []
            for label in k3s_opts["nodeLabels"]:
                entry = {"label": label["label"]}
                if "nodeFilters" in label:
                    entry["nodeFilters"] = label["nodeFilters"]
                result["nodeLabels"].append(entry)

        return result

    def _build_runtime_options(self, runtime_opts: dict) -> dict:
        """Build runtime-specific options."""
        result: dict[str, Any] = {}

        for key in ["gpuRequest", "serversMemory", "agentsMemory", "hostPidMode"]:
            if key in runtime_opts:
                result[key] = runtime_opts[key]

        if "labels" in runtime_opts:
            result["labels"] = []
            for label in runtime_opts["labels"]:
                entry: dict[str, Any] = {"label": label["label"]}
                if "nodeFilters" in label:
                    entry["nodeFilters"] = label["nodeFilters"]
                result["labels"].append(entry)

        if "ulimits" in runtime_opts:
            result["ulimits"] = []
            for ulimit in runtime_opts["ulimits"]:
                entry = {}
                for key in ["name", "soft", "hard"]:
                    if key in ulimit:
                        entry[key] = ulimit[key]
                result["ulimits"].append(entry)

        return result


def generate_k3d_config(name: str, config: dict) -> dict:
    """Generate a k3d configuration dictionary.

    Args:
        name: Cluster name
        config: Configuration from inventory

    Returns:
        k3d configuration dictionary
    """
    builder = K3dClusterConfig(name, config)
    return builder.build()


def main(input_params: Optional[dict] = None) -> BaseObj:
    """Main entry point for the kadet generator.

    Generates k3d cluster configuration files from inventory parameters.

    Args:
        input_params: Optional input parameters (unused, for compatibility)

    Returns:
        BaseObj containing generated k3d configuration files
    """
    obj = BaseObj()

    # Get k3d clusters configuration from inventory
    clusters_config = (
        inv.parameters.get("generators", {}).get("k3d", {}).get("clusters", {})
    )

    if not clusters_config:
        return obj

    clusters_plain = _convert_to_dict(clusters_config)

    for cluster_name, cluster_config in clusters_plain.items():
        builder = K3dClusterConfig(cluster_name, cluster_config)
        config = builder.build()

        dropped = _dropped_keys(builder.config, config)
        if dropped:
            logger.warning(
                "k3d cluster '%s': dropped keys outside k3d v1alpha5: %s",
                cluster_name,
                ", ".join(dropped),
            )

        # Store config dict directly - Kapitan will serialize to YAML
        obj.root[f"{cluster_name}"] = config

    return obj


__all__ = [
    "K3dClusterConfig",
    "_convert_to_dict",
    "generate_k3d_config",
    "inv",
    "main",
]
