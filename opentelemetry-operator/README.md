# OpenTelemetry Operator Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/opentelemetry-operator/) page.

Kapitan kadet generator for [OpenTelemetry Operator](https://github.com/open-telemetry/opentelemetry-operator) resources (`opentelemetry.io`). Built for OpenTelemetry Operator 0.160.0.

- **OpenTelemetryCollector** (`v1beta1`): a managed collector as Deployment, DaemonSet, StatefulSet or sidecar
- **Instrumentation** (`v1alpha1`): auto-instrumentation injection settings
- **TargetAllocator** (`v1alpha1`): standalone Prometheus target distribution for collectors
- **OpAMPBridge** (`v1alpha1`): OpAMP management of collectors

ClusterObservability is not rendered; it needs the alpha operator feature gate `operator.clusterobservability`. The operator install, RBAC, Secrets and the instrumented workloads belong in the `helm` or `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/opentelemetry-operator@sha256:<digest>
        output_path: lib/opentelemetry-operator
    compile:
      - output_path: manifests/opentelemetry-operator/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/opentelemetry-operator
```

### Inventory Contract

All keys live under `parameters.generators.opentelemetry_operator`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `collectors.<name>` | OpenTelemetryCollector | `<namespace>/<name>-otelcol` |
| `instrumentations.<name>` | Instrumentation | `<namespace>/<name>-otelinst` |
| `target_allocators.<name>` | TargetAllocator | `<namespace>/<name>-targetallocator` |
| `opamp_bridges.<name>` | OpAMPBridge | `<namespace>/<name>-opampbridge` |

Every resource accepts `namespace`, `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. Precedence is generator defaults < `spec` < flat keys and shorthands: a flat key wins over the same field in `spec` and logs a warning.

Flat keys are the snake_case spelling of every top-level CRD `spec` field of the rendered version, for example `mode`, `config`, `target_allocator`, `pod_dns_config`, `host_pid`, `prometheus_cr`, `apache_httpd` or `components_allowed`. Values pass through unchanged: the collector `config` is free-form collector YAML and its keys are never translated.

Collector `${env:VAR}` references must be escaped as `\${env:VAR}` in an interpolating inventory backend such as omegaconf, which otherwise tries to resolve them.

### Shorthands and Defaults

| Input | Result | Source |
|---|---|---|
| collector `target_allocator: <name>` | label `opentelemetry.io/target-allocator: <name>`; a dict still passes through to the embedded `targetAllocator` | A standalone TargetAllocator is linked by this label on the collector ([TargetAllocator CRD](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/docs/target-allocator/README.md#targetallocator-crd)). |
| collector without `mode` that uses a target allocator (that label, or `targetAllocator.enabled: true`) | `mode: statefulset` | The target allocator supports only `statefulset` and `daemonset` ([note](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/docs/target-allocator/README.md)); the operator defaults `mode` to `deployment` ([webhook](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/internal/webhook/collector_webhook.go#L63-L66)) and rejects an embedded target allocator in that mode ([validation](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/internal/webhook/collector_webhook.go#L330-L332)). |

The `per-node` allocation strategy needs `mode: daemonset`; set it explicitly. The operator looks up a standalone TargetAllocator in the collector's namespace ([controller](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/internal/controllers/opentelemetrycollector_controller.go#L213-L224)), so keep both in the same namespace.

All other unset keys are not emitted, so the operator's defaults apply: `mode: deployment`, `replicas: 1`, `upgradeStrategy: automatic`, `managementState: managed`, the collector config defaults, the auto-instrumentation images and resources, and the TargetAllocator `allocationStrategy: consistent-hashing`. These are deliberately left without a generator default:

- `prometheus_cr` selectors. Without `serviceMonitorSelector` and `podMonitorSelector` the TargetAllocator discovers no monitors; `{}` selects every monitor in the cluster, which on a shared cluster lets a monitor author read the collector's credentials ([selectors](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/docs/target-allocator/README.md#podservice-monitor-selectors), [security](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/docs/target-allocator/security.md)).
- OpAMPBridge `capabilities`. The CRD requires them and they decide what the OpAMP server may do: the `Reports*` capabilities only report, `AcceptsRemoteConfig` lets the server rewrite collector configs in the cluster, so the inventory sets them deliberately ([OpAMPBridge CRD](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/cmd/operator-opamp-bridge/README.md#opampbridge-crd)).
- OpAMP labels on collectors. A bridge reports or manages only collectors labeled `opentelemetry.io/opamp-reporting: "true"` or `opentelemetry.io/opamp-managed: "true"` (or the bridge name); set them in `labels` ([collector labels](https://github.com/open-telemetry/opentelemetry-operator/blob/v0.160.0/cmd/operator-opamp-bridge/README.md#opentelemetrycollector-crd)).

### Example

```yaml
parameters:
  generators:
    opentelemetry_operator:
      namespace: observability
      collectors:
        gateway:
          replicas: 2
          labels:
            opentelemetry.io/opamp-managed: bridge
          config:
            receivers:
              otlp:
                protocols:
                  grpc:
                    endpoint: 0.0.0.0:4317
                  http:
                    endpoint: 0.0.0.0:4318
            processors:
              batch: {}
            exporters:
              otlphttp:
                endpoint: http://tempo.observability.svc:4318
            service:
              pipelines:
                traces:
                  receivers: [otlp]
                  processors: [batch]
                  exporters: [otlphttp]
        metrics:
          target_allocator: metrics
          config:
            receivers:
              prometheus:
                config:
                  scrape_configs: []
            exporters:
              debug: {}
            service:
              pipelines:
                metrics:
                  receivers: [prometheus]
                  exporters: [debug]
      target_allocators:
        metrics:
          prometheus_cr:
            enabled: true
            podMonitorSelector:
              matchLabels:
                team: platform
            serviceMonitorSelector:
              matchLabels:
                team: platform
      instrumentations:
        default:
          namespace: web
          exporter:
            endpoint: http://gateway-collector.observability.svc:4318
          propagators: [tracecontext, baggage]
          sampler:
            type: parentbased_traceidratio
            argument: "0.25"
      opamp_bridges:
        bridge:
          endpoint: ws://opamp-server.observability.svc:4320/v1/opamp
          capabilities:
            ReportsEffectiveConfig: true
            ReportsHealth: true
```

This renders `observability/gateway-otelcol`, `observability/metrics-otelcol` (labeled for the `metrics` TargetAllocator, `mode: statefulset`), `observability/metrics-targetallocator`, `web/default-otelinst` and `observability/bridge-opampbridge`.
