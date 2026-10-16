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
    "namespaces": ("v1", "Namespace", "namespace", False, {}),
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


RBAC_GROUP = "rbac.authorization.k8s.io"


def _rbac_manifest(kind, name, namespace, config, body):
    return Manifest(
        name=name,
        namespace=namespace,
        config={
            "api_version": f"{RBAC_GROUP}/v1",
            "kind": kind,
            "labels": config.get("labels"),
            "annotations": config.get("annotations"),
            "body": body,
        },
    )


def _subjects(name, namespace, config):
    subjects = list(_convert_to_dict(config.get("subjects")) or [])
    for account in config.get("service_accounts") or []:
        account_namespace, _, account_name = account.rpartition("/")
        account_namespace = account_namespace or namespace
        if not account_namespace:
            raise ValueError(
                f"rbac.{name}: service account {account} needs <namespace>/<name>"
            )
        subjects.append(
            {"kind": "ServiceAccount", "name": account_name, "namespace": account_namespace}
        )
    for kind, key in (("Group", "groups"), ("User", "users")):
        for subject in config.get(key) or []:
            subjects.append({"apiGroup": RBAC_GROUP, "kind": kind, "name": subject})
    return subjects


def rbac_manifests(name, config):
    """One role and its bindings: yields (output key, manifest).

    With `namespace` the role is a Role in that namespace; without, a
    ClusterRole. `role` or `cluster_role` names an existing role to bind
    instead of creating one. A Role is bound in its namespace; a ClusterRole
    by a RoleBinding in each of `namespaces` and by a ClusterRoleBinding with
    `cluster_wide`. Without subjects only the role is rendered.
    """
    namespace = config.get("namespace")
    namespaces = list(config.get("namespaces") or [])
    cluster_wide = bool(config.get("cluster_wide"))
    role, cluster_role = config.get("role"), config.get("cluster_role")
    defines = config.get("rules") is not None or config.get("aggregation_rule") is not None

    if role and cluster_role:
        raise ValueError(f"rbac.{name}: set role or cluster_role, not both")
    if (role or cluster_role) and defines:
        raise ValueError(f"rbac.{name}: role and cluster_role bind an existing role; drop rules")
    if not (role or cluster_role or defines):
        raise ValueError(f"rbac.{name}: set rules, aggregation_rule, role or cluster_role")
    if role and not namespace:
        raise ValueError(f"rbac.{name}: role needs the namespace of that Role")
    if namespace and (namespaces or cluster_wide):
        raise ValueError(f"rbac.{name}: a Role is bound in its namespace only; drop namespaces and cluster_wide")
    if namespace and cluster_role:
        raise ValueError(f"rbac.{name}: bind a ClusterRole with namespaces, not namespace")
    if config.get("aggregation_rule") is not None and namespace:
        raise ValueError(f"rbac.{name}: aggregation_rule needs a ClusterRole; drop namespace")

    subjects = _subjects(name, namespace, config)
    scopes = [namespace] if namespace else namespaces
    if subjects and not (scopes or cluster_wide):
        raise ValueError(f"rbac.{name}: subjects need namespace, namespaces or cluster_wide")
    if (namespaces or cluster_wide or role or cluster_role) and not subjects:
        raise ValueError(f"rbac.{name}: set service_accounts, groups, users or subjects")

    if defines and namespace:
        yield f"{namespace}/{name}-role", _rbac_manifest(
            "Role", name, namespace, config, {"rules": _convert_to_dict(config.get("rules")) or []}
        )
    elif defines:
        body = {"rules": _convert_to_dict(config.get("rules")) or []}
        if config.get("aggregation_rule") is not None:
            body["aggregationRule"] = _convert_to_dict(config.get("aggregation_rule"))
        yield f"{name}-clusterrole", _rbac_manifest("ClusterRole", name, None, config, body)
    if not subjects:
        return

    role_ref = {
        "apiGroup": RBAC_GROUP,
        "kind": "Role" if namespace else "ClusterRole",
        "name": role or cluster_role or name,
    }
    for scope in scopes:
        yield f"{scope}/{name}-rolebinding", _rbac_manifest(
            "RoleBinding",
            name,
            scope,
            config,
            {"roleRef": role_ref, "subjects": _subjects(name, scope, config)},
        )
    if cluster_wide:
        yield f"{name}-clusterrolebinding", _rbac_manifest(
            "ClusterRoleBinding", name, None, config, {"roleRef": role_ref, "subjects": subjects}
        )
