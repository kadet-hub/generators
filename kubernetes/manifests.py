"""Generic manifest passthrough and the cluster and namespace policy sections."""

from . import k8s
from .utils import _convert_to_dict


class Manifest(k8s.Base):
    """Any kind: type and metadata from flat keys, all other fields from `body`."""

    def new(self):
        self.need("config")
        config = self.kwargs.config
        for key in ("api_version", "kind"):
            if not config.get(key):
                raise ValueError(f"manifest {self.kwargs.name}: {key} is required")
        body = _convert_to_dict(config.get("body")) or {}
        for key in ("apiVersion", "kind", "metadata"):
            if key in body:
                raise ValueError(
                    f"manifest {self.kwargs.name}: body must not set {key}; use "
                    "api_version, kind, name, namespace, labels and annotations"
                )
        self.kwargs.body = body
        self.kwargs.apiVersion = config.get("api_version")
        self.kwargs.kind = config.get("kind")
        super().new()

    def body(self):
        super().body()
        config = self.kwargs.config
        if self.kwargs.get("namespace"):
            self.add_namespace(self.kwargs.namespace)
        self.add_labels(config.get("labels") or {})
        self.add_annotations(config.get("annotations") or {})
        for key, value in self.kwargs.body.items():
            self.root[key] = value


# section: (apiVersion, kind, output suffix, namespaced, {flat key: field path})
# The flat keys cover every field the kind has in Kubernetes 1.37.
POLICY_SECTIONS = {
    "storage_classes": (
        "storage.k8s.io/v1",
        "StorageClass",
        "sc",
        False,
        {
            "provisioner": "provisioner",
            "parameters": "parameters",
            "reclaim_policy": "reclaimPolicy",
            "volume_binding_mode": "volumeBindingMode",
            "allow_volume_expansion": "allowVolumeExpansion",
            "mount_options": "mountOptions",
            "allowed_topologies": "allowedTopologies",
        },
    ),
    "ingress_classes": (
        "networking.k8s.io/v1",
        "IngressClass",
        "ingressclass",
        False,
        {"controller": "spec.controller", "parameters": "spec.parameters"},
    ),
    "runtime_classes": (
        "node.k8s.io/v1",
        "RuntimeClass",
        "runtimeclass",
        False,
        {"handler": "handler", "overhead": "overhead", "scheduling": "scheduling"},
    ),
    "priority_classes": (
        "scheduling.k8s.io/v1",
        "PriorityClass",
        "pc",
        False,
        {
            "value": "value",
            "global_default": "globalDefault",
            "preemption_policy": "preemptionPolicy",
            "description": "description",
        },
    ),
    "limit_ranges": ("v1", "LimitRange", "limits", True, {"limits": "spec.limits"}),
    "resource_quotas": (
        "v1",
        "ResourceQuota",
        "quota",
        True,
        {
            "hard": "spec.hard",
            "scopes": "spec.scopes",
            "scope_selector": "spec.scopeSelector",
        },
    ),
}

# Annotation that marks the cluster default (`default: true`), per upstream docs.
DEFAULT_CLASS_ANNOTATIONS = {
    "storage_classes": "storageclass.kubernetes.io/is-default-class",
    "ingress_classes": "ingressclass.kubernetes.io/is-default-class",
}


def policy_manifest(section, name, namespace, config):
    """Build the object for one entry of a POLICY_SECTIONS section."""
    api_version, kind, _, _, fields = POLICY_SECTIONS[section]
    body = {}
    for key, path in fields.items():
        value = config.get(key)
        if value is None:
            continue
        *parents, leaf = path.split(".")
        target = body
        for parent in parents:
            target = target.setdefault(parent, {})
        target[leaf] = _convert_to_dict(value)
    manifest = Manifest(
        name=name,
        namespace=namespace,
        config={
            "api_version": api_version,
            "kind": kind,
            "labels": config.get("labels"),
            "annotations": config.get("annotations"),
            "body": body,
        },
    )
    if section in DEFAULT_CLASS_ANNOTATIONS and config.get("default"):
        manifest.add_annotation(DEFAULT_CLASS_ANNOTATIONS[section], "true")
    return manifest
