"""kMCP MCPServer resource generators for Kapitan.

This module provides classes and functions for generating kMCP MCPServer resources
using Kapitan's kadet input type. Supports both stdio and HTTP transport types.

kMCP is a development platform and control plane for the Model Context Protocol (MCP).
See: https://github.com/kagent-dev/kmcp

Schema reference: kagent.dev/v1alpha1 MCPServer

BACKEND COMPATIBILITY
─────────────────────
The generator must work with ALL valid Kapitan inventory backends:
  - reclass / reclass-rs  → plain Python dicts
  - omegaconf             → OmegaConf DictConfig / ListConfig

RULES for inventory access:
  1. Always use `.get("key", default)` — never direct attribute access.
  2. Always call `_convert_to_dict()` on nested values before passing
     them to resource classes or mutating them.
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


# ─── Helpers ───────────────────────────────────────────────────────────────


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


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge any user-supplied ``spec`` dict into *spec_target*."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when flat keys will override passthrough values from ``spec``."""
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


# Valid enum values from schema
VALID_TRANSPORT_TYPES = ("stdio", "http")

# Schema defaults
DEFAULT_PORT = 3000


class MCPServer(k8s.Base):
    """kMCP MCPServer resource.

    Generates an MCPServer custom resource for deploying MCP servers in Kubernetes.

    Smart defaults to reduce configuration duplication:
        - http_transport.target_port defaults to deployment.port
        - deployment.port defaults to 3000

    Required kwargs:
        name: Resource name.
        mcpserver: MCPServer configuration dictionary.

    Minimal HTTP transport example (no duplication):
        {
            'transport_type': 'http',
            'deployment': {
                'image': 'my-server:latest',
                'port': 8080,  # http_transport.target_port inherits this
            },
        }
    """

    _FLAT_KEY_MAP = {
        "transport_type": "transportType",
        **{
            f"deployment.{key}": f"deployment.{field}"
            for key, field in (
                ("port", "port"),
                ("image", "image"),
                ("image_pull_policy", "imagePullPolicy"),
                ("cmd", "cmd"),
                ("args", "args"),
                ("env", "env"),
                ("volume_mounts", "volumeMounts"),
                ("volumes", "volumes"),
                ("secret_refs", "secretRefs"),
                ("configmap_refs", "configMapRefs"),
                ("init_container", "initContainer"),
                ("service_account", "serviceAccount"),
            )
        },
        "stdio_transport": "stdioTransport",
        "http_transport.target_port": "httpTransport.targetPort",
        "http_transport.target_path": "httpTransport.path",
        "http_transport.path": "httpTransport.path",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kagent.dev/v1alpha1"
        self.kwargs.kind = "MCPServer"
        super().new()

    def body(self) -> None:
        super().body()
        mcpserver = _convert_to_dict(self.kwargs.mcpserver)
        deployment = mcpserver.get("deployment", {})
        default_namespace = self.kwargs.get("default_namespace", "default")

        # Resolve port once - used by both deployment and http transport
        spec_deployment = (_convert_to_dict(mcpserver.get("spec")) or {}).get(
            "deployment"
        ) or {}
        self._resolved_port = deployment.get(
            "port", spec_deployment.get("port", DEFAULT_PORT)
        )

        self.add_namespace(mcpserver.get("namespace", default_namespace))
        self.add_annotations(_convert_to_dict(mcpserver.get("annotations", {})))
        self.add_labels(_convert_to_dict(mcpserver.get("labels", {})))
        self.add_label("app.kubernetes.io/managed-by", "kmcp")
        self.add_label("app.kubernetes.io/component", "mcp-server")

        spec = self.root.spec

        # 1. Passthrough
        _merge_spec_passthrough(spec, mcpserver)

        # 2. Collision warnings
        _warn_collisions(mcpserver, self._FLAT_KEY_MAP, self.kwargs.name)

        # 3. Explicit abstractions — flat keys take precedence over passthrough
        self._build_deployment_spec(deployment)
        self._build_transport_spec(mcpserver)

    def _build_deployment_spec(self, deployment: dict) -> None:
        """Build the deployment section of the MCPServer spec."""
        spec = self.root.spec.deployment

        # Use resolved port; the default must not stomp a passthrough value
        if deployment.get("port") is not None:
            spec.port = deployment.get("port")
        elif "port" not in spec:
            spec.port = self._resolved_port

        # Direct field mappings (snake_case -> camelCase)
        field_mappings = [
            ("image", "image"),
            ("image_pull_policy", "imagePullPolicy"),
            ("cmd", "cmd"),
            ("args", "args"),
            ("env", "env"),
            ("volume_mounts", "volumeMounts"),
            ("volumes", "volumes"),
        ]

        for source_key, target in field_mappings:
            value = deployment.get(source_key)
            if value is not None:
                spec[target] = _convert_to_dict(value)

        # LocalObjectReference fields (auto-wrap string lists)
        self._set_refs(spec, deployment, "secret_refs", target_key="secretRefs")
        self._set_refs(spec, deployment, "configmap_refs", target_key="configMapRefs")

        # Nested object fields
        self._set_nested(
            spec,
            deployment,
            "init_container",
            target_key="initContainer",
            field_map={"image": "image", "image_pull_policy": "imagePullPolicy"},
        )
        self._set_nested(
            spec,
            deployment,
            "service_account",
            target_key="serviceAccount",
            field_map={"annotations": "annotations", "labels": "labels"},
        )

    def _build_transport_spec(self, mcpserver: dict) -> None:
        """Build the transport section of the MCPServer spec."""
        # flat key > spec passthrough > stdio (the controller rejects an
        # empty transportType)
        transport_type = mcpserver.get(
            "transport_type", self.root.spec.get("transportType", "stdio")
        )

        if transport_type not in VALID_TRANSPORT_TYPES:
            raise ValueError(
                f"Invalid transport_type '{transport_type}'. "
                f"Must be one of: {VALID_TRANSPORT_TYPES}"
            )

        self.root.spec.transportType = transport_type

        if transport_type == "stdio":
            self.root.spec.stdioTransport = _convert_to_dict(
                mcpserver.get("stdio_transport", {})
            )

        elif transport_type == "http":
            http_config = mcpserver.get("http_transport", {})
            # keep spec passthrough fields such as tls
            http_transport = _convert_to_dict(self.root.spec.get("httpTransport", {}))

            # targetPort: defaults to deployment.port (deduplication!);
            # the controller rejects an HTTP transport without it
            target_port = http_config.get("target_port")
            if target_port is not None:
                http_transport["targetPort"] = target_port
            elif not http_transport.get("targetPort"):
                http_transport["targetPort"] = self._resolved_port

            # target_path is the documented key; path is accepted as well
            path = http_config.get("target_path", http_config.get("path"))
            if path is not None:
                http_transport["path"] = path
            # Note: path is optional per schema, only set if explicitly provided

            self.root.spec.httpTransport = _convert_to_dict(http_transport)

    def _set_refs(
        self, spec, source: dict, source_key: str, *, target_key: str
    ) -> None:
        """Set LocalObjectReference list field with auto-wrapping."""
        refs = source.get(source_key)
        if refs:
            refs = _convert_to_dict(refs)
            if isinstance(refs, list) and refs and isinstance(refs[0], str):
                spec[target_key] = [{"name": ref} for ref in refs]
            else:
                spec[target_key] = refs

    def _set_nested(
        self,
        spec,
        source: dict,
        source_key: str,
        *,
        target_key: str,
        field_map: dict,
    ) -> None:
        """Set nested object field with field mapping."""
        nested = source.get(source_key)
        if nested is not None:
            nested = _convert_to_dict(nested)
            # If it's a dict with snake_case keys, map them
            if isinstance(nested, dict):
                mapped = {}
                for src, dst in field_map.items():
                    value = nested.get(src)
                    if value is not None:
                        mapped[dst] = _convert_to_dict(value)
                if mapped:
                    spec[target_key] = mapped
            else:
                spec[target_key] = nested


def generate_manifests(input_params) -> BaseObj:
    """Generate MCPServer manifests from inventory parameters.

    Args:
        input_params: Input parameters (unused, reads from inventory).

    Returns:
        BaseObj containing generated MCPServer resources.
    """
    obj = BaseObj()
    kmcp_config = inv.parameters.get("generators", {}).get("kmcp", {}) or {}
    kmcp_config = _convert_to_dict(kmcp_config)
    default_namespace = kmcp_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )
    for name, config in kmcp_config.get("mcpservers", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-mcpserver"] = MCPServer(
            name=name, mcpserver=config, default_namespace=default_namespace
        )
    return obj


def main(input_params) -> BaseObj:
    """Entry point for Kapitan kadet compilation.

    Args:
        input_params: Input parameters from Kapitan.

    Returns:
        BaseObj containing generated resources.
    """
    return generate_manifests(input_params)


__all__ = [
    "MCPServer",
    "generate_manifests",
    "inv",
    "k8s",
    "main",
    "_convert_to_dict",
    "_merge_spec_passthrough",
    "_warn_collisions",
]
