# Changelog

## 1.1.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.1.0

- New sections `service_monitors`, `pod_monitors` and `prometheus_rules` render ServiceMonitor, PodMonitor and PrometheusRule (`monitoring.coreos.com/v1`), so the generator covers every `monitoring.coreos.com` kind the kube-prometheus-stack chart installs. Their Prometheus Operator v0.94.1 CRD schemas are added under `schemas/`.
- New shorthands (sources in README.md):
  - `selector` given as a label map becomes `{matchLabels: ...}`, like the existing `*_selector` keys;
  - `endpoints` and `pod_metrics_endpoints` accept a port name or a list of port names and endpoint objects; each name becomes `{port: <name>}`;
  - `namespace_selector: [<namespace>, ...]` becomes `{matchNames: [...]}`. Without it a monitor only discovers its own namespace; all namespaces need an explicit `{any: true}`;
  - PrometheusRule `rules: [...]` becomes one group named after the resource. Setting both `rules` and `groups` fails the compile.
- New generator-wide key `release_label` adds `release: <value>` to ServiceMonitor, PodMonitor, Probe, ScrapeConfig and PrometheusRule, the label the kube-prometheus-stack chart (92.3.0) selects them by. No default; existing inventories compile to the same output.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Ships the upstream Prometheus Operator v0.94.1 CRD schemas and the Kubernetes 1.35.0 ServiceAccount, ClusterRole and ClusterRoleBinding schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. New target `precedence` covers the merge order `spec` < flat keys and shorthands.
- New shorthands, each a plain value where the CRD needs a nested object; the full forms still pass through unchanged (sources in README.md):
  - any `*_selector` given as a label map becomes `{matchLabels: ...}`;
  - `storage: <size>` on Prometheus, PrometheusAgent and Alertmanager becomes a `volumeClaimTemplate` with that storage request;
  - Probe `prober: <host:port>` becomes `{url: ...}` and Probe `targets: [...]` becomes `{staticConfig: {static: [...]}}`.
- No defaults are added: the fields the generator could fill are already defaulted by the CRDs or the operator, or are deployment decisions such as selectors (see README.md).
