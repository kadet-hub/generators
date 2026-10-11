# Prometheus Operator Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/prometheus-operator/)): pin a released version by digest from its catalog page.

Kapitan kadet generator for [Prometheus Operator](https://prometheus-operator.dev/) custom resources (`monitoring.coreos.com`):

| Section | Kind | apiVersion | Output key |
|---|---|---|---|
| `prometheuses` | Prometheus | `monitoring.coreos.com/v1` | `<namespace>/<name>-prom` |
| `prometheus_agents` | PrometheusAgent | `monitoring.coreos.com/v1alpha1` | `<namespace>/<name>-promagent` |
| `alertmanagers` | Alertmanager | `monitoring.coreos.com/v1` | `<namespace>/<name>-am` |
| `alertmanager_configs` | AlertmanagerConfig | `monitoring.coreos.com/v1alpha1` | `<namespace>/<name>-amcfg` |
| `thanos_rulers` | ThanosRuler | `monitoring.coreos.com/v1` | `<namespace>/<name>-ruler` |
| `probes` | Probe | `monitoring.coreos.com/v1` | `<namespace>/<name>-prb` |
| `scrape_configs` | ScrapeConfig | `monitoring.coreos.com/v1alpha1` | `<namespace>/<name>-scfg` |

`rbac: true` on a Prometheus or PrometheusAgent adds its ServiceAccount, ClusterRole and ClusterRoleBinding (see [RBAC](#rbac)).

Built for Prometheus Operator 0.94.1. ServiceMonitor, PodMonitor and PrometheusRule belong in the `kubernetes` generator. `monitoring.thanos.io` resources (Thanos Operator) belong in the `thanos` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/prometheus-operator@sha256:<digest>
        output_path: lib/prometheus-operator
    compile:
      - output_path: manifests/prometheus-operator/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/prometheus-operator
```

### Inventory Contract

All keys live under `parameters.generators.prometheus_operator`. `namespace` at that level sets the default namespace, falling back to `parameters.namespace`, then `default`.

Every resource entry accepts `namespace`, `labels`, `annotations` and `spec`. For the same field, `spec` loses to the flat keys and shorthands below; a flat key or shorthand that overrides a `spec` value logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged unless a shorthand applies:

| Kind | Flat keys |
|---|---|
| Prometheus, PrometheusAgent | `service_account_name`, `replicas`, `shards`, `version`, `image`, `scrape_interval`, `external_labels`, `resources`, `storage`, `remote_write`, `service_monitor_selector`, `service_monitor_namespace_selector`, `pod_monitor_selector`, `pod_monitor_namespace_selector`, `probe_selector`, `probe_namespace_selector`, `scrape_config_selector`, `scrape_config_namespace_selector` |
| Prometheus only | `retention`, `retention_size`, `evaluation_interval`, `rule_selector`, `rule_namespace_selector`, `alerting` |
| PrometheusAgent only | `mode` |
| Alertmanager | `replicas`, `retention`, `service_account_name`, `config_secret`, `alertmanager_config_selector`, `alertmanager_config_namespace_selector`, `storage` |
| AlertmanagerConfig | `route`, `receivers`, `inhibit_rules`, `mute_time_intervals` |
| ThanosRuler | `replicas`, `retention`, `evaluation_interval`, `rule_selector`, `rule_namespace_selector`, `query_endpoints`, `query_config`, `alertmanagers_url`, `alertmanagers_config`, `service_account_name` |
| Probe | `prober`, `module`, `targets`, `interval`, `scrape_timeout`, `job_name` |
| ScrapeConfig | `job_name`, `static_configs`, `kubernetes_sd_configs` (`kubernetesSDConfigs`), `http_sd_configs` (`httpSDConfigs`), `scrape_interval`, `metrics_path`, `scheme` |

Shorthands:

| Input | Result | Source |
|---|---|---|
| any `*_selector: {<label>: <value>, ...}` | `{matchLabels: {<label>: <value>, ...}}` | [LabelSelector][selector] |
| `storage: <size>` (Prometheus, PrometheusAgent, Alertmanager) | `{volumeClaimTemplate: {spec: {resources: {requests: {storage: <size>}}}}}` | [storage guide][storage], [StorageSpec][storage-spec] |
| Probe `prober: <host:port>` | `{url: <host:port>}` | [ProberSpec][prober] |
| Probe `targets: [<target>, ...]` | `{staticConfig: {static: [<target>, ...]}}` | [ProbeTargets][probe-targets] |

A selector that contains `matchLabels` or `matchExpressions`, and `{}`, pass through unchanged, as do dict values of the other keys.

No defaults are added. The CRDs and the operator already default replicas, retention, intervals and port names, the operator's flags set image and version, and the Alertmanager config Secret defaults to `alertmanager-<name>`; emitting any of them would only pin today's values or override the operator's configuration. Selectors stay unset unless configured: an unset selector selects nothing and `{}` selects everything ([API reference][selector]), and choosing between them is a deployment decision. With all four of `service_monitor_selector`, `pod_monitor_selector`, `probe_selector` and `scrape_config_selector` unset, the operator leaves the Prometheus configuration unmanaged.

[selector]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheus_types.go#L138-L150
[storage]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/Documentation/platform/storage.md
[storage-spec]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheus_types.go#L1534-L1553
[prober]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/probe_types.go#L260-L269
[probe-targets]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/probe_types.go#L197-L225

### RBAC

`rbac: true` on a Prometheus or PrometheusAgent entry adds the RBAC the [upstream RBAC guide](https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/Documentation/platform/rbac.md) lists as a prerequisite. Absent or `false` adds nothing.

| Resource | Output key | Name |
|---|---|---|
| ServiceAccount | `<namespace>/<sa>-sa` | `<sa>` |
| ClusterRole | `<namespace>-<name>-clusterrole` | `<namespace>-<name>` |
| ClusterRoleBinding | `<namespace>-<name>-crb` | `<namespace>-<name>` |

`<sa>` is `service_account_name` (or `serviceAccountName` in `spec`), else the CR name; `spec.serviceAccountName` is set to it. The ClusterRole grants get/list/watch on `nodes`, `nodes/metrics`, `services`, `endpoints`, `pods`, `endpointslices` and `ingresses`, get on `configmaps` and get on `/metrics`. The CR's `labels` apply to all three. A Prometheus and a PrometheusAgent with the same name and namespace cannot both set `rbac: true`.

### Example

```yaml
parameters:
  generators:
    prometheus_operator:
      namespace: monitoring
      prometheuses:
        main:
          rbac: true
          replicas: 2
          retention: 15d
          storage: 50Gi
          service_monitor_selector:
            team: platform
          service_monitor_namespace_selector: {}
          rule_selector:
            team: platform
          alerting:
            alertmanagers:
              - name: alertmanager-operated
                namespace: monitoring
                port: web
          spec:
            enableAdminAPI: false
      prometheus_agents:
        agent:
          rbac: true
          service_account_name: prometheus-agent
          remote_write:
            - url: https://metrics.example.com/api/v1/write
          pod_monitor_selector:
            team: platform
      alertmanagers:
        main:
          replicas: 3
          storage: 1Gi
          alertmanager_config_selector:
            team: platform
      alertmanager_configs:
        platform:
          labels:
            team: platform
          route:
            receiver: team-mail
            groupBy:
              - alertname
          receivers:
            - name: team-mail
              emailConfigs:
                - to: oncall@example.com
      thanos_rulers:
        main:
          query_endpoints:
            - dnssrv+_http._tcp.thanos-query.monitoring.svc
          rule_selector:
            team: platform
          alertmanagers_url:
            - dnssrv+_web._tcp.alertmanager-operated.monitoring.svc
      probes:
        website:
          module: http_2xx
          prober: blackbox-exporter.monitoring.svc:9115
          targets:
            - https://example.com
      scrape_configs:
        node-exporter:
          static_configs:
            - targets:
                - node-1.example.com:9100
          metrics_path: /metrics
```
