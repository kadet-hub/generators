"""Kubernetes configuration resources: ConfigMap, Secret.

This module provides classes for generating Kubernetes ConfigMap and Secret
resources. Supports versioning for immutable configurations and both
data and stringData fields for secrets.
"""

import re

from . import k8s
from .base import SharedConfig
from .utils import encode_string

# A Kapitan ref (?{backend:path}) is replaced on reveal; encoding it would break that.
KAPITAN_REF = re.compile(r"\?\{[^}]+\}")


class ConfigMap(k8s.Base, SharedConfig):
    """Kubernetes ConfigMap resource.

    Generates a ConfigMap manifest for storing non-confidential configuration data.

    Required kwargs:
        name: ConfigMap name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "ConfigMap"
        super().new()

    def body(self) -> None:
        """Build the ConfigMap."""
        super().body()

    def add_item(
        self,
        key: str,
        value: str,
        request_encode: bool = False,
        stringdata: bool = False,
    ) -> None:
        """Add an item to the ConfigMap data.

        Args:
            key: Data key name.
            value: Data value.
            request_encode: Whether to base64 encode the value.
            stringdata: Unused for ConfigMap (kept for interface compatibility).
        """
        encode = request_encode
        self.root["data"][key] = (
            encode_string(str(value)) if encode else str(value)
        )


class ComponentConfig(ConfigMap, SharedConfig):
    """Component-specific ConfigMap resource.

    Extended ConfigMap with component-specific metadata setup,
    versioning support, and automatic data population from config.

    Required kwargs:
        config: Configuration dictionary with data, labels, annotations, etc.
        name: ConfigMap name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("config")
        super().new()

    def body(self) -> None:
        """Build the component ConfigMap."""
        super().body()
        self.config = self.kwargs.config

        self.setup_metadata()
        self.add_data(self.config.get("data", {}))
        self.add_directory(self.config.get("directory"), encode=False)
        if self.config.get("versioned", False):
            self.versioning()


class Secret(k8s.Base):
    """Kubernetes Secret resource.

    Generates a Secret manifest for storing sensitive configuration data.
    Supports both base64-encoded data and stringData fields.

    Required kwargs:
        name: Secret name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "Secret"
        super().new()

    def add_item(
        self,
        key: str,
        value: str,
        request_encode: bool = False,
        stringdata: bool = False,
    ) -> None:
        """Add an item to the Secret.

        Args:
            key: Data key name.
            value: Data value.
            request_encode: Whether to base64 encode the value.
            stringdata: If True, use stringData field instead of data.
        """
        encode = not stringdata and request_encode
        field = "stringData" if stringdata else "data"
        if encode and not KAPITAN_REF.fullmatch(str(value)):
            value = encode_string(str(value))
        self.root[field][key] = value


class ComponentSecret(Secret, SharedConfig):
    """Component-specific Secret resource.

    Extended Secret with component-specific metadata setup,
    versioning support, and automatic data population from config.

    Required kwargs:
        config: Configuration dictionary with data, string_data, type, etc.
        name: Secret name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("config")
        super().new()

    def body(self) -> None:
        """Build the component Secret."""
        super().body()
        self.config = self.kwargs.config
        self.root.type = self.config.get("type", "Opaque")

        self.setup_metadata()
        if self.config.get("data"):
            self.add_data(self.config.get("data"))
        if self.config.get("string_data"):
            self.add_string_data(self.config.get("string_data"))
        self.add_directory(self.config.get("directory"), encode=True)
        if self.config.get("versioned", False):
            self.versioning()
