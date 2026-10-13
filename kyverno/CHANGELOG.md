# Changelog

## 1.1.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.1.0

- Renders the `policies.kyverno.io` kinds of Kyverno 1.19.1 at their storage version `v1beta1`: ValidatingPolicy, MutatingPolicy, GeneratingPolicy and DeletingPolicy with their namespaced variants under `validating_policies`, `namespaced_validating_policies`, `mutating_policies`, `namespaced_mutating_policies`, `generating_policies`, `namespaced_generating_policies`, `deleting_policies` and `namespaced_deleting_policies`, and PolicyException under `cel_policy_exceptions`. Their schemas ship under `schemas/policies.kyverno.io/`.
- `match_kinds` on these kinds expands to `matchConstraints.resourceRules` for the GA built-in kinds of Kubernetes 1.37.1. No Kyverno defaults are added; the README lists them with sources.
- ClusterPolicy and Policy render the deprecated `failure_policy` and `webhook_timeout_seconds` as `webhookConfiguration.failurePolicy` and `webhookConfiguration.timeoutSeconds`, and `validation_failure_action` as each validate rule's `failureAction`, unless a validate rule sets its own `failureAction` or the policy has `validation_failure_action_overrides` or a `verifyImages` rule. Output changes only for inventories that set these keys, with the same effect in Kyverno.
- `failure_policy` or `webhook_timeout_seconds` together with the same field in `webhook_configuration` now stops the compile; Kyverno's admission already rejected such a policy.
- `generate_existing_on_policy_update` renders as `generateExisting` in each generate rule that sets none. 1.0.0 emitted `spec.generateExistingOnPolicyUpdate`, which Kyverno 1.19.1 rejects even when it is `false`.
- A key that a `policies.kyverno.io` kind does not take, such as `match_kinds` on a PolicyException, stops the compile.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Kyverno 1.19.1. Ships the CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Emits the storage versions `kyverno.io/v1` and `kyverno.io/v2`, which Kyverno 1.19.1 marks deprecated in favour of the `policies.kyverno.io` CEL kinds; the API server prints a deprecation warning, and the CEL kinds are planned as a follow-up.
- `match_kinds: [<kind>, ...]`, so far only accepted on rules, now also works on PolicyException, ClusterCleanupPolicy and CleanupPolicy and expands to `match.any[].resources.kinds`. It overrides `spec.match` and logs a warning.
- No defaults are added; `validationFailureAction` stays at Kyverno's default `Audit` unless set.
- The README documents that the reclass-rs backend strips the `=` of Kyverno equality anchors such as `=(field)`.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
