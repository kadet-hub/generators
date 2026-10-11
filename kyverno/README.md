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

Built for Kyverno 1.19.1.

At 1.19.1 Kyverno marks every version of ClusterPolicy, Policy, PolicyException, ClusterCleanupPolicy and CleanupPolicy deprecated in favour of the CEL-based `policies.kyverno.io` kinds ([ClusterPolicy][dep-cpol], [Policy][dep-pol], [PolicyException][dep-polex], [ClusterCleanupPolicy][dep-ccleanup], [CleanupPolicy][dep-cleanup], [migration guide](https://kyverno.io/docs/guides/migration-to-cel/)). The generator emits the storage versions `kyverno.io/v1` and `kyverno.io/v2`, and the API server prints a deprecation warning when they are applied. The `policies.kyverno.io` kinds are planned as a follow-up.

[dep-cpol]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_clusterpolicies.yaml#L57-L61
[dep-pol]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_policies.yaml#L57-L61
[dep-polex]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_policyexceptions.yaml#L21-L24
[dep-ccleanup]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_clustercleanuppolicies.yaml#L28-L32
[dep-cleanup]: https://github.com/kyverno/kyverno/blob/v1.19.1/config/crds/kyverno/kyverno.io_cleanuppolicies.yaml#L28-L32

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

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged unless a shorthand applies:

| Kind | Flat keys |
|---|---|
| ClusterPolicy, Policy | `rules`, `validation_failure_action`, `validation_failure_action_overrides`, `background`, `admission`, `failure_policy`, `webhook_timeout_seconds`, `apply_rules`, `schema_validation`, `mutate_existing_on_policy_update`, `generate_existing_on_policy_update`, `use_server_side_apply`, `webhook_configuration` |
| PolicyException | `match`, `match_kinds`, `exceptions`, `background`, `conditions`, `pod_security` |
| ClusterCleanupPolicy, CleanupPolicy | `match`, `match_kinds`, `exclude`, `schedule`, `context`, `conditions` |

A rule accepts `name`, `context`, `match`, `match_kinds`, `exclude`, `preconditions`, `cel_preconditions`, `validate`, `mutate`, `generate`, `verify_images` and `image_extractors`; any other rule key, such as `skipBackgroundRequests`, passes through verbatim. An exception entry takes `policy_name` and `rule_names`.

Shorthands:

| Input | Result | Source |
|---|---|---|
| `match_kinds: [<kind>, ...]` on a rule, a PolicyException or a cleanup policy | `match: {any: [{resources: {kinds: [<kind>, ...]}}]}`; replaces `match` | [match and exclude][match], [MatchResources][match-types] |

No defaults are added. `validation_failure_action` stays unset unless configured, so Kyverno's CRD default `Audit` applies and policies only report violations; blocking requires an explicit `Enforce` ([spec_types.go][vfa]). The spec-level `validation_failure_action`, `failure_policy` and `webhook_timeout_seconds` are deprecated in the CRD in favour of `failureAction` inside the rule's `validate` block and `webhook_configuration`; they still work and are kept for existing inventories. Invalid values of `validation_failure_action`, `failure_policy` and `webhook_timeout_seconds` (1 to 30) raise `ValueError` and stop the compile.

With the reclass-rs inventory backend, keys that start with `=` lose that character, because reclass treats `=` as its constant-key prefix. A Kyverno equality anchor `=(field)` in a pattern then becomes the conditional anchor `(field)` without any error, which changes what the policy checks. Use the omegaconf backend for policies with equality anchors, or write those checks as `validate.cel` or `deny` conditions.

[match]: https://kyverno.io/docs/policy-types/cluster-policy/match-exclude/
[match-types]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/match_resources_types.go#L10-L20
[vfa]: https://github.com/kyverno/kyverno/blob/v1.19.1/api/kyverno/v1/spec_types.go#L66-L69

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
```
