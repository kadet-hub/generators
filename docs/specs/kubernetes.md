# kubernetes generator

Status: Draft
Code: `kubernetes/`
Verified against: main @ 53ac637

## Problem and decision

The kubernetes generator had no spec. Its behaviour is described in
`kubernetes/README.md` and the CHANGELOG. This spec starts with the two
component keys that a migration of the cert-manager chart showed to be
wrong or too rigid: `service` and container `args`. Other behaviour moves
in here when a change touches it.

An empty `service` mapping rendered no Service, so a plain ClusterIP
Service needed `type: ClusterIP`, the API default. `args` was a list only.
reclass-rs appends lists and omegaconf merges them with `EXTEND_UNIQUE`,
so a target could not change or drop one argument that a class sets.

## Component Service

- K8S-1: A component whose `service` is a mapping, an empty one included,
  MUST render its Service.

  `service: {}` is the Service with the API defaults: `type` stays unset,
  which the API reads as ClusterIP. The port rules of the README apply
  unchanged, so an empty `service` still fails without a `service_port`.

  - Test: `kubernetes/tests/test_components.py::test_empty_service_renders_service`, `::test_empty_service_serves_api_service`; fixture target `complete`
  - Since: #102

- K8S-2: A component without `service`, or with `service: null`, MUST
  render no Service from that key.

  `null` lets a target drop a Service that a class sets. A StatefulSet
  keeps the component name as its `serviceName`.
  `additional_services` is not affected.

  - Test: `kubernetes/tests/test_components.py::test_missing_or_null_service_renders_none`, `::test_null_service_on_statefulset`
  - Since: #102

## Container args

`args` applies to the main container, `additional_containers` and
`init_containers`, which all render through the same container code.

- K8S-3: `args` as a list MUST render as that list.

  This is the form before this change. Output for it is unchanged.

  - Test: `kubernetes/tests/test_components.py::test_args_list`; fixture target `complete`
  - Since: bb1b5c1

- K8S-4: `args` as a mapping MUST render its values in the order of the
  mapping: a scalar value as one argument, a list value as its items in
  order, a `null` value as nothing.

  The keys are names only and do not appear in the output. A target
  overrides a class's argument by its key, drops it with `null` and adds
  new ones after the class's. reclass-rs and omegaconf on Kapitan 0.36.3
  both keep an overridden key in its place and append new keys, the order
  `env` already renders in. Scalars render as strings, as `env` values
  do. A list value keeps a flag and its value together, such as
  `[--leader-election-namespace, kube-system]`.

  - Test: `kubernetes/tests/test_components.py::test_args_mapping`; fixture target `complete`
  - Since: #102

- K8S-5: An `args` mapping value that is itself a mapping MUST fail the
  compile, naming the container and the key.

  - Test: `kubernetes/tests/test_components.py::test_args_mapping_value_mapping_fails`
  - Since: #102

DEC-1: `args` takes a mapping next to the list. Three alternatives were
considered. A flag map that renders `--flag: value` as `--flag=value`
would decide the argument syntax for the program; not every program
accepts `--flag=value`, and positional arguments and subcommands have no
flag. Sorting the keys, as container ports are sorted, would make users
encode the order in key names, while argument order matters to most
programs. A separate `extra_args` list appended after `args` would be a
second key for the same thing and still could not change or drop an
argument a class sets. The list form stays because existing inventories
use it; a class whose arguments targets change switches to the mapping.

## RBAC for one workload

DEC-2: There is no generator mechanism for several roles per set of
subjects; an `rbac` entry stays one role with its bindings. A recipe keeps
the chart's split: one `rbac` entry per chart role, as the chart has it.
cert-manager's controller binds 8 ClusterRoles cluster-wide to one
ServiceAccount, so its recipe has 8 entries. Role names follow the chart
and change only where the generator requires it: every name is also a
`name` label value, so `<release>-controller-approve:cert-manager-io`
needs a name without `:`.

The repeated parts, such as the subject list, `cluster_wide` and common
rule blocks, are written once in the inventory and referenced with
omegaconf interpolation and Kapitan's built-in `${merge:...}` resolver.
A `roles` map on an `rbac` entry was proposed in #101 and not taken,
because the inventory can already share these parts.

## Implementation inventory

| Item | Value |
|---|---|
| Component Service | `kubernetes/generators.py` (`_build_service_bundle`) |
| Container args | `kubernetes/base.py` (`Container.body`) |
| Unit tests | `kubernetes/tests/test_components.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider kubernetes/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `kubernetes/tests/fixtures`, targets `minimal` and `complete` |
