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
| `service_monitors` | ServiceMonitor | `monitoring.coreos.com/v1` | `<namespace>/<name>-smon` |
| `pod_monitors` | PodMonitor | `monitoring.coreos.com/v1` | `<namespace>/<name>-pmon` |
| `prometheus_rules` | PrometheusRule | `monitoring.coreos.com/v1` | `<namespace>/<name>-promrule` |

`rbac: true` on a Prometheus or PrometheusAgent adds its ServiceAccount, ClusterRole and ClusterRoleBinding (see [RBAC](#rbac)).

These are all `monitoring.coreos.com` kinds the operator and the kube-prometheus-stack chart install. Built for Prometheus Operator 0.94.1. `monitoring.thanos.io` resources (Thanos Operator) belong in the `thanos` generator.

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

All keys live under `parameters.generators.prometheus_operator`. `namespace` at that level sets the default namespace, falling back to `parameters.namespace`, then `default`. `release_label` at that level is described under [kube-prometheus-stack](#kube-prometheus-stack).

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
| ServiceMonitor | `selector`, `namespace_selector`, `endpoints`, `job_label`, `target_labels`, `pod_target_labels`, `sample_limit` |
| PodMonitor | `selector`, `namespace_selector`, `pod_metrics_endpoints`, `job_label`, `pod_target_labels`, `sample_limit` |
| PrometheusRule | `groups`, `rules` (shorthand below) |

Shorthands:

| Input | Result | Source |
|---|---|---|
| `selector` and any `*_selector` except `namespace_selector`: `{<label>: <value>, ...}` | `{matchLabels: {<label>: <value>, ...}}` | [LabelSelector][selector] |
| `storage: <size>` (Prometheus, PrometheusAgent, Alertmanager) | `{volumeClaimTemplate: {spec: {resources: {requests: {storage: <size>}}}}}` | [storage guide][storage], [StorageSpec][storage-spec] |
| Probe `prober: <host:port>` | `{url: <host:port>}` | [ProberSpec][prober] |
| Probe `targets: [<target>, ...]` | `{staticConfig: {static: [<target>, ...]}}` | [ProbeTargets][probe-targets] |
| ServiceMonitor `endpoints`, PodMonitor `pod_metrics_endpoints`: `<port name>` or a list whose items are port names or endpoint objects | `[{port: <port name>}, ...]` | [Endpoint][endpoint], [PodMetricsEndpoint][pod-endpoint], [getting started][getting-started] |
| ServiceMonitor, PodMonitor `namespace_selector: [<namespace>, ...]` | `{matchNames: [<namespace>, ...]}` | [NamespaceSelector][ns-selector] |
| PrometheusRule `rules: [<rule>, ...]` | `{groups: [{name: <resource name>, rules: [<rule>, ...]}]}` | [RuleGroup][rule-group] |

A selector that contains `matchLabels` or `matchExpressions`, and `{}`, pass through unchanged, as do dict values of the other keys. `namespace_selector` dicts such as `{any: true}` pass through unchanged. Port numbers have no shorthand: a PodMonitor endpoint on a number needs `{portNumber: <n>}`, and a ServiceMonitor endpoint names a Service port. `rules` names its group after the resource; the operator writes one rule file per PrometheusRule, so the name is unique. Set `rules` or `groups`, not both; setting both fails the compile.

No defaults are added. The CRDs and the operator already default replicas, retention, intervals and port names, the operator's flags set image and version, and the Alertmanager config Secret defaults to `alertmanager-<name>`; emitting any of them would only pin today's values or override the operator's configuration. Selectors stay unset unless configured: an unset selector selects nothing and `{}` selects everything ([API reference][selector]), and choosing between them is a deployment decision. With all four of `service_monitor_selector`, `pod_monitor_selector`, `probe_selector` and `scrape_config_selector` unset, the operator leaves the Prometheus configuration unmanaged.

A ServiceMonitor or PodMonitor without `namespace_selector` discovers targets only in its own namespace ([NamespaceSelector][ns-selector]); scraping all namespaces needs `namespace_selector: {any: true}`. `selector` and ServiceMonitor `endpoints` are required by the CRD and have no default, so a monitor without them fails schema validation at compile time.

[selector]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheus_types.go#L138-L150
[storage]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/Documentation/platform/storage.md
[storage-spec]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheus_types.go#L1534-L1553
[prober]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/probe_types.go#L260-L269
[probe-targets]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/probe_types.go#L197-L225
[endpoint]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/types.go#L549-L555
[pod-endpoint]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/podmonitor_types.go#L224-L236
[getting-started]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/Documentation/developer/getting-started.md#using-servicemonitors
[ns-selector]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/types.go#L791-L810
[rule-group]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheusrule_types.go#L67-L84

### kube-prometheus-stack

The Prometheus and ThanosRuler of the [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/kube-prometheus-stack-92.3.0/charts/kube-prometheus-stack) chart select ServiceMonitors, PodMonitors, Probes, ScrapeConfigs and PrometheusRules by the label `release: <helm release name>` as long as the chart's `*SelectorNilUsesHelmValues` values keep their default `true` ([values][kps-values], [Prometheus template][kps-prometheus], [ThanosRuler template][kps-ruler]; chart 92.3.0, Prometheus Operator 0.94.1). `release_label: <helm release name>` adds that label to every ServiceMonitor, PodMonitor, Probe, ScrapeConfig and PrometheusRule this generator renders. It has no default. A `release` key in a resource's own `labels` wins over it. The chart's AlertmanagerConfig selector does not use the label, so AlertmanagerConfig does not get it.

[kps-values]: https://github.com/prometheus-community/helm-charts/blob/kube-prometheus-stack-92.3.0/charts/kube-prometheus-stack/values.yaml#L4654-L4753
[kps-prometheus]: https://github.com/prometheus-community/helm-charts/blob/kube-prometheus-stack-92.3.0/charts/kube-prometheus-stack/templates/prometheus/prometheus.yaml#L203-L307
[kps-ruler]: https://github.com/prometheus-community/helm-charts/blob/kube-prometheus-stack-92.3.0/charts/kube-prometheus-stack/templates/thanos-ruler/ruler.yaml#L64-L73

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
      service_monitors:
        alertmanager:
          labels:
            team: platform
          selector:
            operated-alertmanager: "true"
          endpoints: web
      pod_monitors:
        thanos-ruler:
          labels:
            team: platform
          selector:
            app.kubernetes.io/name: thanos-ruler
          namespace_selector:
            - monitoring
          pod_metrics_endpoints:
            - web
      prometheus_rules:
        platform-alerts:
          labels:
            team: platform
          rules:
            - alert: AlertmanagerDown
              expr: absent(up{job="alertmanager-operated"} == 1)
              for: 5m
              labels:
                severity: critical
```
