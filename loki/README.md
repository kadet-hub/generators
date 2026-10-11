# Loki Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/loki/) page.

Built for Loki Operator 0.11.0 (`loki.grafana.com/v1`). The compiled output is not checked against JSON Schemas: the upstream CRDs are AGPL-3.0-only, so this generator does not ship them.

Kapitan kadet generator for [Loki Operator](https://loki-operator.dev/) resources:

- **LokiStack**: a managed Loki deployment
- **AlertingRule**: LogQL alerting rules for one tenant
- **RecordingRule**: LogQL recording rules for one tenant
- **RulerConfig**: ruler settings (Alertmanager, remote write) for a LokiStack

The object storage Secret belongs in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/loki@sha256:<digest>
        output_path: lib/loki
    compile:
      - output_path: manifests/loki/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/loki
```

### Inventory Contract

All keys live under `parameters.generators.loki`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `loki_stacks.<name>` | LokiStack | `<namespace>/<name>-lokistack` |
| `alerting_rules.<name>` | AlertingRule | `<namespace>/<name>-alertingrule` |
| `recording_rules.<name>` | RecordingRule | `<namespace>/<name>-recordingrule` |
| `ruler_configs.<name>` | RulerConfig | `<namespace>/<name>-rulerconfig` |

The CRDs define no shortNames, so the suffix is the lowercase kind.

Every resource accepts `namespace`, `labels`, `annotations` and `spec`; rules also accept `loki_stack`. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands. A flat key replaces the same field from `spec` and logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged:

| Kind | Flat keys |
|---|---|
| LokiStack | `size`, `storage`, `storage_class_name`, `hash_ring`, `limits`, `management_state`, `network_policies`, `proxy`, `replication`, `rules`, `template`, `tenants` |
| AlertingRule, RecordingRule | `tenant_id`, `groups` |
| RulerConfig | `alertmanager`, `evaluation_interval`, `overrides`, `poll_interval`, `remote_write` |

The deprecated `replicationFactor` is not a flat key; use `replication.factor`.

### LokiStack Defaults

The generator fills these fields only where neither `spec` nor a flat key sets them.

| Input | Result |
|---|---|
| `storage: <type>` | `storage.secret` with `name: <stack name>-<type>` and `type: <type>` |
| `storage` without `schemas` | `storage.schemas: [{version: v13, effectiveDate: "2023-10-15"}]` |
| `tenants` without `mode` | `mode: passthrough` if the block has `passthrough`, `dynamic` if it has `authorization.opa`, `static` if it has `authorization.roles` or `authorization.roleBindings`; otherwise no mode |
| `rules.enabled: true` without `rules.selector` | `selector.matchLabels` on `loki.grafana.com/lokistack: <stack name>`, plus a `namespaceSelector` on `kubernetes.io/metadata.name` for the namespaces of its rules outside the stack namespace |

The storage shorthand follows the Secret naming of the operator's [object storage guide](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/docs/lokistack/object_storage.md) (`lokistack-dev-s3` for the stack `lokistack-dev`). `<type>` is one of `s3`, `azure`, `gcs`, `swift`, `alibabacloud`. A Secret with another name, a `credentialMode` or `tls` needs the full `storage` block.

Without `schemas` the CRD applies `v11` from 2020-10-11 ([CRD default](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/api/loki/v1/lokistack_types.go#L699)), and the operator then sets the `StorageNeedsSchemaUpdate` warning because the latest schema is not `v13` ([status](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/status/lokistack.go#L198)). The API recommends the latest schema with a past effective date for a new stack ([API](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/api/loki/v1/lokistack_types.go#L681-L688)), and Loki calls `v13` the recommended schema ([Loki schema docs](https://grafana.com/docs/loki/latest/operations/storage/schema/)). The date is fixed to keep the output deterministic. It is the one the operator's own examples use ([tenancy modes](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/docs/user-guides/tenancy-modes.md)).

A stack that already runs on the CRD default keeps `v11` in `status.storage.schemas`. The operator's webhook rejects an update that drops it or adds a schema with a past date ([validation](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/validation/lokistack.go#L294-L376)). For such a stack, set `storage.schemas` to its current entries plus `v13` with an effective date in the future.

The CRD default for `tenants.mode` is `openshift-logging`. It works only on OpenShift and rejects custom `authentication` and `authorization`. The derived mode is the only one the operator's [mode validation](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/handlers/internal/gateway/modes.go) accepts for that block; see the [tenancy modes guide](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/docs/user-guides/tenancy-modes.md). The operator's default configuration enables the gateway ([config](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/config/overlays/community/controller_manager_config.yaml#L17)), and a stack without `tenants` is then degraded ([gateway](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/handlers/internal/gateway/gateway.go#L35-L41)). Set `tenants` on every stack.

Rules are bound to a stack by the label `loki.grafana.com/lokistack: <stack name>`. A rule gets it for the stack named in its `loki_stack`; without `loki_stack`, rules are bound to the only stack when `loki_stacks` has exactly one entry. A `labels` entry with the same key wins. The operator selects rules by `rules.selector`, and a stack without a selector loads none ([rule discovery](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/handlers/internal/rules/rules.go#L108-L148), [nil selector](https://github.com/kubernetes/apimachinery/blob/v0.35.3/pkg/apis/meta/v1/helpers.go#L36-L39)). It searches only the stack namespace unless `rules.namespaceSelector` matches other namespaces ([design](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/docs/enhancements/ruler_support.md#alertingrule-and-recordingrule-reconciliation)). The namespace selector uses the label Kubernetes sets on every namespace ([Kubernetes docs](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/#automatic-labelling)), so the generator does not need to label namespaces. The operator documents no label convention of its own. Its samples select on `openshift.io/cluster-monitoring` ([sample](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/hack/lokistack_gateway_ocp.yaml)), which marks a namespace for monitoring rather than naming a stack. An explicit `selector` or `namespaceSelector` is never changed, and rules bound by other labels stay as they are.

Not defaulted:

- `size`: depends on the daily log volume, from 50 GB/day for `1x.pico` to 2 TB/day for `1x.medium` ([sizing](https://docs.redhat.com/en/documentation/red_hat_openshift_logging/6.0/html/configuring_logging/configuring-lokistack-storage)). Required by the CRD.
- `storage_class_name`: depends on the cluster. Required by the CRD.
- `replication.factor`: the operator sets 2 for every size except `1x.demo` ([sizes](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/manifests/internal/sizes.go#L379-L382)).
- Retention: Loki deletes nothing unless `limits.global.retention` or a tenant retention is set ([config](https://github.com/grafana/loki/blob/2cbdcb2f8289e10e1fc3ebb026b6ab05573326bb/operator/internal/manifests/config.go#L369-L391)). There is no vendor default; set `limits.global.retention.days` or a lifecycle rule on the bucket.
- Other CRD defaults (`managementState: Managed`, `evaluationInterval: 1m`, `pollInterval: 1m`) are left to the API server.

A RulerConfig applies to the LokiStack with the same name in the same namespace.

### Example

```yaml
parameters:
  generators:
    loki:
      namespace: logging
      loki_stacks:
        logs:
          size: 1x.small
          storage: s3
          storage_class_name: standard
          limits:
            global:
              retention:
                days: 30
          tenants:
            authentication:
              - tenantName: application
                tenantId: application
                oidc:
                  secret:
                    name: application-oidc
                  issuerURL: https://idp.example.com/
            authorization:
              roles:
                - name: read-write
                  permissions: [read, write]
                  resources: [logs]
                  tenants: [application]
              roleBindings:
                - name: developers
                  roles: [read-write]
                  subjects:
                    - kind: group
                      name: developers
          rules:
            enabled: true
      alerting_rules:
        high-error-rate:
          tenant_id: application
          groups:
            - name: errors
              interval: 1m
              rules:
                - alert: HighErrorRate
                  expr: sum(rate({app="web"} |= "error" [5m])) > 10
                  for: 10m
                  labels:
                    severity: warning
      recording_rules:
        request-rates:
          tenant_id: application
          groups:
            - name: rates
              interval: 1m
              rules:
                - record: web:requests:rate5m
                  expr: sum(rate({app="web"}[5m]))
      ruler_configs:
        logs:
          evaluation_interval: 1m
          alertmanager:
            endpoints:
              - http://alertmanager.monitoring.svc:9093
```

The `logs` stack compiles to the `logs-s3` Secret reference, the `v13` schema, `tenants.mode: static` and a rules selector on `loki.grafana.com/lokistack: logs`, the label both rules get.
