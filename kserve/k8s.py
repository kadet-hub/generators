import re

from kapitan.inputs.kadet import BaseObj


class Base(BaseObj):
    def new(self):
        self.need("apiVersion")
        self.need("kind")
        self.need("name")

    def body(self):
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

    def add_labels(self, labels):
        for key, value in labels.items():
            self.add_label(key, value)

    def add_label(self, key, value):
        self.root.metadata.labels[key] = value

    def add_namespace(self, namespace):
        self.root.metadata.namespace = namespace

    def add_annotations(self, annotations):
        for key, value in annotations.items():
            self.add_annotation(key, value)

    def add_annotation(self, key, value):
        self.root.metadata.annotations[key] = value
