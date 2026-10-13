"""Base Kubernetes resource class for cert-manager generator.

This module provides the foundational Base class that all cert-manager resources
inherit from. It handles common metadata operations like labels, annotations,
and namespaces.
"""

import re

from kapitan.inputs.kadet import BaseObj


class Base(BaseObj):
    """Base class for all cert-manager Kubernetes resources.

    Provides common functionality for Kubernetes resource generation including:
    - API version and kind configuration
    - Metadata management (name, namespace, labels, annotations)

    All cert-manager resource classes should inherit from this class.

    Attributes:
        name: The resource name.
        root: The underlying resource structure.
        kwargs: Configuration parameters passed during initialization.
    """

    def new(self) -> None:
        """Initialize required fields for the resource."""
        self.need("apiVersion")
        self.need("kind")
        self.need("name")

    def body(self) -> None:
        """Set up the basic resource structure."""
        self.root.apiVersion = self.kwargs.apiVersion
        self.root.kind = self.kwargs.kind
        self.name = self.kwargs.name
        self.root.metadata.name = self.kwargs.get("rendered_name", self.name)
        name = self.root.metadata.name
        if len(name) > 63 or not re.fullmatch(r"(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?", name):
            raise ValueError(
                f"{self.root.kind} '{name}': the name is also the value of the 'name' label, and a label"
                f" value must be at most 63 characters (this one has {len(name)}) of letters, digits,"
                " '-', '_' or '.', starting and ending with a letter or digit; use a shorter name"
            )
        self.add_label("name", name)

    def add_labels(self, labels: dict[str, str]) -> None:
        """Add multiple labels to the resource metadata.

        Args:
            labels: Dictionary of label key-value pairs.
        """
        for key, value in labels.items():
            self.add_label(key, value)

    def add_label(self, key: str, value: str) -> None:
        """Add a single label to the resource metadata.

        Args:
            key: Label key.
            value: Label value.
        """
        self.root.metadata.labels[key] = value

    def add_namespace(self, namespace: str) -> None:
        """Set the namespace for the resource.

        Args:
            namespace: The namespace name.
        """
        self.root.metadata.namespace = namespace

    def add_annotations(self, annotations: dict[str, str]) -> None:
        """Add multiple annotations to the resource metadata.

        Args:
            annotations: Dictionary of annotation key-value pairs.
        """
        for key, value in annotations.items():
            self.add_annotation(key, value)

    def add_annotation(self, key: str, value: str) -> None:
        """Add a single annotation to the resource metadata.

        Args:
            key: Annotation key.
            value: Annotation value.
        """
        self.root.metadata.annotations[key] = value
