"""Kubernetes RBAC resources: ServiceAccount, Role, RoleBinding, ClusterRole, ClusterRoleBinding.

This module provides classes for generating Kubernetes RBAC (Role-Based Access Control)
resources. These resources control access to Kubernetes API resources.
"""

from . import k8s
from .utils import get_namespace, inv


def service_account_name(component):
    """Name of the component's ServiceAccount: service_account.name, else the component name."""
    return (component.get("service_account") or {}).get("name") or component.get("name")


def cluster_scoped_name(component):
    """<namespace>-<component>: cluster-scoped names must not collide across namespaces."""
    return f"{get_namespace(component, default='default')}-{component.get('name')}"


class ServiceAccount(k8s.Base):
    """Kubernetes ServiceAccount resource.

    Generates a ServiceAccount manifest for pod identity.

    Required kwargs:
        component: Component configuration dictionary.
        name: ServiceAccount name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "ServiceAccount"
        super().new()

    def body(self) -> None:
        """Build the ServiceAccount."""
        super().body()
        component = self.kwargs.component
        namespace = get_namespace(component)
        if namespace:
            self.add_namespace(namespace)
        service_account = component.get("service_account", {})
        self.add_annotations(service_account.get("annotations", {}))
        # Pods opt in with automountServiceAccountToken; see README.
        automount = service_account.get("automount_service_account_token")
        self.root.automountServiceAccountToken = (
            automount if automount is not None else False
        )
        # Only set imagePullSecrets if explicitly configured (must be array, not empty dict)
        image_pull_secrets = component.get("image_pull_secrets")
        pull_secret_name = inv.parameters.get("pull_secret", {}).get("name")
        if image_pull_secrets:
            self.root.imagePullSecrets = image_pull_secrets
        elif pull_secret_name:
            self.root.imagePullSecrets = [{"name": pull_secret_name}]


class Role(k8s.Base):
    """Kubernetes Role resource.

    Generates a namespaced Role manifest with permission rules.

    Required kwargs:
        component: Component configuration dictionary with role.rules.
        name: Role name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "Role"
        super().new()

    def body(self) -> None:
        """Build the Role."""
        super().body()
        _name = self.kwargs.name
        component = self.kwargs.component
        # role.namespace puts the Role elsewhere, e.g. leader election in kube-system.
        namespace = component.get("role", {}).get("namespace") or get_namespace(component)
        if namespace:
            self.add_namespace(namespace)
        self.root.rules = component.get("role", {}).get("rules")


class RoleBinding(k8s.Base):
    """Kubernetes RoleBinding resource.

    Generates a RoleBinding manifest linking a Role to subjects.

    Required kwargs:
        component: Component configuration dictionary.
        name: RoleBinding name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "RoleBinding"
        super().new()

    def body(self) -> None:
        """Build the RoleBinding."""
        super().body()
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": self.kwargs.component.get("name"),
        }
        _name = self.kwargs.name
        component = self.kwargs.component
        namespace = get_namespace(component)
        role_namespace = component.get("role", {}).get("namespace") or namespace
        if role_namespace:
            self.add_namespace(role_namespace)
        sa_subject = {
            "kind": "ServiceAccount",
            "name": service_account_name(component),
        }
        if namespace:
            sa_subject["namespace"] = namespace
        binding = component.get("role", {}).get("binding", {}) or {}
        self.root.roleRef = (
            binding.get("role_ref")
            or binding.get("roleRef")
            or component.get("roleRef")
            or default_role_ref
        )
        self.root.subjects = (
            binding.get("subjects") or component.get("subject") or [sa_subject]
        )


class ClusterRole(k8s.Base):
    """Kubernetes ClusterRole resource.

    Generates a cluster-wide ClusterRole manifest with permission rules.

    Required kwargs:
        component: Component configuration dictionary with cluster_role.rules.
        name: ClusterRole name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "ClusterRole"
        super().new()

    def body(self) -> None:
        """Build the ClusterRole."""
        self.kwargs.rendered_name = cluster_scoped_name(self.kwargs.component)
        super().body()
        component = self.kwargs.component
        self.root.rules = component.get("cluster_role", {}).get("rules")


class ClusterRoleBinding(k8s.Base):
    """Kubernetes ClusterRoleBinding resource.

    Generates a ClusterRoleBinding manifest linking a ClusterRole to subjects.

    Required kwargs:
        component: Component configuration dictionary.
        name: ClusterRoleBinding name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "rbac.authorization.k8s.io/v1"
        self.kwargs.kind = "ClusterRoleBinding"
        super().new()

    def body(self) -> None:
        """Build the ClusterRoleBinding."""
        component = self.kwargs.component
        self.kwargs.rendered_name = cluster_scoped_name(component)
        super().body()
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": cluster_scoped_name(component),
        }
        # A ServiceAccount subject needs its namespace.
        sa_subject = {
            "kind": "ServiceAccount",
            "name": service_account_name(component),
            "namespace": get_namespace(component, default="default"),
        }
        binding = component.get("cluster_role", {}).get("binding", {}) or {}
        self.root.roleRef = (
            binding.get("role_ref")
            or binding.get("roleRef")
            or component.get("roleRef")
            or default_role_ref
        )
        self.root.subjects = (
            binding.get("subjects") or component.get("subject") or [sa_subject]
        )
