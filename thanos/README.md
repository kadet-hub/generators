# Thanos Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/thanos/)): pin a released version by digest from its catalog page.

Kapitan kadet generator for [Thanos Operator](https://github.com/thanos-community/thanos-operator) resources (`monitoring.thanos.io/v1alpha1`):

- **ThanosQuery**: Thanos Querier, optionally fronted by Query Frontend
- **ThanosReceive**: Receive router and ingester hashrings
- **ThanosRuler**: rule evaluation against Thanos Query
- **ThanosStore**: Store Gateway serving blocks from object storage
- **ThanosCompact**: compaction, downsampling and retention of object storage blocks

Built for Thanos Operator main@1b6edfb. The Thanos Operator has no release yet and marks its APIs alpha, so the schemas are pinned to `main` commit `1b6edfbba0e54af83870b158ee1124e499455b43`; expect breaking changes when upstream moves.

`monitoring.coreos.com/v1` ThanosRuler (Prometheus Operator) is a different API and belongs to the `prometheus-operator` generator. The Thanos sidecar is configured on the Prometheus Operator `Prometheus` resource. The object storage Secret belongs in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/thanos@sha256:<digest>
        output_path: lib/thanos
    compile:
      - output_path: manifests/thanos/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/thanos
```

### Inventory Contract

All keys live under `parameters.generators.thanos`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `object_storage_config` | | Object storage Secret shared by every kind that needs one, as `<secret>` or `{name, key}`. See [Defaults](#defaults). |
| `thanos_queries.<name>` | ThanosQuery | `<namespace>/<name>-thanosquery` |
| `thanos_receives.<name>` | ThanosReceive | `<namespace>/<name>-thanosreceive` |
| `thanos_rulers.<name>` | ThanosRuler | `<namespace>/<name>-thanosruler` |
| `thanos_stores.<name>` | ThanosStore | `<namespace>/<name>-thanosstore` |
| `thanos_compacts.<name>` | ThanosCompact | `<namespace>/<name>-thanoscompact` |

Every resource accepts `namespace`, `labels`, `annotations` and `spec`. `labels` and `annotations` set the custom resource metadata; the CRD fields `spec.labels` and `spec.annotations`, which the operator copies to the generated workloads, are set through `spec`. For the same field, defaults lose to `spec`, and `spec` loses to the flat keys and shorthands below; a flat key or shorthand that overrides a `spec` value logs a warning.

Flat keys are the snake_case spelling of the top-level CRD `spec` fields; values pass through unchanged.

Common to ThanosQuery, ThanosRuler, ThanosStore and ThanosCompact: `additional_args`, `additional_containers`, `additional_env`, `additional_ports`, `additional_service_ports`, `additional_volume_mounts`, `additional_volumes`, `affinity`, `base_image`, `config_maps`, `image_pull_policy`, `image_pull_secrets`, `log_format`, `log_level`, `node_selector`, `paused`, `pod_disruption_budget_config`, `resource_requirements`, `secrets`, `security_context`, `tolerations`, `topology_spread_constraints`, `version`.

StatefulSet fields, on ThanosReceive, ThanosRuler, ThanosStore and ThanosCompact: `min_ready_seconds`, `persistent_volume_claim_retention_policy`, `pod_management_policy`, `termination_grace_period_seconds`.

| Kind | Additional flat keys |
|---|---|
| ThanosQuery | `replicas`, `custom_store_label_selector`, `grpc_proxy_strategy`, `query_frontend`, `replica_labels`, `telemetry_quantiles`, `web_config` |
| ThanosReceive | `router_spec`, `ingester_spec`, `paused` |
| ThanosRuler | `replicas`, `alertmanager_url`, `alert_label_drop`, `evaluation_interval`, `query_label_selector`, `rule_config_selector`, `rule_tenancy_config`, `ruler_mode`, `storage` |
| ThanosStore | `replicas`, `object_storage_config`, `sharding_strategy`, `storage`, `block_config`, `caching_bucket_config`, `ignore_deletion_marks_delay`, `index_cache_config`, `index_header_config`, `store_limits_options`, `time_range_config` |
| ThanosCompact | `object_storage_config`, `retention`, `retention_config`, `storage`, `block_config`, `block_viewer_global_sync`, `compact_config`, `debug_config`, `downsampling_config`, `sharding_config`, `time_range_config`, `vertical_compaction_config` |

Shorthands:

| Input | Result |
|---|---|
| `object_storage_config: <secret>` (generator, ThanosStore, ThanosCompact) | `{name: <secret>, key: thanos.yaml}` |
| ThanosCompact `retention: <duration>` | the same retention for `raw`, `fiveMinutes` and `oneHour`; resolutions set in `retention_config` keep their value |

`thanos.yaml` is the Secret key used throughout the upstream samples and docs. A dict passes through, for a different key. On a ThanosReceive or ThanosRuler, set a different Secret through `ingester_spec.defaultObjectStorageConfig` or `ruler_mode.stateful.objectStorageConfig` in the full `{name, key}` form.

### Defaults

A field the inventory leaves out is filled as below. Fields the CRD marks required get the CRD's own default, so the shortest entry passes offline schema validation and behaves as if the API server had defaulted it. Other CRD defaults (`imagePullPolicy: IfNotPresent`, `logFormat: logfmt` and so on) are left to the API server.

| Kind | Field | Default | Source |
|---|---|---|---|
| ThanosStore, ThanosCompact | `objectStorageConfig` | generator `object_storage_config` | required, no CRD default ([store][store-types], [compact][compact-types]); the [samples] share one Secret across components |
| ThanosReceive | `ingesterSpec.defaultObjectStorageConfig` | generator `object_storage_config` | required, no CRD default ([receive][receive-ingester]) |
| ThanosRuler | `rulerMode.stateful.objectStorageConfig` | generator `object_storage_config` | required in Stateful mode, no CRD default ([ruler][ruler-mode]) |
| ThanosQuery | `replicaLabels` | `[prometheus_replica, replica, rule_replica]` | [upstream sample][query-sample]: the replica labels of [Prometheus Operator][prometheus-replica], ThanosReceive ingesters ([receive][receive-hashring]) and ThanosRuler ([ruler][ruler-mode]); the CRD default `[replica]` ([query][query-types]) deduplicates only the ingesters |
| ThanosCompact | `retentionConfig.{raw,fiveMinutes,oneHour}` | `retention`, else `0d` (keep forever) | CRD default `0d` ([compact][compact-retention]); Thanos recommends no retention, or the same retention for every resolution ([Thanos compact docs][thanos-retention], [downsampling note][thanos-downsampling]) |
| ThanosCompact | `resourceRequirements` | `requests.cpu` = `compactConfig.compactConcurrency`, else `1` | "give `--compact.concurrency` amount of CPU cores" ([Thanos compact docs][thanos-compact-cpu]); the operator passes `compactConcurrency` as that flag ([builder][compact-builder]), whose default is `1` ([flags][thanos-compact-flags]). Only set when `resource_requirements` is absent. |
| ThanosQuery, ThanosRuler, ThanosStore | `replicas` | `1` | CRD default ([query][query-types], [ruler][ruler-types], [store][store-types]) |
| ThanosReceive | `routerSpec.{replicas,replicationFactor,externalLabels}` | `1`, `1`, `{receive: "true"}` | CRD default ([receive][receive-router]) |
| ThanosReceive | each hashring's `replicas`, `externalLabels`, `tsdbConfig.retention` | `1`, `{replica: $(POD_NAME)}`, `2h` | CRD default ([receive][receive-hashring], [TSDB][tsdb-config]) |
| ThanosRuler | `ruleConfigSelector` | `{matchLabels: {operator.thanos.io/prometheus-rule: "true"}}` | CRD default ([ruler][ruler-types]) |
| ThanosRuler | `rulerMode.type`, and in Stateful mode `stateful.{retention,externalLabels}` | `Stateful`, `2h`, `{rule_replica: $(NAME)}` | CRD default ([ruler][ruler-mode]) |
| ThanosStore | `shardingStrategy.type` | `block` | CRD default ([store][store-sharding]) |

The Thanos documentation is the one for v0.42.0, the version the operator deploys by default ([options][operator-version]). No other component gets resource requests; neither the operator nor the Thanos docs give sizing values for them. The receive replication factor stays at the CRD default `1`, since the Thanos docs give no recommended value; with `replicationFactor` 3 or 5 every hashring needs at least that many `replicas` to reach the write quorum ([Thanos receive docs][thanos-quorum]). Fields without a default (`storage.size`, ThanosRuler `alertmanagerURL`, ThanosReceive `hashrings`) stay required in the inventory.

[samples]: https://github.com/thanos-community/thanos-operator/tree/1b6edfbba0e54af83870b158ee1124e499455b43/config/samples
[query-sample]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/config/samples/v1alpha1_thanosquery.yaml
[query-types]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosquery_types.go#L27-L38
[receive-router]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosreceive_types.go#L62-L85
[receive-ingester]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosreceive_types.go#L94-L98
[receive-hashring]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosreceive_types.go#L123-L135
[tsdb-config]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/types.go#L58-L64
[ruler-types]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosruler_types.go#L30-L52
[ruler-mode]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosruler_types.go#L96-L121
[store-types]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosstore_types.go#L30-L37
[store-sharding]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanosstore_types.go#L91-L96
[compact-types]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanoscompact_types.go#L30-L39
[compact-retention]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/api/v1alpha1/thanoscompact_types.go#L167-L185
[compact-builder]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/internal/pkg/manifests/compact/builder.go#L437
[operator-version]: https://github.com/thanos-community/thanos-operator/blob/1b6edfbba0e54af83870b158ee1124e499455b43/internal/pkg/manifests/options.go#L20-L21
[prometheus-replica]: https://github.com/prometheus-operator/prometheus-operator/blob/v0.94.1/pkg/apis/monitoring/v1/prometheus_types.go#L307-L313
[thanos-retention]: https://github.com/thanos-io/thanos/blob/v0.42.0/docs/components/compact.md#L121-L127
[thanos-downsampling]: https://github.com/thanos-io/thanos/blob/v0.42.0/docs/components/compact.md#L157-L181
[thanos-compact-cpu]: https://github.com/thanos-io/thanos/blob/v0.42.0/docs/components/compact.md#L201-L205
[thanos-compact-flags]: https://github.com/thanos-io/thanos/blob/v0.42.0/docs/components/compact.md#L388
[thanos-quorum]: https://github.com/thanos-io/thanos/blob/v0.42.0/docs/components/receive.md#L371-L389

### Example

```yaml
parameters:
  generators:
    thanos:
      namespace: monitoring
      object_storage_config: thanos-object-storage
      thanos_queries:
        global:
          replicas: 2
          query_frontend:
            replicas: 2
            logQueriesLongerThan: 10s
      thanos_receives:
        ingest:
          router_spec:
            replicas: 3
            replicationFactor: 3
          ingester_spec:
            hashrings:
              - name: default
                replicas: 3
                storage:
                  size: 10Gi
      thanos_rulers:
        rules:
          alertmanager_url: http://alertmanager.monitoring.svc:9093
          storage:
            size: 1Gi
      thanos_stores:
        gateway:
          replicas: 2
          storage:
            size: 10Gi
      thanos_compacts:
        compactor:
          retention: 1y
          storage:
            size: 50Gi
```

Every kind reads its object storage from the Secret `thanos-object-storage`, key `thanos.yaml`; the query deduplicates on the replica labels of Prometheus, the ingesters and the ruler; the compactor keeps every resolution for one year and requests one CPU.
