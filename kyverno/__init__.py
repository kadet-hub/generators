"""Kyverno policy generator for Kapitan.

Generates the policies.kyverno.io CEL kinds: ValidatingPolicy, MutatingPolicy,
GeneratingPolicy, DeletingPolicy, their namespaced variants and PolicyException.
Kyverno 1.20 rejects creates of the legacy kyverno.io policies and no longer
executes them, so their sections fail the compile.

Schema reference: policies.kyverno.io/v1beta1
See: https://kyverno.io/docs/
"""

__version__ = "2.0.0"

import logging
import re
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

# =============================================================================
# Helper Functions
# =============================================================================


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj/kadet/OmegaConf objects to plain dicts."""
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


# =============================================================================
# Base Kyverno Resource Class
# =============================================================================


def _default_namespace() -> str:
    """Namespace fallback chain: generators.kyverno.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("kyverno", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge any user-supplied ``spec`` dict into *spec_target*.

    This is the escape hatch: anything not explicitly modelled can still be
    emitted by placing it under the ``spec`` key in inventory.
    """
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when flat keys will override passthrough values from ``spec``.

    A null flat key is not applied by ``_set_field`` and so does not collide.

    Args:
        config:   The resource configuration dict.
        mapping:  dict of flat_key -> crd_key (both support dotted paths).
        name:     The resource name (the outer inventory key).
    """
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


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set ``target[target_key]`` from ``config[source_key]`` when it is not None."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _convert_to_dict(value)


class KyvernoBase(k8s.Base):
    """Base class for Kyverno resources with common patterns."""

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", _default_namespace())

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Add common metadata fields from config."""
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))


# =============================================================================
# policies.kyverno.io CEL kinds
# =============================================================================

# Resources of the GA built-in kinds per group/version, from the discovery
# documents api__v1.json and aggregated_v2.json of Kubernetes 1.37.1:
# https://github.com/kubernetes/kubernetes/tree/v1.37.1/api/discovery
_BUILTIN_RESOURCES = {
    "v1": {
        "Binding": "bindings", "ComponentStatus": "componentstatuses", "ConfigMap": "configmaps",
        "Endpoints": "endpoints", "Event": "events", "LimitRange": "limitranges", "Namespace": "namespaces",
        "Node": "nodes", "PersistentVolume": "persistentvolumes", "PersistentVolumeClaim": "persistentvolumeclaims",
        "Pod": "pods", "PodTemplate": "podtemplates", "ReplicationController": "replicationcontrollers",
        "ResourceQuota": "resourcequotas", "Secret": "secrets", "Service": "services",
        "ServiceAccount": "serviceaccounts",
    },
    "admissionregistration.k8s.io/v1": {
        "MutatingAdmissionPolicy": "mutatingadmissionpolicies",
        "MutatingAdmissionPolicyBinding": "mutatingadmissionpolicybindings",
        "MutatingWebhookConfiguration": "mutatingwebhookconfigurations",
        "ValidatingAdmissionPolicy": "validatingadmissionpolicies",
        "ValidatingAdmissionPolicyBinding": "validatingadmissionpolicybindings",
        "ValidatingWebhookConfiguration": "validatingwebhookconfigurations",
    },
    "apiextensions.k8s.io/v1": {"CustomResourceDefinition": "customresourcedefinitions"},
    "apiregistration.k8s.io/v1": {"APIService": "apiservices"},
    "apps/v1": {
        "ControllerRevision": "controllerrevisions", "DaemonSet": "daemonsets", "Deployment": "deployments",
        "ReplicaSet": "replicasets", "StatefulSet": "statefulsets",
    },
    "authentication.k8s.io/v1": {"SelfSubjectReview": "selfsubjectreviews", "TokenReview": "tokenreviews"},
    "authorization.k8s.io/v1": {
        "LocalSubjectAccessReview": "localsubjectaccessreviews", "SelfSubjectAccessReview": "selfsubjectaccessreviews",
        "SelfSubjectRulesReview": "selfsubjectrulesreviews", "SubjectAccessReview": "subjectaccessreviews",
    },
    "autoscaling/v2": {"HorizontalPodAutoscaler": "horizontalpodautoscalers"},
    "batch/v1": {"CronJob": "cronjobs", "Job": "jobs"},
    "certificates.k8s.io/v1": {
        "CertificateSigningRequest": "certificatesigningrequests", "ClusterTrustBundle": "clustertrustbundles",
        "PodCertificateRequest": "podcertificaterequests",
    },
    "coordination.k8s.io/v1": {"Lease": "leases"},
    "discovery.k8s.io/v1": {"EndpointSlice": "endpointslices"},
    "events.k8s.io/v1": {"Event": "events"},
    "flowcontrol.apiserver.k8s.io/v1": {
        "FlowSchema": "flowschemas", "PriorityLevelConfiguration": "prioritylevelconfigurations",
    },
    "networking.k8s.io/v1": {
        "IPAddress": "ipaddresses", "Ingress": "ingresses", "IngressClass": "ingressclasses",
        "NetworkPolicy": "networkpolicies", "ServiceCIDR": "servicecidrs",
    },
    "node.k8s.io/v1": {"RuntimeClass": "runtimeclasses"},
    "policy/v1": {"PodDisruptionBudget": "poddisruptionbudgets"},
    "rbac.authorization.k8s.io/v1": {
        "ClusterRole": "clusterroles", "ClusterRoleBinding": "clusterrolebindings", "Role": "roles",
        "RoleBinding": "rolebindings",
    },
    "resource.k8s.io/v1": {
        "DeviceClass": "deviceclasses", "DeviceTaintRule": "devicetaintrules", "ResourceClaim": "resourceclaims",
        "ResourceClaimTemplate": "resourceclaimtemplates", "ResourceSlice": "resourceslices",
    },
    "scheduling.k8s.io/v1": {"PriorityClass": "priorityclasses"},
    "storage.k8s.io/v1": {
        "CSIDriver": "csidrivers", "CSINode": "csinodes", "CSIStorageCapacity": "csistoragecapacities",
        "StorageClass": "storageclasses", "VolumeAttachment": "volumeattachments",
        "VolumeAttributesClass": "volumeattributesclasses",
    },
    "storagemigration.k8s.io/v1": {"StorageVersionMigration": "storageversionmigrations"},
}


def _resource_rules(kinds: list, operations: tuple) -> list:
    """``match_kinds`` of a CEL kind: one ``matchConstraints.resourceRules`` entry per built-in kind."""
    rules = []
    for kind in kinds:
        found = [(gv, resources[kind]) for gv, resources in _BUILTIN_RESOURCES.items() if kind in resources]
        if not found:
            raise ValueError(
                f"match_kinds: '{kind}' is not a built-in Kubernetes kind; "
                "list it under match_constraints.resourceRules"
            )
        rules.append(
            {
                "apiGroups": [gv.rpartition("/")[0] for gv, _ in found],
                "apiVersions": sorted({gv.rpartition("/")[2] for gv, _ in found}),
                "operations": list(operations),
                "resources": [found[0][1]],
            }
        )
    return rules


class CelPolicy(KyvernoBase):
    """A policies.kyverno.io resource.

    Required kwargs:
        name: Resource name.
        config: Resource configuration dictionary.
        kind: The kind.
        namespaced: Whether the kind is namespace-scoped.
        fields: The spec fields that take a flat key (their snake_case spelling).
        operations: The operations ``match_kinds`` matches; None if the kind has
            no matchConstraints.
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "policies.kyverno.io/v1beta1"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config, include_namespace=self.kwargs.namespaced)

        flat_keys = {
            re.sub("([A-Z])", r"_\1", field).lower(): field for field in self.kwargs.fields
        }
        if self.kwargs.operations:
            flat_keys["match_kinds"] = "matchConstraints.resourceRules"
        # An ignored key could widen what a policy or exception applies to
        allowed = {"name", "labels", "annotations", "spec", *flat_keys}
        if self.kwargs.namespaced:
            allowed.add("namespace")
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ValueError(
                f"{self.kwargs.kind} '{self.kwargs.name}': unknown keys {', '.join(unknown)}"
            )

        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, flat_keys, self.kwargs.name)
        for flat_key, field in flat_keys.items():
            if flat_key != "match_kinds":
                _set_field(spec, config, flat_key, target_key=field)
        if self.kwargs.operations and config.get("match_kinds"):
            spec.setdefault("matchConstraints", {})["resourceRules"] = _resource_rules(
                config["match_kinds"], self.kwargs.operations
            )


_ADMISSION_OPERATIONS = ("CREATE", "UPDATE")
_VALIDATING_FIELDS = (
    "auditAnnotations", "autogen", "evaluation", "failurePolicy", "matchConditions",
    "matchConstraints", "validationActions", "validations", "variables", "webhookConfiguration",
)
_MUTATING_FIELDS = (
    "auditAnnotations", "autogen", "evaluation", "failurePolicy", "matchConditions",
    "matchConstraints", "mutations", "reinvocationPolicy", "targetMatchConditions",
    "targetMatchConstraints", "variables", "webhookConfiguration",
)
_GENERATING_FIELDS = (
    "auditAnnotations", "evaluation", "generate", "matchConditions", "matchConstraints",
    "useServerSideApply", "variables", "webhookConfiguration",
)
_DELETING_FIELDS = (
    "conditions", "deletionPropagationPolicy", "matchConstraints", "schedule", "variables",
)
_EXCEPTION_FIELDS = (
    "allowedValues", "evaluationMode", "expiresAt", "images", "matchConditions",
    "policyRefs", "properties", "reportResult",
)

# Inventory key: (kind, output suffix, namespaced, spec fields, match_kinds operations)
_CEL_KINDS = {
    "validating_policies": ("ValidatingPolicy", "vpol", False, _VALIDATING_FIELDS, _ADMISSION_OPERATIONS),
    "namespaced_validating_policies": (
        "NamespacedValidatingPolicy", "nvpol", True, _VALIDATING_FIELDS, _ADMISSION_OPERATIONS,
    ),
    "mutating_policies": ("MutatingPolicy", "mpol", False, _MUTATING_FIELDS, _ADMISSION_OPERATIONS),
    "namespaced_mutating_policies": (
        "NamespacedMutatingPolicy", "nmpol", True, _MUTATING_FIELDS, _ADMISSION_OPERATIONS,
    ),
    "generating_policies": ("GeneratingPolicy", "gpol", False, _GENERATING_FIELDS, _ADMISSION_OPERATIONS),
    "namespaced_generating_policies": (
        "NamespacedGeneratingPolicy", "ngpol", True, _GENERATING_FIELDS, _ADMISSION_OPERATIONS,
    ),
    "deleting_policies": ("DeletingPolicy", "dpol", False, _DELETING_FIELDS, ("*",)),
    "namespaced_deleting_policies": ("NamespacedDeletingPolicy", "ndpol", True, _DELETING_FIELDS, ("*",)),
    "cel_policy_exceptions": ("PolicyException", "celpolex", True, _EXCEPTION_FIELDS, None),
}


# Sections of the legacy kyverno.io kinds that 1.x rendered: their replacement
_LEGACY_SECTIONS = {
    "cluster_policies": "validating_policies, mutating_policies or generating_policies",
    "policies": "namespaced_validating_policies, namespaced_mutating_policies or namespaced_generating_policies",
    "policy_exceptions": "cel_policy_exceptions",
    "cluster_cleanup_policies": "deleting_policies",
    "cleanup_policies": "namespaced_deleting_policies",
}


# =============================================================================
# Main Entry Point
# =============================================================================


def main(input_params) -> BaseObj:
    """Generate Kyverno resources from inventory.

    Reads the keys of _CEL_KINDS from parameters.generators.kyverno and fails
    on the keys of _LEGACY_SECTIONS.
    """
    obj = BaseObj()

    # Get kyverno config from generators namespace
    kyverno_config = inv.parameters.get("generators", {}).get("kyverno", {}) or {}

    for key in _LEGACY_SECTIONS:
        if kyverno_config.get(key):
            raise ValueError(
                f"generators.kyverno.{key}: Kyverno 1.20 rejects creates of the legacy "
                f"kyverno.io policies and no longer executes them; use {_LEGACY_SECTIONS[key]}, "
                "see https://kyverno.io/docs/guides/migration-to-cel/"
            )

    # policies.kyverno.io CEL kinds
    for key, (kind, suffix, namespaced, fields, operations) in _CEL_KINDS.items():
        for name, config in (kyverno_config.get(key) or {}).items():
            config = _convert_to_dict(config) or {}
            resource_name = config.get("name", name)
            path = f"{resource_name}-{suffix}"
            if namespaced:
                path = f"{config.get('namespace', _default_namespace())}/{path}"
            obj.root[path] = CelPolicy(
                name=resource_name,
                config=config,
                kind=kind,
                namespaced=namespaced,
                fields=fields,
                operations=operations,
            )

    return obj


__all__ = [
    "CelPolicy",
    "KyvernoBase",
    "main",
    "k8s",
    "inv",
    "_convert_to_dict",
]
