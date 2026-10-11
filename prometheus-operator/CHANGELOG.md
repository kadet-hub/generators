# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Ships the upstream Prometheus Operator v0.94.1 CRD schemas and the Kubernetes 1.35.0 ServiceAccount, ClusterRole and ClusterRoleBinding schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. New target `precedence` covers the merge order `spec` < flat keys and shorthands.
- New shorthands, each a plain value where the CRD needs a nested object; the full forms still pass through unchanged (sources in README.md):
  - any `*_selector` given as a label map becomes `{matchLabels: ...}`;
  - `storage: <size>` on Prometheus, PrometheusAgent and Alertmanager becomes a `volumeClaimTemplate` with that storage request;
  - Probe `prober: <host:port>` becomes `{url: ...}` and Probe `targets: [...]` becomes `{staticConfig: {static: [...]}}`.
- No defaults are added: the fields the generator could fill are already defaulted by the CRDs or the operator, or are deployment decisions such as selectors (see README.md).
