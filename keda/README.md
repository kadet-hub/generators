# KEDA Generator

Kapitan kadet generator for [KEDA](https://keda.sh/) resources (`keda.sh/v1alpha1`, KEDA v2.21):

- **ScaledObject**: event-driven scaling of a Deployment, StatefulSet or any `/scale` resource
- **ScaledJob**: event-driven creation of Kubernetes Jobs
- **TriggerAuthentication**: namespaced scaler credentials
- **ClusterTriggerAuthentication**: cluster-scoped scaler credentials

Scale targets, Secrets and ServiceAccounts belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/keda@sha256:<digest>
        output_path: lib/keda
    compile:
      - output_path: manifests/keda/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/keda
```

### Inventory Contract

All keys live under `parameters.generators.keda`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `scaled_objects.<name>` | ScaledObject | `<namespace>/<name>-so` |
| `scaled_jobs.<name>` | ScaledJob | `<namespace>/<name>-sj` |
| `trigger_authentications.<name>` | TriggerAuthentication | `<namespace>/<name>-ta` |
| `cluster_trigger_authentications.<name>` | ClusterTriggerAuthentication | `<name>-cta` |

Every resource accepts `labels`, `annotations` and `spec`; namespaced kinds also accept `namespace`. `spec` is merged into the resource spec first, then the flat keys below are applied. A flat key that overrides a `spec` value logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged:

| Kind | Flat keys |
|---|---|
| ScaledObject | `scale_target_ref`, `triggers`, `min_replica_count`, `max_replica_count`, `idle_replica_count`, `polling_interval`, `cooldown_period`, `initial_cooldown_period`, `fallback`, `advanced` |
| ScaledJob | `job_target_ref`, `triggers`, `env_source_container_name`, `min_replica_count`, `max_replica_count`, `polling_interval`, `successful_jobs_history_limit`, `failed_jobs_history_limit`, `scaling_strategy`, `rollout` |
| TriggerAuthentication, ClusterTriggerAuthentication | `secret_target_ref`, `config_map_target_ref`, `env`, `pod_identity`, `hashi_corp_vault`, `azure_key_vault`, `azure_service_principal`, `aws_secret_manager`, `gcp_secret_manager`, `bound_service_account_token`, `oauth2`, `file_path` |

Shorthands:

| Input | Result |
|---|---|
| `scale_target_ref: <name>` | `scaleTargetRef: {name: <name>}` |
| trigger `authentication_ref: <name>` | `authenticationRef: {name: <name>}` |

A dict passes through, for example `authentication_ref: {name: x, kind: ClusterTriggerAuthentication}`. All other trigger keys, including the scaler-specific `metadata`, stay verbatim. Operator defaults (`minReplicaCount: 0`, `maxReplicaCount: 100`, `pollingInterval: 30`, `cooldownPeriod: 300`, scale target kind `Deployment`) are not emitted.

### Example

```yaml
parameters:
  generators:
    keda:
      namespace: workers
      scaled_objects:
        orders-consumer:
          scale_target_ref: orders-consumer
          min_replica_count: 1
          max_replica_count: 20
          triggers:
            - type: rabbitmq
              metadata:
                protocol: amqp
                queueName: orders
                mode: QueueLength
                value: "20"
              authentication_ref: rabbitmq-auth
            - type: prometheus
              metadata:
                serverAddress: http://prometheus.monitoring.svc:9090
                query: sum(rate(http_requests_total{app="orders"}[2m]))
                threshold: "100"
              authentication_ref:
                name: prometheus-auth
                kind: ClusterTriggerAuthentication
      scaled_jobs:
        report-builder:
          job_target_ref:
            template:
              spec:
                restartPolicy: Never
                containers:
                  - name: builder
                    image: registry.example.com/report-builder:1.0.0
          max_replica_count: 10
          triggers:
            - type: aws-sqs-queue
              metadata:
                queueURL: https://sqs.eu-central-1.amazonaws.com/000000000000/reports
                queueLength: "5"
                awsRegion: eu-central-1
              authentication_ref: aws-auth
      trigger_authentications:
        rabbitmq-auth:
          secret_target_ref:
            - parameter: host
              name: rabbitmq-credentials
              key: host
        aws-auth:
          pod_identity:
            provider: aws
      cluster_trigger_authentications:
        prometheus-auth:
          bound_service_account_token:
            - parameter: bearerToken
              serviceAccountName: keda-prometheus
```
