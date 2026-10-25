# strimzi generator

Status: Draft
Code: `strimzi/`, `conftest.py`
Verified against: main @ 0011e4c

## Problem and decision

The strimzi generator had no spec. Its behaviour is described in
`strimzi/README.md` and the CHANGELOG. This spec starts with the resource
names, which a recipe in kadet-hub/recipes could not set. Other behaviour
moves in here when a change touches it.

Every Kafka, KafkaNodePool and KafkaUser is named after its key, and a
KafkaTopic after a name derived from its key. kadet-hub/recipes lets a
recipe write only keys below its own name (RCP-18 there), so its `kafka`
recipe could only render a Kafka `kafka*`. The kadet-hub/examples recipe it
replaces names the Kafka `events` and its node pool `dual`. Strimzi names
the pods `events-dual-<n>`, their claims `data-0-events-dual-<n>`, the
Service `events-kafka-bootstrap` and the Secret `events-cluster-ca-cert`
after the two. A target that moves to the recipe keeps its data and its
clients' settings only if both keep their names.

## Resource names

- STZ-1: A Kafka, node pool, topic or user entry with `name` MUST render
  its resource with that name. The output key MUST take the name in place
  of the key: `<namespace>/<name>-kafka`, `<namespace>/<kafka>-<name>-kafkanodepool`
  with the Kafka's name, `<namespace>/<name>-kafkatopic` and
  `<namespace>/<name>-kafkauser`. An entry without `name` MUST keep the
  name its key gives it.

  `strimzi.io/cluster` on node pools, topics and users carries the Kafka's
  name. A topic's or user's `cluster` and `generators.strimzi.cluster` name
  the Kafka's resource, not its key, as references do in the
  cloudnative-pg and rabbitmq generators (CNPG-1, RMQ-1). A topic with
  `name` has no name derived from its key. Its Kafka topic is
  `topic_name` or, by the operator's default, the resource's name. Two node
  pools with the same name in one namespace still fail the compile, and so
  do two entries with the same output key.

  - Test: `strimzi/tests/test_names.py`; fixture target `complete`, whose
    entries `development`, `single`, `scratch-topic` and `dev-client-user`
    render `dev`, `dual`, `scratch` and `dev-client`
  - Since: #112

- STZ-2: A topic or user without `namespace` whose `cluster` names Kafkas
  in more than one namespace MUST fail the compile, naming the namespaces.

  Before `name`, a Kafka's name was its key, so it named one Kafka. Now two
  entries can render the same name in different namespaces, and the topic
  would otherwise land in either.

  - Test: `strimzi/tests/test_names.py::test_cluster_in_two_namespaces_fails`
  - Since: #112

DEC-1: The name is a key of the entry, as in the cloudnative-pg and
rabbitmq generators (DEC-1 there). Letting kadet-hub/recipes accept the
examples recipe's names was rejected for the reason DEC-1 of the
cloudnative-pg spec gives.

## Implementation inventory

| Item | Value |
|---|---|
| Resource names | `strimzi/__init__.py` (`main`) |
| Unit tests | `strimzi/tests/test_names.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider strimzi/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `strimzi/tests/fixtures`, targets `minimal` and `complete` |
