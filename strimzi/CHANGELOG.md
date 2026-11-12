# Changelog

## 1.1.2

Built for Strimzi 1.3.1. Its Kafka, KafkaNodePool, KafkaTopic and KafkaUser CRDs are unchanged, so the shipped schemas and rendered output are unchanged. Strimzi 1.3.1 adds Kafka 4.3.2 and makes it the default, which the Cluster Operator uses for a Kafka entry without `version`. The upstream files and documentation pages the README and the code comments cite differ at 1.3.1 only in Strimzi, Kafka and Bridge versions, and their links move to that tag.

## 1.1.1

Republished so the artefact carries the repository's LICENSE, which the kadet-hub registry adds to every artefact it builds since kadet-hub/registry#418. The artefacts of 1.1.0 and earlier have no LICENSE although they declare Apache-2.0. Rendered output is unchanged.

## 1.1.0

`name` on a Kafka, node pool, topic or user entry names its resource and its output key, which before always came from the entry's key. A recipe that may write only keys of its own name can then keep a cluster's name, such as the Kafka `events` with the node pool `dual` whose pods, claims, Services and Secrets carry both names. `cluster` and `strimzi.io/cluster` name the Kafka's resource. A topic or user whose `cluster` names Kafkas in two namespaces fails the compile unless it sets `namespace`. Output is unchanged for inventories without `name`.

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub.

- Built for Strimzi 1.3.0 (`kafka.strimzi.io/v1`). Ships the Kafka, KafkaNodePool, KafkaTopic and KafkaUser CRD schemas of this release (Apache-2.0) under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Kafka entries fan out into their KafkaNodePools; the replication settings of `spec.kafka.config` are derived from the broker count.
- Secure defaults: one internal TLS listener with mTLS authentication and simple authorization; no plain or external listener unless the inventory lists it; `authorization: none` and `entity_operator: false` opt out.
- Shorthands for storage, authentication, authorization and ACLs, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
