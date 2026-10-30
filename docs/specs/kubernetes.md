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

## Routes to a Gateway outside the inventory

A route rendered below `gateways.<gateway>.routes` attaches to the Gateway
of that entry, which the generator renders too. A chart such as Nextcloud's
renders only an HTTPRoute, attached to a Gateway the cluster already runs,
and redirects `/.well-known/caldav` to `/remote.php/dav` with a path
redirect. A recipe of that chart could render neither. kadet-hub/recipes
needs both for its `nextcloud` recipe (RCP-56 there).

`generators.kubernetes.routes.<name>` takes the keys of a Gateway's route,
`type`, `namespace`, `hostnames`, `rules`, `annotations`, `labels`,
`api_version` and `enabled`, plus `parent_refs`. Each entry of
`parent_refs` has `name` and optionally `namespace`, `section_name` and
`port`, and renders as a `parentRefs` entry with `name`, `namespace`,
`sectionName` and `port`. The API defaults `group` and `kind` to a
Gateway. The route's namespace resolves as a Gateway's does, from its
`namespace`, `generators.kubernetes.namespace` or `parameters.namespace`.
The output file is `<namespace>/<name>-route`.

Whether the Gateway admits the route is decided by the Gateway's listener
(`allowedRoutes`), not by the route, so a route in another namespace than
its Gateway needs no ReferenceGrant.

- K8S-6: Every enabled entry of `generators.kubernetes.routes` MUST render
  one route of its `type`, HTTPRoute by default, with a `parentRefs` entry
  for each entry of `parent_refs`, and MUST render no Gateway.

  - Test: `kubernetes/tests/test_components.py::test_route_parent_refs`; fixture target `complete`
  - Since: #107

- K8S-7: A `routes` entry without `parent_refs`, or with a `parent_refs`
  entry without `name`, MUST fail the compile, naming the route.

  - Test: `kubernetes/tests/test_components.py::test_route_without_parent_fails`
  - Since: #107

- K8S-8: A redirect rule with `replace_full_path` MUST render
  `path: {type: ReplaceFullPath, replaceFullPath: <value>}`, one with
  `replace_prefix_match` `path: {type: ReplacePrefixMatch,
  replacePrefixMatch: <value>}`. A rule with both MUST fail the compile.

  This holds for the routes of `gateways` and of `routes`. A path redirect
  is Extended support in Gateway API (`HTTPRoutePathRedirect`), and the API
  accepts `ReplacePrefixMatch` only on a rule whose match is a
  `PathPrefix`. An empty `replace_prefix_match` strips the matched prefix.

  - Test: `kubernetes/tests/test_components.py::test_redirect_path`, `::test_redirect_both_paths_fails`; fixture target `complete`
  - Since: #107

DEC-3: Routes to a Gateway outside the inventory get a section of their
own. A flag on `gateways.<gateway>` that skips the Gateway was considered.
The key of a `gateways` entry is the Gateway's name, which for a route to
the user's Gateway is the user's choice. A recipe may only write keys below
its own name (RCP-18 in kadet-hub/recipes), so its route needs a key of
its own, and `parent_refs` can name the Gateway from the inventory. A
`routes` entry can also attach to several Gateways.

## Webhooks with a CA from their server

A webhook with `failurePolicy: Fail` and no `clientConfig.caBundle` fails
the compile, unless a cert-manager CA injection annotation is set, because
the API server could call it without a CA to verify. Some operators write
the CA themselves. The CloudNativePG operator creates its serving
certificate and patches `caBundle` into its webhook configurations at
start, so its chart renders them without one.

- K8S-9: A component with `webhook_ca_injected: true` MUST render its
  webhooks without `caBundle` and with `failurePolicy: Fail` without
  failing. Without that key or a CA injection annotation such a webhook
  MUST still fail the compile.

  The key covers `webhooks` and `validating_webhooks` of the component and
  renders nothing. It states that something outside the inventory writes
  the CA. Until it does, every call of the webhook fails.

  - Test: `kubernetes/tests/test_components.py::test_webhook_ca_injected`, `::test_webhook_without_ca_fails`
  - Since: #107

The same operator patches its webhook configurations by name. CloudNativePG
1.30.1 looks for `cnpg-mutating-webhook-configuration` and
`cnpg-validating-webhook-configuration` (`internal/configuration` of
cloudnative-pg), while the generator names both `<namespace>-<component>`.
The operator then writes no CA into them, and every call fails.

- K8S-10: A component's `webhook_configuration_name` MUST name its
  MutatingWebhookConfiguration and `validating_webhook_configuration_name`
  its ValidatingWebhookConfiguration. Without them both MUST keep the name
  `<namespace>-<component>`.

  The two kinds take separate keys because an operator may expect two
  different names, as CloudNativePG does. A name the user sets is not
  scoped by namespace, so two components that set the same one collide.

  - Test: `kubernetes/tests/test_components.py::test_webhook_configuration_names`, `::test_webhook_configuration_default_names`
  - Since: #109

## Volume mounts

A container's `volume_mounts` is a mapping whose keys name the volumes, so
a volume can be mounted once per container. Nextcloud's chart mounts its
claim `nextcloud-main` at six paths, each with its own `subPath`.

- K8S-11: A `volume_mounts` entry with `volume` MUST mount that volume, and
  its key MUST then name only the mount. An entry without `volume` MUST
  mount the volume of its key, as before.

  - Test: `kubernetes/tests/test_components.py::test_volume_mounts_of_one_volume`, `::test_volume_mount_named_by_key`
  - Since: #109

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

## Chainsaw tests

The compile entry with `function: generate_chainsaw_asserts` wrote one
Chainsaw StepTemplate per component, and every project wrote the Test
that runs them by hand. That Test only lists the templates, so it fell
out of step whenever a component was added or removed.

- K8S-12: `generate_chainsaw_asserts` MUST also write one Chainsaw Test
  per namespace, at `<namespace>/chainsaw-test`, whose steps use that
  namespace's StepTemplates in component order.

  The Test is named after the namespace and sets `spec.namespace` to it.
  Chainsaw then asserts in the namespace the workloads were applied to,
  and creates no ephemeral namespace. A namespace whose components are
  all CronJobs has no StepTemplate and gets no Test.

  Kapitan names the files `.yml` when the compile entry sets
  `output_type: yml` and `.yaml` otherwise, so the step paths take the
  extension of the entry with `function: generate_chainsaw_asserts`.
  Chainsaw 0.2.15 finds `chainsaw-test.yaml` or, without one,
  `chainsaw-test.yml`, and resolves `use.template` relative to the
  Test's directory.

  The Test sets no timeouts: `chainsaw test --assert-timeout` or a
  Chainsaw configuration sets them for a run.

  - Test: `kubernetes/tests/test_components.py::test_chainsaw_test_per_namespace`, `::test_chainsaw_test_uses_output_type`, `::test_no_chainsaw_test_for_cronjobs_only`; fixture target `complete`; `manual:` `chainsaw test --no-cluster` on the compiled fixture loads both Tests and their templates
  - Since: this change

- K8S-13: `generators.kubernetes.chainsaw.workloads.<name>` with `kind`
  and an optional `namespace` MUST render the same StepTemplate and Test
  step as a component, for a workload that the generator does not
  render, such as one from Kapitan's helm input.

  `kind` is one of Deployment, StatefulSet, DaemonSet and Job; any other
  value fails the compile. `namespace` defaults to `parameters.namespace`,
  as for a component. A name that a component of the same namespace
  already asserts fails the compile, because both write one file.

  The generator does not know the replica count of such a workload, so
  the assert reads it from the object. A Deployment or StatefulSet is
  ready when it is rolled out as `kubectl rollout status` checks it:
  `status.observedGeneration` has reached `metadata.generation`, and
  `updatedReplicas` and `availableReplicas` (StatefulSet:
  `readyReplicas`) have reached `spec.replicas`. The comparison is `>=`
  and not `==`, because Chainsaw's `==` compares the literal `` `0` `` and
  `spec.replicas` by type and never matches at 0 replicas. Because of
  `updatedReplicas`, a StatefulSet
  with the `OnDelete` update strategy counts as rolled out only once its
  pods run the current revision. A DaemonSet is ready as for a
  component, a Job when its `Complete` condition is `True`.

  - Test: `kubernetes/tests/test_components.py::test_chainsaw_workloads_rendered_elsewhere`, `::test_chainsaw_workload_kind_must_be_known`, `::test_chainsaw_workload_and_component_of_one_name_fail`; fixture target `complete`; `manual:` Chainsaw 0.2.15 on kind: the four kinds and a Deployment with 0 replicas pass, a Deployment and a StatefulSet with an image that does not exist fail
  - Since: this change

- K8S-14: `generators.kubernetes.chainsaw.resources.<key>` with
  `api_version`, `kind` and a `status` mapping MUST render a StepTemplate
  that asserts the object's status, and a step in its namespace's Test
  after the readiness steps.

  `name` defaults to the key and `namespace` to `parameters.namespace`.
  `status` becomes the assert's `status` block unchanged, so it can hold
  plain values or Chainsaw expressions, such as `phase: Ready` on a
  CephCluster. An entry without `api_version`, `kind` or a `status`
  mapping fails the compile. The kind's schema is not checked. A key that
  a component or a `workloads` entry of the same namespace already uses
  fails the compile, because both write one file.

  - Test: `kubernetes/tests/test_components.py::test_chainsaw_resource_status_assert`, `::test_chainsaw_resource_needs_kind_and_status`, `::test_no_chainsaw_keys_render_as_before`; fixture target `complete`; `manual:` Chainsaw 0.2.15 on kind against a custom resource: fails without status and with a wrong nested field, passes once the status matches
  - Since: this change

## Implementation inventory

| Item | Value |
|---|---|
| Component Service | `kubernetes/generators.py` (`_build_service_bundle`) |
| Container args | `kubernetes/base.py` (`Container.body`) |
| Routes, path redirects | `kubernetes/generators.py` (`_generate_routes`), `kubernetes/networking.py` (`GatewayRoute`) |
| Webhook CA | `kubernetes/webhooks.py` (`_webhooks`) |
| Webhook configuration names | `kubernetes/webhooks.py` (`MutatingWebhookConfiguration`, `ValidatingWebhookConfiguration`) |
| Chainsaw Test, external workloads | `kubernetes/generators.py` (`generate_chainsaw_asserts`, `_EXTERNAL_WORKLOADS`, `_resource_asserts`) |
| Volume mounts | `kubernetes/base.py` (`Container.add_volume_mounts`) |
| Unit tests | `kubernetes/tests/test_components.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider kubernetes/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `kubernetes/tests/fixtures`, targets `minimal` and `complete` |
