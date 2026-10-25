# Changelog

## 1.1.0

`name` on an entry of a custom resource section names its resource, its output file and, for the kinds with `spec.name`, the default of `spec.name`, which before always took the entry's key. A recipe that may write only keys of its own name can then keep a resource name, such as the RabbitmqCluster `production` whose StatefulSet, claims and Secrets carry its name. Two entries of a section with the same name in one namespace now fail the compile; before, the later one replaced the earlier output file. Output is unchanged for inventories without `name` on those sections and without such a collision.

## 1.0.3

Built for RabbitMQ Cluster Operator 2.23.1 and Messaging Topology Operator 1.20.4. The Federation schema and CRD gain the upstream default `reconnectDelay: 1`; the other `rabbitmq.com` schemas and CRDs are unchanged. ConfigMaps and Secrets are checked against the Kubernetes 1.37.1 schemas instead of 1.35.0, which differ only in a ConfigMap description. Rendered output is unchanged.

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for RabbitMQ Cluster Operator 2.23.0 and Messaging Topology Operator 1.20.3 (`rabbitmq.com/v1beta1`). Ships the CRD schemas of these releases, MPL-2.0 with the notice in `schemas/rabbitmq.com/NOTICE`, and the Kubernetes 1.35.0 ConfigMap and Secret schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- New defaults and shorthand, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
  - Queue, Exchange, Policy, Vhost, Federation and Shovel get `spec.name` from the entry key; the CRD requires it.
  - `cluster_reference: <name>`, per entry or generator-wide, sets `rabbitmqClusterReference: {name: <name>}` on every topology kind; a dict passes through.
- `rabbitmq_resources` users and vhosts without `cluster_reference` no longer emit `rabbitmqClusterReference: null`; they take the generator-wide `cluster_reference` or leave the field out.
- Breaking: Permissions from `rabbitmq_resources.users.<name>.permissions` emit `userReference: {name: <name>}` instead of `user: <name>`. With generated credentials the RabbitMQ username is random, so `user: <name>` pointed at a user that does not exist. A permission entry can set `user` or `user_reference` explicitly. Migration: the webhook [forbids changing `user` or `userReference`](https://github.com/rabbitmq/messaging-topology-operator/blob/v1.20.3/internal/webhook/v1beta1/permission_webhook.go) on an existing Permission, so delete each affected Permission and apply it again; set `user: <name>` on the entry to keep the old output instead.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
