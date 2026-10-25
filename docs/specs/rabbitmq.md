# rabbitmq generator

Status: Draft
Code: `rabbitmq/`, `conftest.py`
Verified against: main @ 5d11df4

## Problem and decision

The rabbitmq generator had no spec. Its behaviour is described in
`rabbitmq/README.md` and the CHANGELOG. This spec starts with the resource
names, which a recipe in kadet-hub/recipes could not set. Other behaviour
moves in here when a change touches it.

Every entry of a custom resource section renders one resource named after
its key. kadet-hub/recipes lets a recipe write only keys below its own name
(RCP-18 there), so its `rabbitmq` recipe could only render a RabbitmqCluster
named `rabbitmq*`. The kadet-hub/examples recipe it replaces names the
cluster `production`. The RabbitMQ Cluster Operator names the cluster's
StatefulSet `production-server`, its claims
`persistence-production-server-<n>`, its Services and the Secret
`production-default-user` after it. A target that moves to the recipe
keeps its data and its clients' Secret only if the cluster keeps its name.

## Resource names

- RMQ-1: An entry of `rabbitmqcluster`, `queue`, `policy`, `exchange`,
  `binding`, `user`, `permission`, `vhost`, `federation` or `shovel` with
  `name` MUST render its resource with that name and write it to
  `<namespace>/<name>-<kind>`. An entry without `name` MUST keep the name
  of its key.

  The `spec.name` default of Queue, Exchange, Policy, Vhost, Federation and
  Shovel is the resource's name. An entry that keeps an existing resource
  through `name` then also keeps its name inside RabbitMQ, which the
  Messaging Topology Operator's webhook forbids changing. A
  `cluster_reference` names the cluster's resource, not its key. `secrets`
  and `configs` took `name` before.

  - Test: `rabbitmq/tests/test_names.py::test_name_names_the_resource`,
    `::test_key_names_the_resource_without_name`; fixture target `complete`
  - Since: #111

- RMQ-2: Two entries of one section that render the same name in the same
  namespace MUST fail the compile, naming both keys.

  Before, the later one would have replaced the earlier output file.

  - Test: `rabbitmq/tests/test_names.py::test_same_name_fails`
  - Since: #111

DEC-1: The name is a key of the entry, as for this generator's `secrets`
and `configs` and for every entry of the cloudnative-pg generator (CNPG-1).
Letting kadet-hub/recipes accept the examples recipe's names was rejected
for the reason DEC-1 of the cloudnative-pg spec gives.

The generator reads the inventory when its package is imported, so a unit
test needs a target before the package loads. `conftest.py` at the
repository root registers the empty target `unit-test` for that. It lies
outside every generator directory, so the gate does not scan it, and the
tests themselves import only their package and `box`, which the gate's
import policy allows.

## Implementation inventory

| Item | Value |
|---|---|
| Resource names | `rabbitmq/__init__.py` (`generate_rabbitmq_obj`) |
| Unit tests | `rabbitmq/tests/test_names.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider rabbitmq/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `rabbitmq/tests/fixtures`, targets `minimal` and `complete` |
