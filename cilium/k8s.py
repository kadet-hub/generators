"""Base Kubernetes resource class for Cilium generator."""

from kapitan.inputs.kadet import BaseObj


class Base(BaseObj):
    """Base class for all Cilium Kubernetes resources."""

    def new(self) -> None:
        self.need("apiVersion")
        self.need("kind")
        self.need("name")

    def body(self) -> None:
        self.root.apiVersion = self.kwargs.apiVersion
        self.root.kind = self.kwargs.kind
        self.name = self.kwargs.name
        self.root.metadata.name = self.kwargs.get("rendered_name", self.name)
        self.add_label("name", self.root.metadata.name)

    def add_labels(self, labels: dict[str, str]) -> None:
        for key, value in labels.items():
            self.add_label(key, value)

    def add_label(self, key: str, value: str) -> None:
        self.root.metadata.labels[key] = value

    def add_namespace(self, namespace: str) -> None:
        self.root.metadata.namespace = namespace

    def add_annotations(self, annotations: dict[str, str]) -> None:
        for key, value in annotations.items():
            self.add_annotation(key, value)

    def add_annotation(self, key: str, value: str) -> None:
        self.root.metadata.annotations[key] = value
