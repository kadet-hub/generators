# Kyverno Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/kyverno/)): pin a released version by digest from its catalog page.

Kapitan kadet generator for [Kyverno](https://kyverno.io/) policy resources:

| Section | Kind | apiVersion | Output key |
|---|---|---|---|
| `validating_policies` | ValidatingPolicy | `policies.kyverno.io/v1beta1` | `<name>-vpol` |
| `namespaced_validating_policies` | NamespacedValidatingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-nvpol` |
| `mutating_policies` | MutatingPolicy | `policies.kyverno.io/v1beta1` | `<name>-mpol` |
| `namespaced_mutating_policies` | NamespacedMutatingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-nmpol` |
| `generating_policies` | GeneratingPolicy | `policies.kyverno.io/v1beta1` | `<name>-gpol` |
| `namespaced_generating_policies` | NamespacedGeneratingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-ngpol` |
| `deleting_policies` | DeletingPolicy | `policies.kyverno.io/v1beta1` | `<name>-dpol` |
| `namespaced_deleting_policies` | NamespacedDeletingPolicy | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-ndpol` |
| `cel_policy_exceptions` | PolicyException | `policies.kyverno.io/v1beta1` | `<namespace>/<name>-celpolex` |

Built for Kyverno 1.20.0.

Kyverno 1.20 denies creates and spec updates of the legacy `kyverno.io` policies (ClusterPolicy, Policy, PolicyException, ClusterCleanupPolicy, CleanupPolicy) and no longer executes them, although their CRDs stay served ([admission][legacy-deny], [execution][legacy-exec]). Since 2.0.0 the generator renders only the `policies.kyverno.io` kinds. The sections `cluster_policies`, `policies`, `policy_exceptions`, `cluster_cleanup_policies` and `cleanup_policies` stop the compile with a `ValueError` that names the replacement section. Kyverno's [migration guide](https://kyverno.io/docs/guides/migration-to-cel/) maps the legacy rules to CEL. Generator 1.1.4 renders the legacy kinds for Kyverno 1.19.

The kinds are emitted at `v1beta1`, still their storage version at 1.20.0; `v1` is served with the same schema ([ValidatingPolicy CRD][storage]).

[legacy-deny]: https://github.com/kyverno/kyverno/pull/17535
[legacy-exec]: https://github.com/kyverno/kyverno/pull/18164
[storage]: https://github.com/kyverno/kyverno/blob/v1.20.0/config/crds/policies.kyverno.io/policies.kyverno.io_validatingpolicies.yaml#L4759

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

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged unless the shorthand below applies:

| Kind | Flat keys |
|---|---|
| ValidatingPolicy, NamespacedValidatingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `validations`, `validation_actions`, `failure_policy`, `audit_annotations`, `variables`, `autogen`, `evaluation`, `webhook_configuration` |
| MutatingPolicy, NamespacedMutatingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `mutations`, `failure_policy`, `audit_annotations`, `variables`, `autogen`, `evaluation`, `reinvocation_policy`, `target_match_constraints`, `target_match_conditions`, `webhook_configuration` |
| GeneratingPolicy, NamespacedGeneratingPolicy | `match_kinds`, `match_constraints`, `match_conditions`, `generate`, `audit_annotations`, `variables`, `evaluation`, `use_server_side_apply`, `webhook_configuration` |
| DeletingPolicy, NamespacedDeletingPolicy | `match_kinds`, `match_constraints`, `schedule`, `conditions`, `variables`, `deletion_propagation_policy` |
| PolicyException (`cel_policy_exceptions`) | `policy_refs`, `match_conditions`, `images`, `allowed_values`, `report_result`, `expires_at`, `properties`, `evaluation_mode` |

Shorthand:

| Input | Result | Source |
|---|---|---|
| `match_kinds: [<kind>, ...]` on a policy | `matchConstraints.resourceRules`, one entry per kind with its API groups, GA version and resource, and the operations `CREATE`, `UPDATE`, or `*` on deleting policies; replaces `resourceRules` from `match_constraints` and `spec`, other `matchConstraints` keys stay | [Kubernetes 1.37.1 discovery][discovery], operations as in Kyverno's [migration example][mig-ops] and [DeletingPolicy example][dpol-ops] |

Kyverno's admission rejects a policy without a resource rule in `matchConstraints` ([validate.go][mc-required]). `match_kinds` there knows the GA built-in kinds of Kubernetes 1.37.1; any other kind, such as one from a CRD, stops the compile with a `ValueError` and belongs under `match_constraints.resourceRules`, where its API group and resource are explicit. A key that a kind does not take also stops the compile, since an ignored key such as `match_kinds` on a PolicyException would leave the exception wider than written.

No defaults are added. A field left unset gets Kyverno's default:

| Field | Kinds | Kyverno's default | Source |
|---|---|---|---|
| `validation_actions` | ValidatingPolicy, NamespacedValidatingPolicy | `[Deny]`: a violating request is rejected | [ValidationActions][vpol-actions] |
| `failure_policy` | validating and mutating policies | `Fail`; GeneratingPolicy always uses `Ignore` | [validating][vpol-fp], [mutating][mpol-fp], [generating][gpol-fp] |
| `webhook_configuration.timeoutSeconds` | validating, mutating, generating policies | 10 seconds | [WebhookConfiguration][timeout] |
| `evaluation.admission.enabled`, `evaluation.background.enabled` | validating, mutating, generating policies | `true` | [EvaluationConfiguration][evaluation] |
| `autogen.validatingAdmissionPolicy.enabled`, `autogen.mutatingAdmissionPolicy.enabled` | validating, mutating policies | `false` | [validating][vpol-vap], [mutating][mpol-map] |
| `reinvocation_policy`, `evaluation.mutateExisting.enabled` | mutating policies | `Never`, `false` | [reinvocation][mpol-reinvoke], [mutateExisting][mpol-existing] |
| `evaluation.synchronize.enabled`, `evaluation.generateExisting.enabled`, `evaluation.orphanDownstreamOnPolicyDelete.enabled` | generating policies | `false` | [GeneratingPolicySpec][gpol-eval] |
| `report_result` | PolicyException (`cel_policy_exceptions`) | `skip` | [PolicyExceptionSpec][polex-report] |

PolicyExceptions apply only when Kyverno runs with `enablePolicyException` and lists their namespace in `exceptionNamespace` ([exceptions][polex-flag]). A PolicyException exempts every resource its `match_conditions` select, in any namespace; its own namespace does not limit it, so state the namespace in a condition ([ListExceptions][polex-scope]).

[discovery]: https://github.com/kubernetes/kubernetes/tree/v1.37.1/api/discovery
[mig-ops]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/guides/migration-to-cel.md?plain=1#L56-L81
[dpol-ops]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/policy-types/deleting-policy.mdx?plain=1#L113-L126
[mc-required]: https://github.com/kyverno/kyverno/blob/v1.20.0/pkg/cel/policies/vpol/validate.go#L32-L34
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
[polex-scope]: https://github.com/kyverno/kyverno/blob/v1.20.0/pkg/cel/engine/exception.go#L67-L84
[polex-flag]: https://github.com/kyverno/website/blob/e388c9f1ef171b9414d0f5826fbf05ee0380c09a/src/content/docs/docs/guides/exceptions.md?plain=1#L9

### Example

```yaml
parameters:
  generators:
    kyverno:
      namespace: shop
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
