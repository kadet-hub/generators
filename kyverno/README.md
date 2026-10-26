# Kyverno Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/kyverno/)): pin a released version by digest from its catalog page.

Kapitan kadet generator for [Kyverno](https://kyverno.io/) policy resources:

| Section | Kind | apiVersion | Output key |
|---|---|---|---|
| `cluster_policies` | ClusterPolicy | `kyverno.io/v1` | `<name>-cpol` |
| `policies` | Policy | `kyverno.io/v1` | `<namespace>/<name>-pol` |
| `policy_exceptions` | PolicyException | `kyverno.io/v2` | `<namespace>/<name>-polex` |
| `cluster_cleanup_policies` | ClusterCleanupPolicy | `kyverno.io/v2` | `<name>-ccleanup` |
| `cleanup_policies` | CleanupPolicy | `kyverno.io/v2` | `<namespace>/<name>-cleanup` |
| `validating_policies` | ValidatingPolicy | `policies.kyverno.io/v1beta1` | `<name>-vpol` |
| `namespaced_validating_policies` | NamespacedValidatingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-nvpol` |
| `mutating_policies` | MutatingPolicy | `policies.kyverno.io/v1beta1` | `<name>-mpol` |
| `namespaced_mutating_policies` | NamespacedMutatingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-nmpol` |
| `generating_policies` | GeneratingPolicy | `policies.kyverno.io/v1beta1` | `<name>-gpol` |
| `namespaced_generating_policies` | NamespacedGeneratingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-ngpol` |
| `deleting_policies` | DeletingPolicy | `policies.kyverno.io/v1beta1` | `<name>-dpol` |
| `namespaced_deleting_policies` | NamespacedDeletingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-ndpol` |
| `cel_policy_exceptions` | PolicyException | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-celpolex` |

Built for Kyverno 1.19.2.

At 1.19.1 Kyverno marks every version of ClusterPolicy, Policy, PolicyException, ClusterCleanupPolicy and CleanupPolicy deprecated in favour of the CEL-based `policies.kyverno.io` kinds and plans to remove them in 1.20 ([ClusterPolicy][dep-cpol], [Policy][dep-pol], [PolicyException][dep-polex], [ClusterCleanupPolicy][dep-ccleanup], [CleanupPolicy][dep-cleanup], [migration guide](https://kyverno.io/docs/guides/migration-to-cel/)). For these legacy kinds the generator emits the storage versions `kyverno.io/v1` and `kyverno.io/v2`, and the API server prints a deprecation warning when they are applied. The `policies.kyverno.io` kinds are emitted at `v1beta1`, their storage version at 1.19.1; `v1` is served with the same schema and becomes the storage version in 1.20 ([storage version][storage]).

[dep-cpol]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_clusterpolicies.yaml#L57-L61
[dep-pol]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_policies.yaml#L57-L61
[dep-polex]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_policyexceptions.yaml#L21-L24
[dep-ccleanup]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_clustercleanuppolicies.yaml#L28-L32
[dep-cleanup]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_cleanuppolicies.yaml#L28-L32
[storage]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/policy-types/overview.md?plain=1#L57-L59

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kyverno@sha256:<digest>
        output_path: lib/kyverno
    compile:
      - output_path: manifests/kyverno/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/kyverno
```

### Inventory Contract

All keys live under `parameters.generators.kyverno`. `namespace` at that level sets the default namespace of the namespaced kinds, falling back to `parameters.namespace`, then `default`.

Every resource entry accepts `name` (overrides the map key), `labels`, `annotations` and `spec`; namespaced kinds also accept `namespace`. For the same field, `spec` loses to the flat keys and shorthands below, and a flat key that overrides a `spec` value logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged unless a shorthand or the mapping of deprecated keys below applies:

| Kind | Flat keys |
|---|---|
| ClusterPolicy, Policy | `rules`, `validation_failure_action`, `validation_failure_action_overrides`, `background`, `admission`, `failure_policy`, `webhook_timeout_seconds`, `apply_rules`, `schema_validation`, `mutate_existing_on_policy_update`, `generate_existing_on_policy_update`, `use_server_side_apply`, `webhook_configuration` |
| PolicyException | `match`, `match_kinds`, `exceptions`, `background`, `conditions`, `pod_security` |
| ClusterCleanupPolicy, CleanupPolicy | `match`, `match_kinds`, `exclude`, `schedule`, `context`, `conditions` |
| ValidatingPolicy, NamespacedValidatingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `validations`, `validation_actions`, `failure_policy`, `audit_annotations`, `variables`, `autogen`, `evaluation`, `webhook_configuration` |
| MutatingPolicy, NamespacedMutatingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `mutations`, `failure_policy`, `audit_annotations`, `variables`, `autogen`, `evaluation`, `reinvocation_policy`, `target_match_constraints`, `target_match_conditions`, `webhook_configuration` |
| GeneratingPolicy, NamespacedGeneratingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `generate`, `audit_annotations`, `variables`, `evaluation`, `use_server_side_apply`, `webhook_configuration` |
| DeletingPolicy, NamespacedDeletingPolicy | `match_kinds`, `match_constraints`, `schedule`, `conditions`, `variables`, `deletion_propagation_policy` |
| PolicyException (`cel_policy_exceptions`) | `policy_refs`, `match_conditions`, `images`, `allowed_values`, `report_result`, `expires_at`, `properties`, `evaluation_mode` |

A rule accepts `name`, `context`, `match`, `match_kinds`, `exclude`, `preconditions`, `cel_preconditions`, `validate`, `mutate`, `generate`, `verify_images` and `image_extractors`; any other rule key, such as `skipBackgroundRequests`, passes through verbatim. An exception entry takes `policy_name` and `rule_names`.

Shorthands:

| Input | Result | Source |
|---|---|---|
| `match_kinds: [<kind>, ...]` on a rule, a legacy PolicyException or a cleanup policy | `match: {any: [{resources: {kinds: [<kind>, ...]}}]}`; replaces `match` | [match and exclude][match], [MatchResources][match-types] |
| `match_kinds: [<kind>, ...]` on a `policies.kyverno.io` policy | `matchConstraints.resourceRules`, one entry per kind with its API groups, GA version and resource, and the operations `CREATE`, `UPDATE`, or `*` on deleting policies; replaces `resourceRules` from `match_constraints` and `spec`, other `matchConstraints` keys stay | [Kubernetes 1.37.1 discovery][discovery], operations as in Kyverno's [migration example][mig-ops] and [DeletingPolicy example][dpol-ops] |

Kyverno's admission rejects a `policies.kyverno.io` policy without a resource rule in `matchConstraints` ([validate.go][mc-required]). `match_kinds` there knows the GA built-in kinds of Kubernetes 1.37.1; any other kind, such as one from a CRD, stops the compile with a `ValueError` and belongs under `match_constraints.resourceRules`, where its API group and resource are explicit. A key that a `policies.kyverno.io` kind does not take also stops the compile, since an ignored key such as `match_kinds` on a PolicyException would leave the exception wider than written.

No defaults are added. A field left unset gets Kyverno's default:

| Field | Kinds | Kyverno's default | Source |
|---|---|---|---|
| `validation_failure_action` | ClusterPolicy, Policy | `Audit`: violations are only reported | [spec_types.go][vfa] |
| `validation_actions` | ValidatingPolicy, NamespacedValidatingPolicy | `[Deny]`: a violating request is rejected | [ValidationActions][vpol-actions] |
| `failure_policy` | validating and mutating policies | `Fail`; GeneratingPolicy always uses `Ignore` | [validating][vpol-fp], [mutating][mpol-fp], [generating][gpol-fp] |
| `webhook_configuration.timeoutSeconds` | validating, mutating, generating policies | 10 seconds | [WebhookConfiguration][timeout] |
| `evaluation.admission.enabled`, `evaluation.background.enabled` | validating, mutating, generating policies | `true` | [EvaluationConfiguration][evaluation] |
| `autogen.validatingAdmissionPolicy.enabled`, `autogen.mutatingAdmissionPolicy.enabled` | validating, mutating policies | `false` | [validating][vpol-vap], [mutating][mpol-map] |
| `reinvocation_policy`, `evaluation.mutateExisting.enabled` | mutating policies | `Never`, `false` | [reinvocation][mpol-reinvoke], [mutateExisting][mpol-existing] |
| `evaluation.synchronize.enabled`, `evaluation.generateExisting.enabled`, `evaluation.orphanDownstreamOnPolicyDelete.enabled` | generating policies | `false` | [GeneratingPolicySpec][gpol-eval] |
| `report_result` | PolicyException (`cel_policy_exceptions`) | `skip` | [PolicyExceptionSpec][polex-report] |

PolicyExceptions apply only when Kyverno runs with `enablePolicyException` and lists their namespace in `exceptionNamespace` ([exceptions][polex-flag]). A `policies.kyverno.io` PolicyException exempts every resource its `match_conditions` select, in any namespace; its own namespace does not limit it, so state the namespace in a condition ([ListExceptions][polex-scope]).

On ClusterPolicy and Policy the deprecated spec-level keys are rendered as their replacements. `failure_policy` and `webhook_timeout_seconds` become `webhookConfiguration.failurePolicy` and `webhookConfiguration.timeoutSeconds`, which Kyverno reads before the deprecated fields ([spec_types.go][wh-get]). Setting one of them together with the same field in `webhook_configuration` stops the compile, because Kyverno rejects a policy with both ([validateDeprecatedFields][wh-both]).

`generate_existing_on_policy_update` becomes `generateExisting` in the `generate` block of each rule, because Kyverno rejects the spec-level field even when it is `false` ([validateDeprecatedFields][wh-both]); a rule that sets its own `generateExisting` keeps it and logs a warning.

`validation_failure_action` becomes `failureAction`, capitalised, in the `validate` block of every rule; Kyverno resolves a rule's own action before the spec-level one ([ruleAction][rule-action]). It stays at spec level where the move would change a resolved action:

- a validate rule sets its own `failureAction`: the policy-wide action is the first rule-level one ([GetValidationFailureAction][policy-action])
- the policy has `validation_failure_action_overrides`, which a rule-level action would outrank ([failureActionForRule][rule-fallback])
- the policy has a `verifyImages` rule, which reads the spec-level action ([validate.go][vi-spec])

Invalid values of `validation_failure_action`, `failure_policy` and `webhook_timeout_seconds` (1 to 30) raise `ValueError` and stop the compile.

With the reclass-rs inventory backend, keys that start with `=` lose that character, because reclass treats `=` as its constant-key prefix. A Kyverno equality anchor `=(field)` in a pattern then becomes the conditional anchor `(field)` without any error, which changes what the policy checks. Use the omegaconf backend for policies with equality anchors, or write those checks as `validate.cel` or `deny` conditions.

[match]: https://kyverno.io/docs/policy-types/cluster-policy/match-exclude/
[match-types]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/match_resources_types.go#L10-L20
[vfa]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/spec_types.go#L66-L69
[discovery]: https://github.com/kubernetes/kubernetes/tree/v1.37.1/api/discovery
[mig-ops]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/guides/migration-to-cel.md?plain=1#L56-L81
[dpol-ops]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/policy-types/deleting-policy.mdx?plain=1#L113-L126
[mc-required]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/cel/policies/vpol/validate.go#L32-L34
[vpol-actions]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/validating_policy.go#L210-L217
[vpol-fp]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1beta1/validating_policy.go#L90-L98
[mpol-fp]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1beta1/mutating_policy.go#L149-L157
[gpol-fp]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1beta1/generating_policy.go#L67-L69
[timeout]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/validating_policy.go#L232-L237
[evaluation]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/common.go#L21-L36
[vpol-vap]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/validating_policy.go#L177-L190
[mpol-map]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/mutating_policy.go#L162-L174
[mpol-reinvoke]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/mutating_policy.go#L212-L219
[mpol-existing]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/mutating_policy.go#L222-L229
[gpol-eval]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/generating_policy.go#L127-L167
[polex-report]: https://github.com/kyverno/api/blob/fb2785727f98db3dd0e263fc354d4b6443a8362e/api/policies.kyverno.io/v1alpha1/policy_exception.go#L52-L57
[polex-scope]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/cel/engine/exception.go#L67-L84
[polex-flag]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/guides/exceptions.md?plain=1#L9
[wh-get]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/spec_types.go#L276-L296
[wh-both]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/spec_types.go#L343-L356
[rule-action]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/engine/api/engineresponse.go#L246-L274
[policy-action]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/engine/api/engineresponse.go#L276-L294
[rule-fallback]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/engine/api/engineresponse.go#L296-L319
[vi-spec]: https://github.com/kyverno/kyverno/blob/v1.19.1/pkg/validation/policy/validate.go#L350-L366

### Example

```yaml
parameters:
  generators:
    kyverno:
      namespace: shop
      cluster_policies:
        disallow-privileged-containers:
          annotations:
            policies.kyverno.io/title: Disallow Privileged Containers
            policies.kyverno.io/category: Pod Security Standards (Baseline)
          validation_failure_action: Enforce
          webhook_configuration:
            failurePolicy: Fail
            timeoutSeconds: 10
          rules:
            - name: privileged-containers
              match_kinds: [Pod]
              validate:
                cel:
                  expressions:
                    - expression: >-
                        object.spec.containers.all(c, !has(c.securityContext) ||
                        !has(c.securityContext.privileged) || c.securityContext.privileged == false)
                      message: Privileged mode is disallowed.
      policies:
        require-memory-limits:
          rules:
            - name: check-memory-limits
              match_kinds: [Pod]
              validate:
                failureAction: Audit
                message: Memory limits are required
                pattern:
                  spec:
                    containers:
                      - resources:
                          limits:
                            memory: "?*"
      policy_exceptions:
        node-exporter-host-access:
          namespace: monitoring
          match:
            any:
              - resources:
                  kinds: [Pod]
                  namespaces: [monitoring]
                  names: ["node-exporter-*"]
          exceptions:
            - policy_name: disallow-privileged-containers
              rule_names: [privileged-containers]
      cluster_cleanup_policies:
        failed-jobs:
          schedule: "0 0 * * *"
          match_kinds: [Job]
          conditions:
            all:
              - key: "{{ target.status.failed || `0` }}"
                operator: GreaterThan
                value: 0
      cleanup_policies:
        preview-pods:
          schedule: "*/30 * * * *"
          spec:
            deletionPropagationPolicy: Foreground
          match:
            any:
              - resources:
                  kinds: [Pod]
                  selector:
                    matchLabels:
                      env: preview
      validating_policies:
        require-team-label:
          match_kinds: [Deployment, StatefulSet]
          validation_actions: [Deny]
          validations:
            - expression: "has(object.metadata.labels) && has(object.metadata.labels.team)"
              message: "label team is required"
      cel_policy_exceptions:
        legacy-billing:
          namespace: billing
          policy_refs:
            - name: require-team-label
              kind: ValidatingPolicy
          match_conditions:
            - name: billing-namespace
              expression: "object.metadata.namespace == 'billing'"
            - name: legacy-deployment
              expression: "object.metadata.name == 'billing-legacy'"
      deleting_policies:
        succeeded-jobs:
          schedule: "0 1 * * *"
          match_kinds: [Job]
          conditions:
            - name: succeeded
              expression: "has(object.status.succeeded) && object.status.succeeded > 0"
```
