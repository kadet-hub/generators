"""Kubernetes resource generators for Kapitan.

This module provides classes and functions for generating Kubernetes manifests
using Kapitan's kadet input type.

All classes are re-exported from submodules for backward compatibility.
"""

__version__ = "1.1.0"

# Re-export utilities
# Re-export k8s base
from . import k8s

# Re-export base classes and validation helpers
from .base import (
    VALID_DNS_POLICIES,
    VALID_IMAGE_PULL_POLICIES,
    VALID_PROTOCOL_TYPES,
    VALID_RESTART_POLICIES,
    VALID_SERVICE_TYPES,
    Container,
    SharedConfig,
    Workload,
    WorkloadCommon,
    _validate_enum,
)

# Re-export config resources
from .config import (
    ComponentConfig,
    ComponentSecret,
    ConfigMap,
    Secret,
)

# Re-export generators
from .generators import (
    GenerateMultipleObjectsForClass,
    generate_component_manifests,
    generate_gateway,
    generate_ingress,
    generate_manifests,
    generate_resource_manifests,
    main,
)

# Re-export networking resources
from .networking import (
    BackendConfig,
    BackendTLSPolicy,
    Gateway,
    GatewayClass,
    GatewayRoute,
    Ingress,
    ManagedCertificate,
    NetworkPolicy,
    ReferenceGrant,
    Service,
)

# Re-export RBAC resources
from .rbac import (
    ClusterRole,
    ClusterRoleBinding,
    Role,
    RoleBinding,
    ServiceAccount,
)

# Re-export scaling resources
from .scaling import (
    HorizontalPodAutoscaler,
    PodDisruptionBudget,
    VerticalPodAutoscaler,
)

# Re-export storage resources
from .storage import (
    PersistentVolume,
    PersistentVolumeClaim,
)
from .utils import (
    encode_string,
    generate_docs,
    get_components,
    get_search_paths,
    inv,
    j2,
    merge,
)

# Re-export webhook resources
from .webhooks import (
    MutatingWebhookConfiguration,
)

# Re-export workload resources
from .workloads import (
    CronJob,
    DaemonSet,
    Deployment,
    Job,
    StatefulSet,
)


__all__ = [
    # Utils
    "j2",
    "merge",
    "encode_string",
    "get_components",
    "generate_docs",
    "inv",
    "get_search_paths",
    # Validation constants
    "VALID_IMAGE_PULL_POLICIES",
    "VALID_RESTART_POLICIES",
    "VALID_SERVICE_TYPES",
    "VALID_DNS_POLICIES",
    "VALID_PROTOCOL_TYPES",
    # Helper functions
    "_validate_enum",
    # Base
    "WorkloadCommon",
    "SharedConfig",
    "Container",
    "Workload",
    # Workloads
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
    # Networking
    "NetworkPolicy",
    "Service",
    "Ingress",
    "Gateway",
    "GatewayClass",
    "GatewayRoute",
    "ManagedCertificate",
    "ReferenceGrant",
    "BackendTLSPolicy",
    "BackendConfig",
    # Config
    "ConfigMap",
    "ComponentConfig",
    "Secret",
    "ComponentSecret",
    # RBAC
    "ServiceAccount",
    "Role",
    "RoleBinding",
    "ClusterRole",
    "ClusterRoleBinding",
    # Scaling
    "PodDisruptionBudget",
    "VerticalPodAutoscaler",
    "HorizontalPodAutoscaler",
    # Storage
    "PersistentVolume",
    "PersistentVolumeClaim",
    # Webhooks
    "MutatingWebhookConfiguration",
    # Generators
    "GenerateMultipleObjectsForClass",
    "generate_resource_manifests",
    "generate_ingress",
    "generate_gateway",
    "generate_component_manifests",
    "generate_manifests",
    "main",
    # K8s base module
    "k8s",
]
