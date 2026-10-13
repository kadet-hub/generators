# Strimzi Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/strimzi/) page.

Built for Strimzi 1.3.0 (`kafka.strimzi.io/v1`, the only served and storage version of every kind, not deprecated). Strimzi 1.x runs Kafka in KRaft mode with KafkaNodePools only. The bundled `kafka.strimzi.io` JSON Schemas come from the upstream CRDs of this release (Apache-2.0).

Kapitan kadet generator for [Strimzi](https://strimzi.io/):

- **Kafka**: a KRaft cluster with its listeners, authorization, broker configuration and Entity Operator
- **KafkaNodePool**: the controller and broker pools of a Kafka entry
- **KafkaTopic**: topics, reconciled by the Topic Operator
- **KafkaUser**: users with TLS or SCRAM-SHA-512 credentials, ACLs and quotas, reconciled by the User Operator

The Cluster Operator installation, client Secrets and NetworkPolicies beyond the ones Strimzi creates belong elsewhere.

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/strimzi@sha256:<digest>
        output_path: lib/strimzi
    compile:
      - output_path: manifests/strimzi/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/strimzi
```

## Inventory contract

All keys live under `parameters.generators.strimzi`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `cluster` | | Default Kafka of topics and users, see below. |
| `kafkas.<name>` | Kafka | `<namespace>/<name>-kafka` |
| `kafkas.<name>.node_pools.<pool>` | KafkaNodePool | `<namespace>/<name>-<pool>-kafkanodepool` |
| `topics.<name>` | KafkaTopic | `<namespace>/<metadata.name>-kafkatopic` |
| `users.<name>` | KafkaUser | `<namespace>/<name>-kafkauser` |

Every entry accepts `labels`, `annotations` and `spec`; Kafka, KafkaTopic and KafkaUser entries also accept `namespace`. Labels starting with `strimzi.io/` other than `strimzi.io/cluster` fail the compile, because the Cluster Operator [rejects them](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/operator-common/src/main/java/io/strimzi/operator/common/model/Labels.java). The generator emits no `name` label: Strimzi copies CR labels onto pods, Services and Secrets, and a label value is limited to 63 characters while a topic name is not. Two entries that render the same output key, or two node pools with the same name in one namespace, fail the compile. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands. Dicts merge key by key, lists and other values replace; a flat key that overrides a `spec` value logs a warning.

| Kind | Flat key | Result |
|---|---|---|
| Kafka | `version`, `metadata_version`, `listeners`, `config` | `spec.kafka.version`, `.metadataVersion`, `.listeners`, `.config` |
| Kafka | `authorization: simple` | `spec.kafka.authorization: {type: simple}`; a dict passes through; `none` removes the default |
| Kafka | `entity_operator: false` | removes the default `entityOperator` |
| KafkaNodePool | `roles`, `replicas`, `resources` | the `spec` field of the same name |
| KafkaNodePool | `storage: 100Gi` | `type: jbod` with one `persistent-claim` volume of that size, `id: 0`, `kraftMetadata: shared`; a dict passes through |
| KafkaTopic | `topic_name`, `partitions`, `replicas`, `config` | `spec.topicName`, `.partitions`, `.replicas`, `.config` |
| KafkaUser | `authentication: tls` | `spec.authentication: {type: tls}`; a dict passes through |
| KafkaUser | `acls` | `spec.authorization: {type: simple, acls: [...]}`, each ACL expanded as below |
| KafkaUser | `quotas` | `spec.quotas` |

An ACL entry names its resource with `topic: <name>`, `group: <name>`, `transactional_id: <id>` or `cluster: true`, plus `pattern_type: prefix` for a prefix match. `operations`, `host` and `type` (`allow`, `deny`) pass through, and an entry with `resource` passes through unchanged. `patternType: literal`, `host: "*"` and `type: allow` are the operator's defaults, documented in the [CRD](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/install/cluster-operator/044-Crd-kafkauser.yaml), and are not emitted. An ACL entry without `resource` must set exactly one of `topic`, `group`, `transactional_id` and `cluster`, or the compile fails.

### Kafka defaults

A Kafka entry without `listeners` gets one internal TLS listener `tls` on port 9093 with mTLS client authentication, and `authorization: {type: simple}`, as in upstream's [tls-auth example](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/packaging/examples/security/tls-auth/kafka.yaml). The CRD requires at least one listener. No plain or anonymous listener and nothing reachable from outside the Kubernetes cluster is emitted unless the inventory lists it. With simple authorization a KafkaUser can only do what its ACLs allow; the Entity Operator, Cruise Control and Cluster Operator [are super users](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/cluster-operator/src/main/java/io/strimzi/operator/cluster/model/KafkaBrokerConfigurationBuilder.java) without an entry. `authorization: none` emits no `spec.kafka.authorization`, so every authenticated client gets full access; use it only for clusters whose access is controlled elsewhere.

`entityOperator: {topicOperator: {}, userOperator: {}}` is set because without it the KafkaTopics and KafkaUsers of this generator are not reconciled; it is part of upstream's [minimal configuration](https://strimzi.io/docs/operators/1.3.0/deploying.html#minimal_configuration_for_a_kafka_cluster). `entity_operator: false` leaves it out for clusters whose topics and users are managed by a standalone Topic or User Operator or not at all.

The replication settings of `spec.kafka.config` are derived from the broker count, the sum of `replicas` of the node pools with the `broker` role: `default.replication.factor`, `offsets.topic.replication.factor` and `transaction.state.log.replication.factor` are `min(3, brokers)`; `min.insync.replicas` and `transaction.state.log.min.isr` are one less, at least 1. That gives upstream's recommended 3 and 2 from three brokers on, as in the [minimal configuration](https://strimzi.io/docs/operators/1.3.0/deploying.html#minimal_configuration_for_a_kafka_cluster), and 1 and 1 for a single broker, as in the [single-node example](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/packaging/examples/kafka/kafka-single-node.yaml). Without the setting, Strimzi falls back to `min.insync.replicas: 1`, and Kafka's default offsets topic replication factor of 3 cannot be met by fewer than three brokers. A Kafka entry without broker pools gets no derived settings.

`version` and `metadataVersion` stay unset, so the Cluster Operator uses its default Kafka version; pin them in production to control upgrades.

### Node pools

Node pools take the namespace of their Kafka and the label `strimzi.io/cluster: <kafka>`. `replicas` defaults to 3 as in upstream's [examples](https://github.com/strimzi/strimzi-kafka-operator/blob/1.3.0/packaging/examples/kafka/kafka-persistent.yaml); `roles` and `storage` have no default and QA-7 fails without them. The pool key is `metadata.name`, and pods are named `<kafka>-<pool>-<id>`, so two clusters in one namespace need different pool keys.

### Topics and users

Topics and users get `strimzi.io/cluster` from `cluster` on the entry, then `generators.strimzi.cluster`, then the only Kafka entry if there is exactly one; otherwise the compile fails, because the operators ignore resources without the label. When the inventory defines Kafka entries, `cluster` must name one of them; a cluster defined elsewhere can only be referenced from an inventory without `kafkas`. The namespace defaults to the namespace of that Kafka entry, which the Entity Operator [watches by default](https://strimzi.io/docs/operators/1.3.0/deploying.html#proc-configuring-entity-operator-watched-namespace-str).

A topic key that is not a valid Kubernetes name, such as `Payments_EU`, becomes `spec.topicName`, as the [topic naming docs](https://strimzi.io/docs/operators/1.3.0/deploying.html#con-operator-topic-names-str) describe. `metadata.name` is derived: the key lowercased, every run of characters other than `a-z0-9` replaced by `-`, cut to 200 characters, leading and trailing `-` removed (`topic` if nothing is left), and an 8 character hash of the key appended (`payments-eu-e1ed1a98`). `partitions` and `replicas` left unset take the broker defaults `num.partitions` and `default.replication.factor`.

A KafkaUser without `authentication` gets no credentials; the generator sets none by default, because credentials plus a cluster without authorization grant full access.

## Example

```yaml
parameters:
  generators:
    strimzi:
      namespace: streaming
      kafkas:
        events:
          version: 4.3.1
          metadata_version: 4.3-IV0
          node_pools:
            controller:
              roles: [controller]
              storage: 20Gi
            broker:
              roles: [broker]
              storage: 500Gi
          config:
            auto.create.topics.enable: false
      topics:
        orders:
          partitions: 12
          config:
            retention.ms: 604800000
      users:
        orders-app:
          authentication: tls
          acls:
            - topic: orders
              operations: [Describe, Read, Write]
            - group: orders-
              pattern_type: prefix
              operations: [Read]
```

`tests/fixtures/inventory/targets/complete.yml` covers three clusters, an opt-in external TLS listener, the `authorization: none` and `entity_operator: false` opt-outs, every flat key and shorthand, and flat keys overriding `spec`.
