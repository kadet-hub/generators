"""Base Kubernetes resource class.

This module provides the foundational Base class that all Kubernetes resources
inherit from. It handles common metadata operations like labels, annotations,
and namespaces.
"""

from kapitan.inputs.kadet import BaseObj


class Base(BaseObj):
    """Base class for all Kubernetes resources.

    Provides common functionality for Kubernetes resource generation including:
    - API version and kind configuration
    - Metadata management (name, namespace, labels, annotations)

    All Kubernetes resource classes should inherit from this class.

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
        self.add_label("name", self.root.metadata.name)

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
