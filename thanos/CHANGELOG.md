# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Ships the upstream Thanos Operator CRD schemas (main commit `1b6edfb`, no upstream release yet) under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. New targets: `defaults` holds the shortest entry per kind, `precedence` the merge order defaults < `spec` < flat keys and shorthands.
- Defaults, each overridden by any inventory value (sources in README.md):
  - generator-level `object_storage_config` (`<secret>` or `{name, key}`) for ThanosStore and ThanosCompact `objectStorageConfig`, ThanosReceive `ingesterSpec.defaultObjectStorageConfig` and Stateful ThanosRuler `rulerMode.stateful.objectStorageConfig`;
  - ThanosQuery `replicaLabels: [prometheus_replica, replica, rule_replica]`, the upstream sample, instead of the CRD default `[replica]`;
  - ThanosCompact `retention` shorthand for the same retention at every resolution, overriding `spec.retentionConfig`; unset resolutions get `0d` (keep forever);
  - ThanosCompact `resourceRequirements.requests.cpu` equal to `compactConfig.compactConcurrency` (default 1) when `resource_requirements` is unset, as the Thanos compact docs recommend;
  - required CRD fields with a CRD default are emitted with that default: `replicas`, ThanosReceive router `replicationFactor` and `externalLabels`, hashring `replicas`, `externalLabels` and `tsdbConfig.retention`, ThanosRuler `ruleConfigSelector` and `rulerMode`, ThanosStore `shardingStrategy.type`.
