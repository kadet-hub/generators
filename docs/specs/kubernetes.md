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

## Container tty and stdin

The Open WebUI chart 17.5.0 sets `tty: true` on its main container, with
no value that turns it off. The generator had no key for the field, so a
recipe could not render it, and `check` of kadet-hub/recipes reported it
as a difference it does not accept. `stdin` is the field the API reference
pairs with `tty`. Both keys apply to the main container,
`additional_containers` and `init_containers`, which render through the
same container code.

- K8S-16: A container's `tty` and `stdin` MUST render as the container
  fields of the same name with the value the inventory sets. A container
  without them, or with `null`, MUST render neither.

  `null` lets a target drop a class's value. Output of an inventory
  without the keys stays byte-identical. The API server stores `false` as
  unset (`omitempty` on both fields in `k8s.io/api` `core/v1`), so
  `false` and a missing key give the same object.

  - Test: `kubernetes/tests/test_components.py::test_tty_and_stdin`, `::test_no_tty_or_stdin_renders_as_before`; fixture target `complete`; `manual:` Kapitan 0.36.3 compiles fixture targets `minimal` and `complete` without the keys to the same output as 1.13.0, with both inventory backends
  - Since: #177

## StatefulSets taken over from a Helm release

A converter that turns a Helm chart into a Kapitan inventory renders the
chart's objects with this generator, and the result is applied over the
running Helm release. The API rejects an update of a StatefulSet that
changes `serviceName` or `volumeClaimTemplates`
(`ValidateStatefulSetUpdate` in `pkg/apis/apps/validation` of Kubernetes
1.37.2). Both have to match the release, and the generator could set
neither to what a chart renders.

A chart's StatefulSet often names a headless Service of its own as
`serviceName`, such as `<release>-headless`, next to the Service that
clients use. The generator took `serviceName` from `service.service_name`,
which also names and renders the component's Service, or from the
component name.

- K8S-17: A StatefulSet component's `statefulset_service_name` MUST set
  `spec.serviceName`, ahead of `service.service_name` and the component
  name. Without it, or with `null`, `serviceName` MUST stay as before.

  The key renders no Service. The governing Service comes from `service`,
  `additional_services` or from outside the inventory. Other workload
  types ignore the key. It carries the workload prefix, as
  `deployment_progress_deadline_seconds` does, because a component-level
  `service_name` would read like the `service_name` below `service`.

  Related: K8S-2

  - Test: `kubernetes/tests/test_components.py::test_statefulset_service_name`; fixture target `complete`; `manual:` Kapitan 0.36.3 compiles fixture targets `minimal` and `complete` without the keys of K8S-17 to K8S-22 to the same output as 1.14.0, with both inventory backends
  - Since: #181

The generator adds the label `name: <claim>` to every claim template. It
came with the migration from kapicorp/generators (bb1b5c1), which has had
it since its initial commit of 2022-12-22, without a reason in the commit
or its README. No code of the generator selects claims by it. A chart's
claim template without that label could not be reproduced.

- K8S-18: A StatefulSet component with `volume_claim_name_label: false`
  MUST render its `volumeClaimTemplates` without the `name` label that
  the generator adds. Without the key, or with another value, every claim
  template MUST keep that label.

  Labels in a claim's own `metadata.labels` stay, a `name` label among
  them.

  - Test: `kubernetes/tests/test_components.py::test_volume_claim_name_label`; fixture target `complete`; `manual:` as K8S-17
  - Since: #181

DEC-5: The claim template label stays by default, and
`volume_claim_name_label: false` turns it off. Dropping it would change
the claim templates of every StatefulSet with `volume_claims` that an
earlier release rendered. The next apply of such a StatefulSet would fail
until it is deleted with `--cascade=orphan` and created again. The claims
the controller created from the templates carry the label too, and
whether a selector outside the generator, such as a backup tool's, uses
it is not known. A `null` label value per claim was considered. The
generator's `merge` replaces a `null` with the default, so it would need
handling of its own, and a takeover needs the label off on all claims of
a StatefulSet anyway. `generators.manifest.default_config` can turn it
off for a whole target.

## Container and pod fields of charts

The same converter found three fields that charts set and the generator
had no key for. Compose's `working_dir` is a gap of kadet-hub/recipes for
the same reason (RCP-37 there). `working_dir` applies to the main
container, `additional_containers` and `init_containers`, which render
through the same container code.

- K8S-19: A container's `working_dir` MUST render as `workingDir`. A
  container without it, or with `null`, MUST render none.

  - Test: `kubernetes/tests/test_components.py::test_working_dir`; fixture target `complete`; `manual:` as K8S-17
  - Since: #181

The umami recipe of kadet-hub/recipes considered `shareProcessNamespace`,
which makes the pod's pause process PID 1, and had no key for it (DEC-120
there).

- K8S-20: A component's `share_process_namespace` MUST render as the
  pod's `shareProcessNamespace` with the value the inventory sets. A
  component without it, or with `null`, MUST render none.

  The containers of the pod then see and can signal each other's
  processes. The Pod Security Standards do not restrict the field:
  pod-security-admission 1.37.2 has no check for it.

  - Test: `kubernetes/tests/test_components.py::test_share_process_namespace`; fixture target `complete`; `manual:` as K8S-17
  - Since: #181

A `ports` key named the container port, and a Service port from it
targeted that name. The API accepts a container port without a name and
checks a name only when one is set (`validateContainerPorts` in
`pkg/apis/core/validation` of Kubernetes 1.37.2).

- K8S-21: A `ports` entry with `unnamed: true` MUST render its container
  port without `name`, and a Service port from it MUST target the
  container port by its number. Without `unnamed`, the key MUST name the
  container port and be the Service port's `targetPort`, as before.

  The key still identifies the entry, orders the ports and names the
  Service port, which a Service with more than one port needs. A probe
  that names the port by its key then finds no port and fails at
  runtime, so it takes the number. An empty key renders `name: ""`, which
  the API stores as no name, but only one entry of the mapping can have
  it.

  - Test: `kubernetes/tests/test_components.py::test_unnamed_port`, `::test_named_port_renders_as_before`; fixture target `complete`; `manual:` as K8S-17
  - Since: #181

## Service IP families

- K8S-22: A Service's `ip_family_policy` and `ip_families` MUST render as
  `spec.ipFamilyPolicy` and `spec.ipFamilies`, on a component's `service`,
  its `additional_services` and `generators.kubernetes.services`. A
  Service without them, or with `null`, MUST render neither.

  A chart that pins a Service to one family, or asks for dual-stack, sets
  them, and the converter found no key for them. The values pass
  unchanged. The API accepts `SingleStack`, `PreferDualStack` and
  `RequireDualStack` and the families `IPv4` and `IPv6`, and rejects both
  fields on an ExternalName Service.

  - Test: `kubernetes/tests/test_components.py::test_service_ip_families`; fixture target `complete`; `manual:` as K8S-17
  - Since: #181

## StatefulSet start order and pod spreading

The StatefulSet of the chart `qdrant` 1.20.0 sets `podManagementPolicy:
Parallel`. The chart's values warn that under the API default
`OrderedReady` the nodes of a Qdrant cluster wait for each other's
readiness forever, so the `qdrant` recipe of kadet-hub/recipes runs one
node (DEC-231 there). element-hq's chart `matrix-stack` 26.11.0 sets
`podManagementPolicy: Parallel` on its StatefulSet
`<release>-synapse-main` and `topologySpreadConstraints` on its
Deployments, StatefulSets and Jobs. The `matrix-synapse` recipe builds on
the image instead of that chart for this reason (kadet-hub/recipes#124).
The generator had a key for neither field. Both fields, and the fields and
values of a constraint, are the same in the API reference of Kubernetes
1.35, 1.36 and 1.37.

- K8S-23: A StatefulSet component's `pod_management_policy` MUST render as
  `spec.podManagementPolicy` with the value the inventory sets. A
  StatefulSet without it, or with `null`, MUST render none.

  Other workload types ignore the key. The value passes unchanged. The API
  accepts `OrderedReady`, its default, and `Parallel` and rejects any other
  value (`ValidateStatefulSetSpec` in `pkg/apis/apps/validation` of
  Kubernetes 1.37.2). The key has no workload prefix, unlike
  `statefulset_service_name`, because no other key reads like it.

  The API rejects a change of the field on an existing StatefulSet
  (`ValidateStatefulSetUpdate` of Kubernetes 1.35.0 and 1.37.2). A
  StatefulSet that runs with the default switches to `Parallel` only after
  it is deleted with `--cascade=orphan` and created again. Setting
  `OrderedReady` on it is no change, because the API stores the default.

  Related: K8S-17

  - Test: `kubernetes/tests/test_components.py::test_pod_management_policy`, `::test_no_pod_management_or_spread_renders_as_before`; fixture target `complete`; `manual:` Kapitan 0.36.3 compiles fixture targets `minimal` and `complete` without the keys of K8S-23 and K8S-24 to the same output as 1.15.0, with both inventory backends
  - Since: #184

- K8S-24: A component's `topology_spread_constraints` MUST render
  unchanged as the pod's `topologySpreadConstraints`, on every workload
  type. A component without it, with `null` or with an empty list MUST
  render none.

  matrix-stack sets the field on Jobs as well, so the key is not limited
  to Deployments and StatefulSets. The API stores an empty list as no
  field (`omitempty` in `k8s.io/api` `core/v1`). The field is part of the
  pod template, so a change rolls the pods out.

  The generator adds no `labelSelector` to an entry. A constraint without
  one counts no pods and spreads nothing: the API reference states that a
  null selector matches no objects, and the PodTopologySpread plugin of
  Kubernetes 1.37.2 keeps it empty when `matchLabelKeys` is set. The pods
  of a component carry the label `name: <component>` for a selector.

  - Test: `kubernetes/tests/test_components.py::test_topology_spread_constraints`, `::test_no_pod_management_or_spread_renders_as_before`; fixture target `complete`; `manual:` as K8S-23
  - Since: #184

DEC-6: `topology_spread_constraints` passes through without a default
`labelSelector`. A selector on the component's `name` label where none is
set, as the `prefer_pods_in_different_*` keys add to their anti-affinity
terms, was considered. A chart's constraint carries its own selector, such
as `app.kubernetes.io/instance: <release>-synapse-main` in matrix-stack,
and an inventory converted from the chart sets it. A default would turn a
constraint that spreads nothing into one that spreads, without the
inventory saying so.

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

## Namespaces in their namespace directory

A Namespace of `generators.kubernetes.namespaces` is cluster-scoped, so it
goes to `<name>-namespace` at the top of the compile `output_path`. A
project that deploys one Argo CD Application per namespace directory has
no Application for that file. Argo CD's `CreateNamespace=true` then
creates the namespace without its labels and annotations, and Pod
Security labels never reach the cluster.

- K8S-15: An entry of `generators.kubernetes.namespaces` MUST be written
  to `<name>/namespace` when its `in_own_directory` is true, or when it
  has no `in_own_directory` and
  `generators.kubernetes.namespaces_in_own_directory` is true. Otherwise
  it MUST stay at `<name>-namespace`.

  `in_own_directory: null` counts as unset, so a target can drop a
  class's value and inherit the default.

  The Namespace is then applied by the Application of its directory,
  with the namespace's other resources. Argo CD sync options such as
  `Prune=false,Delete=false` go into the entry's `annotations`. Only this
  section moves: a Namespace from `manifests` and the cluster-scoped
  kinds of `rbac` keep their paths. Kapitan adds the extension of the
  compile entry's `output_type`, so the file is `namespace.yml` with
  `output_type: yml`.

  - Test: `kubernetes/tests/test_components.py::test_namespaces_in_own_directory`; `manual:` Kapitan 0.36.3 compiles fixture target `complete` with `namespaces_in_own_directory: true` to `payments/namespace`, and without both keys to the same output as 1.12.2
  - Since: #173

DEC-4: `generators.kubernetes.namespaces_in_own_directory` sets the
layout for the target, and an entry's `in_own_directory` overrides it.
The target-wide key is the default because where the output goes follows
from how the project deploys it. A key that existed only per entry would
bring the problem back without an error for a Namespace that lacks it.
The entry key covers the exceptions, such as a project that moves its
Namespaces one Application at a time. It drops the `namespaces_` prefix
because it already sits below `namespaces`.

## Implementation inventory

| Item | Value |
|---|---|
| Component Service | `kubernetes/generators.py` (`_build_service_bundle`) |
| Service IP families, Service port of an unnamed container port | `kubernetes/networking.py` (`Service.body`, `Service._build_service_ports`) |
| StatefulSet `serviceName`, `podManagementPolicy` | `kubernetes/workloads.py` (`StatefulSet.body`) |
| Claim template name label | `kubernetes/base.py` (`WorkloadCommon.add_volume_claims`) |
| Pod `shareProcessNamespace`, `topologySpreadConstraints` | `kubernetes/base.py` (`Workload.body`) |
| Container args, tty, stdin, workingDir, unnamed ports | `kubernetes/base.py` (`Container.body`) |
| Routes, path redirects | `kubernetes/generators.py` (`_generate_routes`), `kubernetes/networking.py` (`GatewayRoute`) |
| Webhook CA | `kubernetes/webhooks.py` (`_webhooks`) |
| Webhook configuration names | `kubernetes/webhooks.py` (`MutatingWebhookConfiguration`, `ValidatingWebhookConfiguration`) |
| Chainsaw Test, external workloads | `kubernetes/generators.py` (`generate_chainsaw_asserts`, `_EXTERNAL_WORKLOADS`, `_resource_asserts`) |
| Volume mounts | `kubernetes/base.py` (`Container.add_volume_mounts`) |
| Namespace output path | `kubernetes/generators.py` (`generate_resource_manifests`) |
| Unit tests | `kubernetes/tests/test_components.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider kubernetes/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `kubernetes/tests/fixtures`, targets `minimal` and `complete` |
