# Changelog

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub.

- Built for Strimzi 1.3.0 (`kafka.strimzi.io/v1`). Ships the Kafka, KafkaNodePool, KafkaTopic and KafkaUser CRD schemas of this release (Apache-2.0) under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Kafka entries fan out into their KafkaNodePools; the replication settings of `spec.kafka.config` are derived from the broker count.
- Secure defaults: one internal TLS listener with mTLS authentication and simple authorization; no plain or external listener unless the inventory lists it; `authorization: none` and `entity_operator: false` opt out.
- Shorthands for storage, authentication, authorization and ACLs, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
