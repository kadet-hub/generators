"""Calico / Tigera Operator generator for Kapitan.

Generates resources for the Tigera operator that manages Calico CNI:
- Installation: Core networking and network policy configuration (must be named "default")
- APIServer: Enables the Calico API server for advanced policy management
- ImageSet: Pins Calico images by digest for security/compliance

Tigera operator installs and manages Calico (or Calico Enterprise / TigeraSecureEnterprise)
on Kubernetes clusters.

Schema reference: operator.tigera.io/v1
Built for Calico v3.33.0 (Tigera operator v1.44.0).
See: https://docs.tigera.io/calico/3.33/reference/installation/api
     https://github.com/tigera/operator/tree/v1.44.0
"""

__version__ = "1.0.0"

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


inv = inventory()
logger = logging.getLogger(__name__)

# =============================================================================
# Valid enum values from schema
# =============================================================================

VALID_VARIANTS = frozenset({"Calico", "CalicoEnterprise", "TigeraSecureEnterprise"})

VALID_CNI_TYPES = frozenset({"Calico", "GKE", "AmazonVPC", "AzureVNET"})

VALID_KUBERNETES_PROVIDERS = frozenset(
    {"", "EKS", "GKE", "AKS", "OpenShift", "DockerEnterprise", "RKE2", "TKG", "Kind"}
)

VALID_BGP_VALUES = frozenset({"Enabled", "Disabled"})

VALID_LINUX_DATAPLANES = frozenset({"Iptables", "BPF", "VPP", "Nftables"})

VALID_ENCAPSULATION_MODES = frozenset(
    {"IPIPCrossSubnet", "IPIP", "VXLAN", "VXLANCrossSubnet", "None"}
)

VALID_NAT_OUTGOING_VALUES = frozenset({"Enabled", "Disabled"})


VALID_IPAM_TYPES = frozenset({"Calico", "HostLocal", "AmazonVPC", "AzureVNET"})

_PROVIDER_CNI_TYPES = {"AKS": "AzureVNET", "EKS": "AmazonVPC", "GKE": "GKE"}


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj/kadet objects to plain dicts."""
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


def _validate_enum(value: Any, valid_values: frozenset, field_name: str) -> None:
    """Validate that a value is in a set of valid enum values."""
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            f"Must be one of: {', '.join(sorted(str(v) for v in valid_values))}"
        )


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge user-provided `spec` dict into the resource spec verbatim."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when a flat abstraction key would overwrite a value from `spec`."""
    spec = _convert_to_dict(config.get("spec")) or {}
    if not spec:
        return
    flat = _convert_to_dict(config)
    for flat_key, crd_key in mapping.items():
        flat_value, spec_value = flat, spec
        for part in flat_key.split("."):
            flat_value = flat_value.get(part) if isinstance(flat_value, dict) else None
        for part in crd_key.split("."):
            spec_value = spec_value.get(part) if isinstance(spec_value, dict) else None
        if flat_value is not None and spec_value is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


# Fields whose CRD spelling deviates from plain camelCase (acronyms)
_CAMEL_OVERRIDES = {
    "container_ip_forwarding": "containerIPForwarding",
}


def _snake_to_camel(field: str) -> str:
    """Convert snake_case to camelCase (with CRD acronym overrides)."""
    if field in _CAMEL_OVERRIDES:
        return _CAMEL_OVERRIDES[field]
    return "".join(
        word.capitalize() if i else word for i, word in enumerate(field.split("_"))
    )


# =============================================================================
# Base Tigera Resource Class
# =============================================================================


class TigeraBase(k8s.Base):
    """Base class for Tigera operator resources."""

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", inv.parameters.get("namespace"))

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Add common metadata fields.

        Most Tigera operator CRDs are cluster-scoped; callers pass
        include_namespace=False for those.
        """
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# =============================================================================
# Installation
# =============================================================================


class Installation(TigeraBase):
    """Tigera operator Installation resource.

    Configures core networking and network policy components for Calico or
    Calico Enterprise.  The resource **must** be named ``default`` (enforced
    by the operator).

    Required kwargs:
        name: Resource name (should be "default").
        config: Installation configuration dictionary.

    Example config::

        calico:
          variant: Calico
          kubernetes_provider: ""
          cni:
            type: Calico
          calico_network:
            bgp: Enabled
            ip_pools:
              - cidr: 10.244.0.0/16
                encapsulation: VXLANCrossSubnet
                nat_outgoing: Enabled
                node_selector: "all()"
    """

    _FLAT_KEY_MAP = {
        "variant": "variant",
        "kubernetes_provider": "kubernetesProvider",
        "registry": "registry",
        "image_path": "imagePath",
        "image_prefix": "imagePrefix",
        "image_pull_secrets": "imagePullSecrets",
        "cni": "cni",
        "calico_network": "calicoNetwork",
        "control_plane_replicas": "controlPlaneReplicas",
        "fips_mode": "fipsMode",
        "non_privileged": "nonPrivileged",
        "flex_volume_path": "flexVolumePath",
        "kubelet_volume_plugin_path": "kubeletVolumePluginPath",
        "service_cidrs": "serviceCIDRs",
        "control_plane_tolerations": "controlPlaneTolerations",
        "control_plane_node_selector": "controlPlaneNodeSelector",
        "calico_node_daemon_set": "calicoNodeDaemonSet",
        "calico_kube_controllers_deployment": "calicoKubeControllersDeployment",
        "typha_deployment": "typhaDeployment",
        "certificate_management": "certificateManagement",
        "node_update_strategy": "nodeUpdateStrategy",
        "node_metrics_port": "nodeMetricsPort",
        "logging": "logging",
        "proxy": "proxy",
        "azure": "azure",
    }

    _NETWORK_KEYS = frozenset(
        {
            "bgp",
            "mtu",
            "linux_dataplane",
            "ip_pools",
            "host_ports",
            "node_address_autodetection_v4",
            "node_address_autodetection_v6",
            "container_ip_forwarding",
            "multi_interface_mode",
            "windows_dataplane",
        }
    )

    _IP_POOL_KEYS = frozenset(
        {
            "cidr",
            "encapsulation",
            "nat_outgoing",
            "node_selector",
            "block_size",
            "disable_bgp_export",
        }
    )

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "operator.tigera.io/v1"
        self.kwargs.kind = "Installation"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=False)
        self._build_spec(config)

    def _build_spec(self, config: dict) -> None:
        """Build the Installation spec."""
        spec = self.root.spec

        # 1. Passthrough — merge any unmodelled fields first.
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # 2. Explicit abstractions — flat keys take precedence.
        # Defaults are applied only when the field is absent after passthrough.

        # variant
        flat_variant = config.get("variant")
        if flat_variant is not None:
            _validate_enum(flat_variant, VALID_VARIANTS, "variant")
            spec.variant = flat_variant

        # kubernetesProvider
        kubernetes_provider = config.get("kubernetes_provider")
        if kubernetes_provider is not None:
            _validate_enum(
                kubernetes_provider, VALID_KUBERNETES_PROVIDERS, "kubernetesProvider"
            )
            spec.kubernetesProvider = kubernetes_provider

        # registry / imagePath / imagePrefix
        for field in ("registry", "image_path", "image_prefix"):
            value = config.get(field)
            if value is not None:
                spec[_snake_to_camel(field)] = value

        # imagePullSecrets
        pull_secrets = config.get("image_pull_secrets")
        if pull_secrets:
            spec.imagePullSecrets = [
                {"name": s} if isinstance(s, str) else _convert_to_dict(s)
                for s in pull_secrets
            ]

        # CNI plugin configuration
        cni_config = config.get("cni")
        if cni_config:
            self._build_cni(spec, _convert_to_dict(cni_config))

        # calicoNetwork
        calico_network = config.get("calico_network")
        if calico_network:
            self._build_calico_network(spec, _convert_to_dict(calico_network))

        # controlPlaneReplicas
        replicas = config.get("control_plane_replicas")
        if replicas is not None:
            spec.controlPlaneReplicas = replicas

        # fipsMode
        fips_mode = config.get("fips_mode")
        if fips_mode is not None:
            spec.fipsMode = fips_mode

        # nonPrivileged
        non_privileged = config.get("non_privileged")
        if non_privileged is not None:
            spec.nonPrivileged = non_privileged

        # flexVolumePath / kubeletVolumePluginPath
        flex_path = config.get("flex_volume_path")
        if flex_path is not None:
            spec.flexVolumePath = flex_path

        kubelet_path = config.get("kubelet_volume_plugin_path")
        if kubelet_path is not None:
            spec.kubeletVolumePluginPath = kubelet_path

        # serviceCIDRs
        service_cidrs = config.get("service_cidrs")
        if service_cidrs:
            spec.serviceCIDRs = service_cidrs

        # controlPlaneTolerations
        tolerations = config.get("control_plane_tolerations")
        if tolerations:
            spec.controlPlaneTolerations = _convert_to_dict(tolerations)

        # controlPlaneNodeSelector
        node_selector = config.get("control_plane_node_selector")
        if node_selector:
            spec.controlPlaneNodeSelector = _convert_to_dict(node_selector)

        # Pass-through fields (advanced overrides)
        for field in (
            "calico_node_daemon_set",
            "calico_kube_controllers_deployment",
            "typha_deployment",
            "certificate_management",
            "node_update_strategy",
            "node_metrics_port",
            "logging",
            "proxy",
            "azure",
        ):
            value = config.get(field)
            if value is not None:
                spec[_snake_to_camel(field)] = _convert_to_dict(value)

    _CNI_KEYS = frozenset({"type", "bin_dir", "conf_dir", "ipam"})

    def _build_cni(self, spec: Any, cni: dict) -> None:
        """Build the spec.cni sub-section."""
        # Unmodelled keys pass through verbatim; modelled keys below win.
        cni_spec: dict[str, Any] = {
            k: v for k, v in cni.items() if k not in self._CNI_KEYS
        }

        cni_type = cni.get("type")
        if cni_type is not None:
            _validate_enum(cni_type, VALID_CNI_TYPES, "cni.type")
            cni_spec["type"] = cni_type
        else:
            # cni.type is required by the CRD once cni is set. Use the operator's
            # own default for the provider (fillDefaults in
            # https://github.com/tigera/operator/blob/v1.44.0/pkg/controller/installation/core_controller.go).
            # A type from spec.cni ranks above this default.
            spec_type = (spec.get("cni") or {}).get("type")
            cni_spec["type"] = spec_type or _PROVIDER_CNI_TYPES.get(
                spec.get("kubernetesProvider"), "Calico"
            )

        for field in ("bin_dir", "conf_dir"):
            value = cni.get(field)
            if value is not None:
                cni_spec[_snake_to_camel(field)] = value

        ipam = cni.get("ipam")
        if ipam:
            ipam_dict = _convert_to_dict(ipam)
            ipam_type = ipam_dict.get("type")
            if ipam_type:
                _validate_enum(ipam_type, VALID_IPAM_TYPES, "cni.ipam.type")
            cni_spec["ipam"] = ipam_dict

        spec.cni = cni_spec

    def _build_calico_network(self, spec: Any, network: dict) -> None:
        """Build the spec.calicoNetwork sub-section."""
        # Unmodelled keys pass through verbatim; modelled keys below win.
        calico_net: dict[str, Any] = {
            k: v for k, v in network.items() if k not in self._NETWORK_KEYS
        }

        bgp = network.get("bgp")
        if bgp is not None:
            _validate_enum(bgp, VALID_BGP_VALUES, "calicoNetwork.bgp")
            calico_net["bgp"] = bgp

        mtu = network.get("mtu")
        if mtu is not None:
            calico_net["mtu"] = mtu

        linux_dataplane = network.get("linux_dataplane")
        if linux_dataplane is not None:
            _validate_enum(
                linux_dataplane, VALID_LINUX_DATAPLANES, "calicoNetwork.linuxDataplane"
            )
            calico_net["linuxDataplane"] = linux_dataplane

        ip_pools = network.get("ip_pools")
        if ip_pools:
            calico_net["ipPools"] = [
                self._build_ip_pool(pool) for pool in _convert_to_dict(ip_pools)
            ]

        # Pass-through network fields
        for field in (
            "host_ports",
            "node_address_autodetection_v4",
            "node_address_autodetection_v6",
            "container_ip_forwarding",
            "multi_interface_mode",
            "windows_dataplane",
        ):
            value = network.get(field)
            if value is not None:
                calico_net[_snake_to_camel(field)] = _convert_to_dict(value)

        spec.calicoNetwork = calico_net

    def _build_ip_pool(self, pool: dict) -> dict:
        """Build a single IPPool entry for calicoNetwork.ipPools."""
        # Unmodelled keys pass through verbatim; modelled keys below win.
        ip_pool: dict[str, Any] = {
            k: v for k, v in pool.items() if k not in self._IP_POOL_KEYS
        }

        cidr = pool.get("cidr")
        if cidr:
            ip_pool["cidr"] = cidr

        encapsulation = pool.get("encapsulation")
        if encapsulation is not None:
            _validate_enum(
                encapsulation, VALID_ENCAPSULATION_MODES, "ipPool.encapsulation"
            )
            ip_pool["encapsulation"] = encapsulation

        nat_outgoing = pool.get("nat_outgoing")
        if nat_outgoing is not None:
            _validate_enum(
                nat_outgoing, VALID_NAT_OUTGOING_VALUES, "ipPool.natOutgoing"
            )
            ip_pool["natOutgoing"] = nat_outgoing

        node_selector = pool.get("node_selector")
        if node_selector is not None:
            ip_pool["nodeSelector"] = node_selector

        block_size = pool.get("block_size")
        if block_size is not None:
            ip_pool["blockSize"] = block_size

        disable_bgp_export = pool.get("disable_bgp_export")
        if disable_bgp_export is not None:
            ip_pool["disableBGPExport"] = disable_bgp_export

        return ip_pool


# =============================================================================
# APIServer
# =============================================================================


class APIServer(TigeraBase):
    """Tigera operator APIServer resource.

    Enables the Calico API server which provides Kubernetes-style
    CRUD access to Calico resources.

    Required kwargs:
        name: Resource name (should be "default").
        config: APIServer configuration dictionary.

    Example config::

        apiserver:
          {}   # Typically empty; spec is optional
    """

    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "operator.tigera.io/v1"
        self.kwargs.kind = "APIServer"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=False)

        # spec is optional for APIServer (defaults work out-of-the-box)
        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        if not self.root.spec:
            self.root.spec = {}


# =============================================================================
# ImageSet
# =============================================================================


class ImageSet(TigeraBase):
    """Tigera operator ImageSet resource.

    Specifies image digests (SHA256) for the images the operator deploys.
    Used for strict security requirements where images must be referenced
    by immutable digest rather than tags.

    The resource name must follow the format ``<variant>-<release>``
    (e.g. ``calico-v3.33.0``).

    Required kwargs:
        name: Resource name.
        config: ImageSet configuration dictionary.

    Example config::

        imageset:
          images:
            - image: calico/node
              digest: sha256:...
            - image: calico/calico
              digest: sha256:...
    """

    _FLAT_KEY_MAP = {
        "images": "images",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "operator.tigera.io/v1"
        self.kwargs.kind = "ImageSet"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=False)

        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        images = config.get("images")
        if images:
            self.root.spec.images = _convert_to_dict(images)
        elif not self.root.spec:
            self.root.spec = {}


# =============================================================================
# Goldmane and Whisker
# =============================================================================


class _DefaultOnlyResource(TigeraBase):
    """Cluster-scoped operator resource whose name must be ``default``.

    Subclasses set KIND and _FLAT_KEY_MAP (flat key -> spec field).
    """

    KIND = ""
    _FLAT_KEY_MAP: dict[str, str] = {}

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "operator.tigera.io/v1"
        self.kwargs.kind = self.KIND
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=False)

        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for flat_key, crd_key in self._FLAT_KEY_MAP.items():
            if config.get(flat_key) is not None:
                self.root.spec[crd_key] = _convert_to_dict(config[flat_key])
        if not self.root.spec:
            self.root.spec = {}


class Goldmane(_DefaultOnlyResource):
    """Goldmane flow aggregator."""

    KIND = "Goldmane"
    _FLAT_KEY_MAP = {
        "metrics_port": "metricsPort",
        "goldmane_deployment": "goldmaneDeployment",
    }


class Whisker(_DefaultOnlyResource):
    """Whisker observability UI; needs Goldmane."""

    KIND = "Whisker"
    _FLAT_KEY_MAP = {
        "notifications": "notifications",
        "whisker_deployment": "whiskerDeployment",
    }

    def body(self) -> None:
        super().body()
        # Upstream defaults to Enabled, which fetches banner text from an
        # external API; no external call without opt-in.
        if "notifications" not in self.root.spec:
            self.root.spec.notifications = "Disabled"


# =============================================================================
# main()
# =============================================================================


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for Kapitan kadet.

    Reads ``generators.calico`` from inventory and generates:
    - ``Installation`` resource (always, named "default" unless overridden)
    - ``APIServer`` resource (when ``api_server`` key is present)
    - ``ImageSet`` resource (when ``imageset`` key is present)
    - ``Goldmane`` / ``Whisker`` resources (when ``goldmane`` / ``whisker`` is present)

    Args:
        input_params: Optional input parameters (unused).

    Returns:
        BaseObj containing generated Tigera operator resources.
    """
    obj = BaseObj()

    calico_config = inv.parameters.get("generators", {}).get("calico", {}) or {}
    calico_config = _convert_to_dict(calico_config)

    # Installation (named "default" by convention; allow override)
    installation_config = calico_config.get("installation") or {}
    installation_name = installation_config.get("name", "default")
    installation = Installation(name=installation_name, config=installation_config)
    obj.root[f"{installation_name}-installation"] = installation

    # APIServer (optional)
    api_server_config = calico_config.get("api_server")
    if api_server_config is not None:
        api_server_config_dict = _convert_to_dict(api_server_config) or {}
        api_server_name = api_server_config_dict.get("name", "default")
        api_server = APIServer(name=api_server_name, config=api_server_config_dict)
        obj.root[f"{api_server_name}-apiserver"] = api_server

    # ImageSet (optional)
    imageset_config = calico_config.get("imageset")
    if imageset_config is not None:
        imageset_config_dict = _convert_to_dict(imageset_config) or {}
        if "name" not in imageset_config_dict:
            logger.warning(
                "calico ImageSet has no 'name'; using 'default', but the operator "
                "expects '<variant>-<release>' (e.g. calico-v3.33.0)"
            )
        imageset_name = imageset_config_dict.get("name", "default")
        imageset = ImageSet(name=imageset_name, config=imageset_config_dict)
        obj.root[f"{imageset_name}-imageset"] = imageset

    # Goldmane and Whisker (optional)
    for key, resource_class in (("goldmane", Goldmane), ("whisker", Whisker)):
        config = calico_config.get(key)
        if config is None:
            continue
        config = _convert_to_dict(config) or {}
        name = config.get("name", "default")
        obj.root[f"{name}-{key}"] = resource_class(name=name, config=config)
    if "whisker" in calico_config and "goldmane" not in calico_config:
        # The operator degrades Whisker without a Goldmane CR
        # (pkg/controller/whisker/controller.go at v1.44.0).
        logger.warning("calico 'whisker' is set without 'goldmane'; Whisker needs Goldmane")

    return obj


__all__ = [
    "Installation",
    "APIServer",
    "ImageSet",
    "Goldmane",
    "Whisker",
    "TigeraBase",
    "main",
    "inv",
    "k8s",
    "VALID_VARIANTS",
    "VALID_CNI_TYPES",
    "VALID_KUBERNETES_PROVIDERS",
    "VALID_BGP_VALUES",
    "VALID_LINUX_DATAPLANES",
    "VALID_ENCAPSULATION_MODES",
]
