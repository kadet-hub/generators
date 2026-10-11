"""Kyverno policy generator for Kapitan.

Generates Kyverno resources for Kubernetes policy management:
- ClusterPolicy: Cluster-wide policy rules for validation, mutation, and generation
- Policy: Namespace-scoped policy rules
- PolicyException: Exceptions to exclude resources from policy enforcement
- ClusterCleanupPolicy: Cluster-wide cleanup policies (TTL-based resource deletion)
- CleanupPolicy: Namespace-scoped cleanup policies

Schema reference: kyverno.io/v1, kyverno.io/v2
See: https://kyverno.io/docs/
"""

__version__ = "1.0.0"

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)

# =============================================================================
# Valid enum values from schema
# =============================================================================

VALID_VALIDATION_FAILURE_ACTIONS = frozenset({"Audit", "Enforce", "audit", "enforce"})

VALID_BACKGROUND_VALUES = frozenset({True, False})

VALID_FAILURE_POLICIES = frozenset({"Fail", "Ignore"})

VALID_WEBHOOK_TIMEOUT_SECONDS = range(1, 31)  # 1-30 seconds

# Rule types
VALID_RULE_TYPES = frozenset({"validate", "mutate", "generate", "verifyImages"})


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


def _validate_enum(value: Any, valid_values: frozenset, field_name: str) -> None:
    """Validate that a value is in a set of valid enum values.

    Args:
        value: Value to validate.
        valid_values: Set of valid values.
        field_name: Name of the field for error message.

    Raises:
        ValueError: If value is not in valid_values.
    """
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            f"Must be one of: {', '.join(str(v) for v in sorted(valid_values))}"
        )


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


def _match(config: dict) -> Any:
    """``match_kinds: [Kind, ...]`` expands to ``match.any[].resources.kinds``; else ``match``."""
    kinds = config.get("match_kinds")
    if kinds:
        return {"any": [{"resources": {"kinds": _convert_to_dict(kinds)}}]}
    return _convert_to_dict(config.get("match"))


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

    _FLAT_KEY_MAP: dict[str, str] = {}


# =============================================================================
# ClusterPolicy
# =============================================================================


class ClusterPolicy(KyvernoBase):
    """Kyverno ClusterPolicy resource.

    Cluster-wide policy that declares validation, mutation, and generation behaviors
    for matching resources across all namespaces.

    Required kwargs:
        name: Resource name.
        config: ClusterPolicy configuration dictionary.

    Example config:
        {
            'rules': [
                {
                    'name': 'require-labels',
                    'match': {
                        'any': [
                            {'resources': {'kinds': ['Pod']}}
                        ]
                    },
                    'validate': {
                        'message': 'The label app is required',
                        'pattern': {
                            'metadata': {
                                'labels': {
                                    'app': '?*'
                                }
                            }
                        }
                    }
                }
            ]
        }
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kyverno.io/v1"
        self.kwargs.kind = "ClusterPolicy"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # ClusterPolicy is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Build spec
        self._build_policy_spec(config)

    _FLAT_KEY_MAP = {
        "rules": "rules",
        "validation_failure_action": "validationFailureAction",
        "validation_failure_action_overrides": "validationFailureActionOverrides",
        "background": "background",
        "admission": "admission",
        "failure_policy": "failurePolicy",
        "webhook_timeout_seconds": "webhookTimeoutSeconds",
        "apply_rules": "applyRules",
        "schema_validation": "schemaValidation",
        "mutate_existing_on_policy_update": "mutateExistingOnPolicyUpdate",
        "generate_existing_on_policy_update": "generateExistingOnPolicyUpdate",
        "use_server_side_apply": "useServerSideApply",
        "webhook_configuration": "webhookConfiguration",
    }

    def _build_policy_spec(self, config: dict) -> None:
        """Build policy spec fields common to ClusterPolicy and Policy."""
        spec = self.root.spec
        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # Rules (required)
        rules = config.get("rules", [])
        if rules:
            spec.rules = self._build_rules(rules)

        # Validation failure action
        validation_failure_action = config.get("validation_failure_action")
        if validation_failure_action:
            _validate_enum(
                validation_failure_action,
                VALID_VALIDATION_FAILURE_ACTIONS,
                "validationFailureAction",
            )
            spec.validationFailureAction = validation_failure_action

        # Validation failure action overrides
        overrides = config.get("validation_failure_action_overrides")
        if overrides:
            spec.validationFailureActionOverrides = _convert_to_dict(overrides)

        # Background processing
        background = config.get("background")
        if background is not None:
            spec.background = background

        # Admission (webhook) control
        admission = config.get("admission")
        if admission is not None:
            spec.admission = admission

        # Failure policy
        failure_policy = config.get("failure_policy")
        if failure_policy:
            _validate_enum(failure_policy, VALID_FAILURE_POLICIES, "failurePolicy")
            spec.failurePolicy = failure_policy

        # Webhook timeout
        webhook_timeout = config.get("webhook_timeout_seconds")
        if webhook_timeout is not None:
            if webhook_timeout not in VALID_WEBHOOK_TIMEOUT_SECONDS:
                raise ValueError(
                    f"webhookTimeoutSeconds must be between 1 and 30, got {webhook_timeout}"
                )
            spec.webhookTimeoutSeconds = webhook_timeout

        # Apply rules (One/All)
        apply_rules = config.get("apply_rules")
        if apply_rules:
            spec.applyRules = apply_rules

        # Schema validation
        schema_validation = config.get("schema_validation")
        if schema_validation is not None:
            spec.schemaValidation = schema_validation

        # Mutate existing on policy update
        mutate_existing = config.get("mutate_existing_on_policy_update")
        if mutate_existing is not None:
            spec.mutateExistingOnPolicyUpdate = mutate_existing

        # Generate existing on policy update
        generate_existing = config.get("generate_existing_on_policy_update")
        if generate_existing is not None:
            spec.generateExistingOnPolicyUpdate = generate_existing

        # Use server-side apply for mutation
        use_server_side_apply = config.get("use_server_side_apply")
        if use_server_side_apply is not None:
            spec.useServerSideApply = use_server_side_apply

        # Webhook configuration
        webhook_config = config.get("webhook_configuration")
        if webhook_config:
            spec.webhookConfiguration = _convert_to_dict(webhook_config)

    def _build_rules(self, rules_config: list) -> list:
        """Build policy rules."""
        rules = []
        for rule in rules_config:
            rule_dict = {}

            # Name (required)
            rule_dict["name"] = rule.get("name", "")

            # Context (variables)
            if rule.get("context"):
                rule_dict["context"] = _convert_to_dict(rule["context"])

            # Match conditions - support shorthand match_kinds
            match_kinds = rule.get("match_kinds")
            if match_kinds:
                # Auto-expand match_kinds: [Pod] to full match structure
                rule_dict["match"] = {"any": [{"resources": {"kinds": match_kinds}}]}
            elif rule.get("match"):
                rule_dict["match"] = _convert_to_dict(rule["match"])

            # Exclude conditions
            if rule.get("exclude"):
                rule_dict["exclude"] = _convert_to_dict(rule["exclude"])

            # Preconditions
            if rule.get("preconditions"):
                rule_dict["preconditions"] = _convert_to_dict(rule["preconditions"])

            # CEL preconditions
            cel_preconditions = rule.get("cel_preconditions")
            if cel_preconditions:
                rule_dict["celPreconditions"] = _convert_to_dict(cel_preconditions)

            # Validate rule
            if rule.get("validate"):
                rule_dict["validate"] = _convert_to_dict(rule["validate"])

            # Mutate rule
            if rule.get("mutate"):
                rule_dict["mutate"] = _convert_to_dict(rule["mutate"])

            # Generate rule
            if rule.get("generate"):
                rule_dict["generate"] = _convert_to_dict(rule["generate"])

            # Verify images rule
            verify_images = rule.get("verify_images")
            if verify_images:
                rule_dict["verifyImages"] = _convert_to_dict(verify_images)

            # Image extractors
            image_extractors = rule.get("image_extractors")
            if image_extractors:
                rule_dict["imageExtractors"] = _convert_to_dict(image_extractors)

            # Pass unmodelled rule fields through verbatim (CRD camelCase,
            # e.g. skipBackgroundRequests, reportProperties) — a whitelist
            # here would silently drop them.
            handled = {
                "name",
                "context",
                "match_kinds",
                "match",
                "exclude",
                "preconditions",
                "cel_preconditions",
                "validate",
                "mutate",
                "generate",
                "verify_images",
                "image_extractors",
            }
            for key, value in rule.items():
                if key not in handled and key not in rule_dict:
                    rule_dict[key] = _convert_to_dict(value)

            rules.append(rule_dict)

        return rules


# =============================================================================
# Policy (Namespace-scoped)
# =============================================================================


class Policy(ClusterPolicy):
    """Kyverno Policy resource (namespace-scoped).

    Namespace-scoped policy that declares validation, mutation, and generation
    behaviors for matching resources within a specific namespace.

    Required kwargs:
        name: Resource name.
        config: Policy configuration dictionary.

    Example config:
        {
            'namespace': 'my-namespace',
            'rules': [
                {
                    'name': 'require-labels',
                    'match': {
                        'any': [
                            {'resources': {'kinds': ['Pod']}}
                        ]
                    },
                    'validate': {
                        'message': 'The label app is required',
                        'pattern': {
                            'metadata': {
                                'labels': {
                                    'app': '?*'
                                }
                            }
                        }
                    }
                }
            ]
        }
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kyverno.io/v1"
        self.kwargs.kind = "Policy"
        # Call Base.new() directly, not ClusterPolicy.new()
        k8s.Base.new(self)

    def body(self) -> None:
        k8s.Base.body(self)
        config = self.kwargs.config

        # Policy is namespace-scoped
        self._add_common_metadata(config, include_namespace=True)

        # Build spec (reuse parent implementation)
        self._build_policy_spec(config)


# =============================================================================
# PolicyException
# =============================================================================


class PolicyException(KyvernoBase):
    """Kyverno PolicyException resource.

    Declares resources to be excluded from specified policies.
    Allows granting exceptions to specific resources without modifying the policy itself.

    Required kwargs:
        name: Resource name.
        config: PolicyException configuration dictionary.

    Example config:
        {
            'namespace': 'my-namespace',
            'match': {
                'any': [
                    {
                        'resources': {
                            'kinds': ['Pod'],
                            'namespaces': ['emergency'],
                            'names': ['critical-*']
                        }
                    }
                ]
            },
            'exceptions': [
                {
                    'policy_name': 'require-labels',
                    'rule_names': ['require-app-label']
                }
            ]
        }
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kyverno.io/v2"
        self.kwargs.kind = "PolicyException"
        super().new()

    _FLAT_KEY_MAP = {
        "match": "match",
        "match_kinds": "match",
        "exceptions": "exceptions",
        "background": "background",
        "conditions": "conditions",
        "pod_security": "podSecurity",
    }

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # PolicyException is namespace-scoped
        self._add_common_metadata(config, include_namespace=True)

        spec = self.root.spec
        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # Match conditions (required), with the match_kinds shorthand
        match = _match(config)
        if match:
            spec.match = match

        # Exceptions (required) - list of policy/rule references
        exceptions = config.get("exceptions", [])
        if exceptions:
            spec.exceptions = self._build_exceptions(exceptions)

        # Background processing
        background = config.get("background")
        if background is not None:
            spec.background = background

        # Conditions (additional CEL conditions)
        if config.get("conditions"):
            spec.conditions = _convert_to_dict(config["conditions"])

        # Pod security exceptions
        pod_security = config.get("pod_security")
        if pod_security:
            spec.podSecurity = _convert_to_dict(pod_security)

    def _build_exceptions(self, exceptions_config: list) -> list:
        """Build exception references."""
        exceptions = []
        for exc in exceptions_config:
            exc_dict = {}

            # Policy name (required)
            policy_name = exc.get("policy_name")
            if policy_name:
                exc_dict["policyName"] = policy_name

            # Rule names (required)
            rule_names = exc.get("rule_names")
            if rule_names:
                exc_dict["ruleNames"] = rule_names

            exceptions.append(exc_dict)

        return exceptions


# =============================================================================
# ClusterCleanupPolicy
# =============================================================================


class ClusterCleanupPolicy(KyvernoBase):
    """Kyverno ClusterCleanupPolicy resource.

    Cluster-wide policy for automatic resource cleanup based on TTL or conditions.

    Required kwargs:
        name: Resource name.
        config: ClusterCleanupPolicy configuration dictionary.

    Example config:
        {
            'match': {
                'any': [
                    {
                        'resources': {
                            'kinds': ['Pod'],
                            'selector': {
                                'matchLabels': {
                                    'cleanup': 'true'
                                }
                            }
                        }
                    }
                ]
            },
            'schedule': '*/5 * * * *',
            'conditions': {
                'any': [
                    {
                        'key': '{{ time_since(\\'\\', metadata.creationTimestamp) }}',
                        'operator': 'GreaterThan',
                        'value': '1h'
                    }
                ]
            }
        }
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kyverno.io/v2"
        self.kwargs.kind = "ClusterCleanupPolicy"
        super().new()

    _FLAT_KEY_MAP = {
        "match": "match",
        "match_kinds": "match",
        "exclude": "exclude",
        "schedule": "schedule",
        "context": "context",
        "conditions": "conditions",
    }

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # ClusterCleanupPolicy is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        self._build_cleanup_spec(config)

    def _build_cleanup_spec(self, config: dict) -> None:
        """Build cleanup policy spec."""
        spec = self.root.spec
        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # Match conditions (required), with the match_kinds shorthand
        match = _match(config)
        if match:
            spec.match = match

        # Exclude conditions
        if config.get("exclude"):
            spec.exclude = _convert_to_dict(config["exclude"])

        # Schedule (cron expression, required)
        schedule = config.get("schedule")
        if schedule:
            spec.schedule = schedule

        # Context (variables)
        if config.get("context"):
            spec.context = _convert_to_dict(config["context"])

        # Conditions (when to delete)
        if config.get("conditions"):
            spec.conditions = _convert_to_dict(config["conditions"])


# =============================================================================
# CleanupPolicy (Namespace-scoped)
# =============================================================================


class CleanupPolicy(ClusterCleanupPolicy):
    """Kyverno CleanupPolicy resource (namespace-scoped).

    Namespace-scoped policy for automatic resource cleanup.

    Required kwargs:
        name: Resource name.
        config: CleanupPolicy configuration dictionary.
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "kyverno.io/v2"
        self.kwargs.kind = "CleanupPolicy"
        k8s.Base.new(self)

    def body(self) -> None:
        k8s.Base.body(self)
        config = self.kwargs.config

        # CleanupPolicy is namespace-scoped
        self._add_common_metadata(config, include_namespace=True)

        # Build spec (reuse parent implementation)
        self._build_cleanup_spec(config)


# =============================================================================
# Main Entry Point
# =============================================================================


def main(input_params) -> BaseObj:
    """Generate Kyverno resources from inventory.

    Reads from parameters.generators.kyverno:
    - cluster_policies: ClusterPolicy configurations
    - policies: Policy configurations
    - policy_exceptions: PolicyException configurations
    - cluster_cleanup_policies: ClusterCleanupPolicy configurations
    - cleanup_policies: CleanupPolicy configurations
    """
    obj = BaseObj()

    # Get kyverno config from generators namespace
    kyverno_config = inv.parameters.get("generators", {}).get("kyverno", {}) or {}

    # ClusterPolicies
    cluster_policies = kyverno_config.get("cluster_policies", {})
    for name, config in cluster_policies.items():
        config = _convert_to_dict(config) or {}
        policy_name = config.get("name", name)
        obj.root[f"{policy_name}-cpol"] = ClusterPolicy(name=policy_name, config=config)

    # Policies (namespace-scoped)
    policies = kyverno_config.get("policies", {})
    for name, config in policies.items():
        config = _convert_to_dict(config) or {}
        policy_name = config.get("name", name)
        namespace = config.get("namespace", _default_namespace())
        obj.root[f"{namespace}/{policy_name}-pol"] = Policy(
            name=policy_name, config=config
        )

    # PolicyExceptions
    policy_exceptions = kyverno_config.get("policy_exceptions", {})
    for name, config in policy_exceptions.items():
        config = _convert_to_dict(config) or {}
        exc_name = config.get("name", name)
        namespace = config.get("namespace", _default_namespace())
        obj.root[f"{namespace}/{exc_name}-polex"] = PolicyException(
            name=exc_name, config=config
        )

    # ClusterCleanupPolicies
    cluster_cleanup = kyverno_config.get("cluster_cleanup_policies", {})
    for name, config in cluster_cleanup.items():
        config = _convert_to_dict(config) or {}
        policy_name = config.get("name", name)
        obj.root[f"{policy_name}-ccleanup"] = ClusterCleanupPolicy(
            name=policy_name, config=config
        )

    # CleanupPolicies (namespace-scoped)
    cleanup = kyverno_config.get("cleanup_policies", {})
    for name, config in cleanup.items():
        config = _convert_to_dict(config) or {}
        policy_name = config.get("name", name)
        namespace = config.get("namespace", _default_namespace())
        obj.root[f"{namespace}/{policy_name}-cleanup"] = CleanupPolicy(
            name=policy_name, config=config
        )

    return obj


__all__ = [
    # Main classes
    "ClusterPolicy",
    "Policy",
    "PolicyException",
    "ClusterCleanupPolicy",
    "CleanupPolicy",
    # Base class
    "KyvernoBase",
    # Entry point
    "main",
    # Imports
    "k8s",
    "inv",
    "_convert_to_dict",
]
