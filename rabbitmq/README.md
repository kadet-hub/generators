# RabbitMQ Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/rabbitmq/) page.

Built for RabbitMQ Cluster Operator 2.23.1 and Messaging Topology Operator 1.20.4 (`rabbitmq.com/v1beta1`, the only served and storage version of every kind, not deprecated). The bundled `rabbitmq.com` JSON Schemas are MPL-2.0, derived from the upstream CRDs of both operators (see `schemas/rabbitmq.com/NOTICE`); the generator code is Apache-2.0. ConfigMaps and Secrets are checked against the Kubernetes 1.35.0 schemas.

Kapitan kadet generator for RabbitMQ on Kubernetes:

- **RabbitmqCluster** (Cluster Operator): a RabbitMQ cluster
- **Queue**, **Exchange**, **Binding**, **Policy**, **Vhost**, **User**, **Permission**, **Federation**, **Shovel** (Messaging Topology Operator): topology inside that cluster
- **ConfigMap** and **Secret**: client configuration and the URI Secrets that Federation and Shovel read

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/rabbitmq@sha256:<digest>
        output_path: lib/rabbitmq
    compile:
      - output_path: manifests/rabbitmq/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/rabbitmq
```

## Inventory contract

All keys live under `parameters.generators.rabbitmq`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `cluster_reference` | | Default `rabbitmqClusterReference` of every topology kind, see below. |
| `rabbitmqcluster.<name>` | RabbitmqCluster | `<namespace>/<name>-rabbitmqcluster` |
| `queue.<name>`, `exchange.<name>`, `binding.<name>`, `policy.<name>`, `vhost.<name>`, `user.<name>`, `permission.<name>`, `federation.<name>`, `shovel.<name>` | the kind | `<namespace>/<name>-<kind lowercased>` |
| `rabbitmq_resources.users.<name>` | User, one Permission per `permissions` entry | `<namespace>/<name>-user`, `<namespace>/<permission>-permission` |
| `rabbitmq_resources.vhosts.<name>` | Vhost | `<namespace>/<name>-vhost` |
| `secrets.<name>` | Secret | `<namespace>/<name>-secret` |
| `configs.<name>` | ConfigMap | `<namespace>/<name>-cm` |

Every entry accepts `namespace`, `labels` and `annotations`. The CRD kinds take their spec from `spec`, passed through unchanged, and topology kinds also accept `cluster_reference`.

### Defaults and shorthands

Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides a `spec` value logs a warning.

| Input | Result |
|---|---|
| entry key of Queue, Exchange, Policy, Vhost, Federation, Shovel | `spec.name` |
| `cluster_reference: <name>` on an entry or generator-wide | `spec.rabbitmqClusterReference: {name: <name>}` |

`spec.name` is the object's name inside RabbitMQ and [required by the CRD](https://github.com/rabbitmq/messaging-topology-operator/tree/v1.20.3/api/v1beta1). The webhook [forbids changing it](https://github.com/rabbitmq/messaging-topology-operator/blob/v1.20.3/internal/webhook/v1beta1/queue_webhook.go) after creation, so set `spec.name` when the RabbitMQ name differs from the entry key, for example a queue named `analytics.reports`.

`rabbitmqClusterReference` is [required on every topology kind](https://github.com/rabbitmq/messaging-topology-operator/blob/v1.20.3/api/v1beta1/rabbitmq_cluster_reference.go). A dict passes through, for example `{name: production, namespace: messaging}` for a cluster in another namespace, which the cluster has to allow with the annotation `rabbitmq.com/topology-allowed-namespaces`.

The generator leaves operator defaults out: RabbitmqCluster `replicas: 1`, `persistence.storage: 10Gi` and the resource requests and limits ([CRD defaults](https://github.com/rabbitmq/cluster-operator/blob/v2.23.0/api/v1beta1/rabbitmqcluster_types.go)); Queue `durable: true`, set by the [defaulting webhook](https://github.com/rabbitmq/messaging-topology-operator/blob/v1.20.3/internal/webhook/v1beta1/queue_defaulter_webhook.go); `vhost: /` and `deletionPolicy: delete`. It sets no default that grants access: Permission `vhost` and `permissions`, User `tags` and the Federation and Shovel `uriSecret` stay unset unless the inventory names them, and a resource without them fails QA-7 at compile time and the API server at apply time.

### `rabbitmq_resources`

| Key | Result |
|---|---|
| `users.<name>.cluster_reference` | `rabbitmqClusterReference` of the User and its Permissions; string or dict |
| `users.<name>.secret_name` | `spec.importCredentialsSecret`; string or `{name: ...}` |
| `users.<name>.user_tags` | `spec.tags` |
| `users.<name>.permissions.<permission>` | Permission with `userReference: {name: <name>}` (or `user`/`user_reference` from the entry), `vhost` and `read_permission`, `write_permission`, `configure_permission` as `permissions.read`, `.write`, `.configure` |
| `vhosts.<name>.cluster_reference` | `rabbitmqClusterReference`; string or dict |

A Permission references the User emitted from its entry by `userReference`, because without `secret_name` the operator [generates a random username](https://github.com/rabbitmq/messaging-topology-operator/blob/v1.20.3/internal/controller/user_controller.go); `user: <RabbitMQ username>` or `user_reference` on the permission entry wins. Credentials Secrets for `secret_name` come from External Secrets or a Kapitan ref, not from this generator.

### `secrets` and `configs`

| Key | Default | Result |
|---|---|---|
| `name` | entry key | `metadata.name` |
| `data.<key>` | | one of `value`, `template` (Jinja2 file, context from `values`) or `file`; `b64_encode: true` base64-encodes the value |
| `string_data.<key>` | | Secrets only: same sources as `data`, emitted as `stringData` |
| `directory` | | every file in the directory, sorted by name; Secrets base64-encode them |
| `type` | `Opaque` | Secrets only |
| `versioned` | `false` | appends an 8 character content hash to `metadata.name`; the output key keeps the plain name |

`use_tesoro: true` emits Secret `data` and `directory` items unencoded as `stringData`. Labels and annotations under `parameters.generators.manifest.default_config.globals.config_maps` and `.secrets` are added when present. Kapitan's `--cache` does not see edits to files read through `file`, `template` and `directory`.

## Example

```yaml
parameters:
  generators:
    rabbitmq:
      namespace: messaging
      cluster_reference: production
      rabbitmqcluster:
        production:
          spec:
            replicas: 3
            persistence:
              storage: 50Gi
            rabbitmq:
              additionalPlugins:
                - rabbitmq_federation
      queue:
        orders:
          spec:
            type: quorum
            vhost: orders
      exchange:
        events:
          spec:
            type: topic
            durable: true
      policy:
        federate-events:
          spec:
            pattern: ^events$
            applyTo: exchanges
            definition:
              federation-upstream: upstream-dc
      federation:
        upstream-dc:
          spec:
            uriSecret:
              name: upstream-dc-uri
            exchange: events
      rabbitmq_resources:
        vhosts:
          orders: {}
        users:
          orders-app:
            secret_name: orders-app-credentials
            permissions:
              orders-app-orders:
                vhost: orders
                configure_permission: ^orders.*
                write_permission: ^orders.*
                read_permission: ^orders.*
      secrets:
        upstream-dc-uri:
          string_data:
            uri:
              value: amqps://upstream.example.com:5671?auth_mechanism=external
```

`tests/fixtures/inventory/targets/complete.yml` covers every kind, a cross-namespace reference and a flat key overriding `spec`.
