# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Loki Operator 0.11.0. Ships no JSON Schemas because the upstream CRDs are AGPL-3.0-only, so the gate does not schema-check the output.
- New LokiStack defaults, documented with their sources in the README. Values set in the inventory win.
  - `storage: <type>` expands to `storage.secret` with `name: <stack name>-<type>`.
  - `storage` without `schemas` gets `v13` effective from `2023-10-15` instead of the CRD default `v11`. A stack already running on `v11` must set `storage.schemas` explicitly; the operator rejects dropping a schema that is in use.
  - `tenants` without `mode` gets `passthrough`, `dynamic` or `static` from its content.
  - Rules are bound to their stack: AlertingRules and RecordingRules get the label `loki.grafana.com/lokistack: <stack>` for the stack in their new `loki_stack` key, or for the only stack, and a stack with `rules.enabled` but no `rules.selector` selects that label, plus its rules' other namespaces by `kubernetes.io/metadata.name`.
- Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands.
- The fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
