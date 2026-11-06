# Changelog

## 1.16.0

- `pod_management_policy` on a StatefulSet component renders as `podManagementPolicy`, such as the `Parallel` that the charts `qdrant` 1.20.0 and `matrix-stack` 26.11.0 set. The API rejects a change of the field on an existing StatefulSet, so one that runs with the default `OrderedReady` switches only after it is deleted with `--cascade=orphan` and applied again.
- `topology_spread_constraints` renders unchanged as the pod's `topologySpreadConstraints`, on every workload type. The generator adds no `labelSelector`, and a constraint without one spreads nothing.

Output is unchanged for inventories without these keys.

## 1.15.0

Keys for what a Helm chart renders and the generator could not, found by converting charts into inventories that are applied over the running Helm release:

- `statefulset_service_name` sets a StatefulSet's `serviceName` and renders no Service, for a governing Service rendered elsewhere, such as a chart's `<release>-headless`. It takes precedence over `service.service_name`.
- `volume_claim_name_label: false` leaves out the `name` label that the generator adds to each StatefulSet claim template. The API rejects a change of the claim templates of an existing StatefulSet, so a StatefulSet applied over a Helm release has to keep them as the chart rendered them. The label stays by default, because removing it would fail the next apply of every StatefulSet with `volume_claims` rendered by an earlier release.
- `working_dir` on a component, its `additional_containers` and `init_containers` renders as `workingDir`.
- `share_process_namespace` renders as the pod's `shareProcessNamespace`.
- A `ports` entry with `unnamed: true` renders its container port without `name`. A Service port from it keeps the key as its name and targets the container port by number.
- `ip_family_policy` and `ip_families` on a component's `service`, `additional_services` and `generators.kubernetes.services` render as `ipFamilyPolicy` and `ipFamilies`.

Output is unchanged for inventories without these keys.

## 1.14.0

- `tty` and `stdin` on a component, and on its `additional_containers` and `init_containers`, render as the container fields of the same name. A recipe can then render what a chart sets there, such as `tty: true` on the main container of the Open WebUI chart 17.5.0. `null` renders neither, so a target can drop a class's value.

Output is unchanged for inventories without `tty` and `stdin`.

## 1.13.0

- `generators.kubernetes.namespaces_in_own_directory: true` writes each Namespace of `generators.kubernetes.namespaces` to `<name>/namespace` instead of `<name>-namespace`. An Argo CD Application per namespace directory then applies the Namespace with its labels and annotations.
- An entry's `in_own_directory` overrides that default for its Namespace.

Output is unchanged without both keys.

## 1.12.2

Built for Kubernetes 1.37.2, a patch release without API changes. kubernetes-json-schema has the same files for 1.37.2 as for 1.37.1, so the shipped schemas and rendered output are unchanged.

## 1.12.1

Built for Gateway API 1.7.0. Its standard channel has the same kinds and storage versions as 1.6.3, so the generator keeps `gateway.networking.k8s.io/v1` for every kind and `v1beta1` for ReferenceGrant. HTTPRoute rules gain `retry`, and HTTPRoute and GRPCRoute reject two rules with the same `name`. The generator sets neither, so rendered output is unchanged.

In the ingress-nginx migration table, session persistence points to the experimental `XBackend`, because 1.7.0 deprecates the rule's `sessionPersistence`. What the README takes from the other Gateway API files holds at v1.7.0, so their links move to that tag, the two `httproute_types.go` anchors to the lines' new position.

## 1.12.0

- `generators.kubernetes.chainsaw.resources` adds Chainsaw status asserts for custom resources, by `api_version`, `kind`, `name`, `namespace` and the expected `status`, such as a CephCluster with `phase: Ready`. The namespace's Chainsaw Test runs them after the readiness asserts.

Output is unchanged for inventories without `chainsaw.resources`.

## 1.11.1

Built for Vertical Pod Autoscaler 1.8.1. Its VerticalPodAutoscaler CRD is unchanged from 1.8.0, so the shipped schema and rendered output are unchanged.

## 1.11.0

- `generators.kubernetes.chainsaw.workloads` adds Chainsaw readiness asserts and Test steps for workloads the generator does not render, such as those from a Helm chart, by name, `kind` and `namespace`. A Deployment or StatefulSet is ready once rolled out, read from the object's own `spec.replicas`.

Output is unchanged for inventories without `chainsaw.workloads`.

## 1.10.0

- The compile entry with `function: generate_chainsaw_asserts` also writes `<namespace>/chainsaw-test`, a Chainsaw Test per namespace that uses the namespace's StepTemplates. A project no longer keeps the list of templates in a hand-written test.
- Ships the schema of the Chainsaw 0.2.15 Test, with its CRD.

The manifests compiled with `generate_manifests` are unchanged.

## 1.9.1

`__version__` now reports the release version, which still read 1.1.1. Rendered output is unchanged.

## 1.9.0

- `webhook_configuration_name` and `validating_webhook_configuration_name` on a component name its MutatingWebhookConfiguration and ValidatingWebhookConfiguration. Without them both stay `<namespace>-<component>`. The CloudNativePG operator writes its CA only into configurations of fixed names.
- A `volume_mounts` entry takes `volume`, the volume it mounts. Its key then names only the mount, so one volume can be mounted at several paths with their own `sub_path`, as Nextcloud's chart mounts its claim six times. Without `volume` the key names the volume, as before.

Output is unchanged for inventories without the two name keys and without `volume` in `volume_mounts`.

## 1.8.0

- `generators.kubernetes.routes.<name>` renders one route attached to Gateways outside the inventory, named in `parent_refs` by `name` and optionally `namespace`, `section_name` and `port`. It takes the route keys of `gateways.<gw>.routes` and renders no Gateway. Before, a route was rendered only together with its Gateway, so a route to the cluster's shared Gateway needed a `manifests` entry. The file is `<namespace>/<name>-route`.
- A redirect rule takes `replace_full_path` or `replace_prefix_match`, which render the redirect's `path` as `ReplaceFullPath` or `ReplacePrefixMatch`, on the routes of `gateways` and of `routes`. Both together fail the compile.
- `webhook_ca_injected: true` on a component renders its webhooks with `failurePolicy: Fail` and no `caBundle`, for a server that writes the CA into its webhook configurations itself, as the CloudNativePG operator does. Without it such a webhook still fails the compile.

Output is unchanged for inventories without `routes`, without the two redirect keys and without `webhook_ca_injected`.

## 1.7.0

- `args` takes a mapping next to the list. Its values render in the mapping's order: a string as one argument, a list as several, `null` as none. A target can override or drop one argument a class sets by its key, which a list did not allow because the backends append or merge lists. A mapping value fails the compile.
- `service: {}` renders the component's Service with the API defaults. Before, an empty mapping rendered no Service and `type: ClusterIP` had to be written. `api_service` accepts it as well. A StatefulSet with `service: null` no longer fails the compile.
- README: component `labels` go on the workload, its Services, HPA and VPA, not on the pod template. Service, PodDisruptionBudget and NetworkPolicy selectors take all pod template labels. The README also states the label-value rule for names, the sorted container ports and `namespaceSelector: {}` on a webhook.

Output is unchanged for inventories without an empty `service` mapping and without an `args` mapping.

## 1.6.0

- `generators.kubernetes.services.<name>` renders a Service for pods that no component renders, such as Prometheus and Alertmanager from prometheus-operator or the static control-plane pods kube-prometheus-stack scrapes, instead of a `manifests` entry with the spec under `body`. It takes the keys and the port shape of a component's Service. `container_port` is the `targetPort` and defaults to `service_port`. `selector` is required unless the Service is `headless`. The file is `<namespace>/<name>-svc.yml`, where `manifests` wrote `<name>-service.yml`.
- A `headless` Service with a `type` other than `ClusterIP` fails the compile, instead of rendering a Service the API rejects.
- `external_name` sets `spec.externalName` and makes the Service `type: ExternalName`, on a component's `service` and in `services`. Before, `type: ExternalName` rendered a Service without `externalName`, which the API rejects; it now fails the compile unless `external_name` is set.

Output is unchanged for inventories without `services`.

## 1.5.0

- `api_service` on a component renders the APIService of an aggregated API served by the component's Service, such as metrics-server's `v1beta1.metrics.k8s.io`, instead of a `manifests` entry that repeats the Service's name, namespace and port. The port is the Service port named `https` or the only one. `group_priority_minimum` and `version_priority` default to 100. The entry needs `ca_bundle`, a cert-manager CA injection annotation or `insecure_skip_tls_verify: true`; anything else fails the compile.
- A compile entry with `function: generate_chainsaw_asserts` writes a Chainsaw StepTemplate per component that asserts its workload is ready, to use as a step in a Chainsaw test.
- Ships the schemas of APIService and of the Chainsaw 0.2.15 StepTemplate, with its CRD.

Output is unchanged for inventories without `api_service` and without that compile entry.

## 1.4.0

Defaults that remove values the inventory had to repeat:

- A Service port's `appProtocol` comes from the port name when the name says the protocol: `http`, `https`, and `h2c`, `ws`, `wss` as their `kubernetes.io/` values. **Services with ports named like this now render `appProtocol`.** An explicit `app_protocol` overrides it; an empty one leaves it out.
- A component's webhook defaults to `admissionReviewVersions: [v1]` and `sideEffects: None`.
- `role.namespace` renders a component's Role and RoleBinding in another namespace, bound to the component's ServiceAccount, for leader election in `kube-system`.
- A component's webhook without `clientConfig.url` points at the component's own Service; `clientConfig.service` takes its `name` and `namespace` unless the inventory sets them. Webhooks that set both render as before.
- `cert-manager.io/inject-ca-from-secret` and `cert-manager.io/inject-apiserver-ca` count as CA injection for a `failurePolicy: Fail` webhook, like `inject-ca-from`. cert-manager uses `inject-ca-from-secret` for its own webhook.

## 1.3.0

A container port's `app_protocol` sets `appProtocol` on its Service port, which charts such as metrics-server set and the Service API has supported since Kubernetes 1.20. Ports without it render as before.

## 1.2.0

New standalone sections for Namespaces and RBAC without a workload, so they no longer go through `manifests` with `api_version`, `kind` and `body`:

- `namespaces.<name>`: a Namespace with `labels` and `annotations`.
- `rbac.<name>`: one role with its bindings. `rules` make a ClusterRole, or a Role with `namespace`; `cluster_role` or `role` bind an existing one instead. A ClusterRole is bound by a RoleBinding in each of `namespaces` and by a ClusterRoleBinding with `cluster_wide`; subjects come from `service_accounts` (`<namespace>/<name>`), `groups`, `users` and `subjects`. Contradicting keys fail the compile.

Output file names match what `manifests` wrote for the same kinds, so moving an entry over keeps its file. Existing output is unchanged.

## 1.1.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.1.0

The Gateway `services` shorthand takes `redirect_status_code` for the HTTP to HTTPS redirect: 301 (the default, output without the key is unchanged), 302, 303, 307 or 308. Any other value fails the compile.

## 1.0.2

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.1

README: ingress-nginx to Gateway API mapping. The rendered output is unchanged.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- ServiceMonitor, PodMonitor and PrometheusRule are no longer rendered; `service_monitors`, `prometheus_rules` and `generators.kubernetes.pod_monitors` log a warning pointing to the prometheus-operator generator.
- TCPRoute, UDPRoute and TLSRoute are rendered as `gateway.networking.k8s.io/v1`, their storage version in Gateway API 1.6; the v1alpha2 and v1alpha3 versions are deprecated and not served by the standard channel.
- A Gateway listener without `allowed_routes.namespaces_from` now admits only the namespaces of the routes the generator renders for it (`Same` or a namespace `Selector`) instead of `All`. Routes rendered outside this Gateway's inventory need `allowed_routes` set.
- PersistentVolume and PersistentVolumeClaim flat keys now override `spec` instead of the reverse, with a warning on each override.
- Probes are rendered only for `healthcheck` entries with a `type` and never on init containers; empty probes made the API reject every workload.
- `replicas` is omitted when `hpa` is set.
- The `affinity` block passes through whole; the `prefer_*` shorthands append to it, and no empty `podAntiAffinity` is rendered.
- NetworkPolicy `podSelector` defaults to the pod template labels (`pod_labels` included).
- `serviceAccountName` is set for `service_account.create` as well as `enabled`; bindings use `service_account.name`.
- Pods and generated ServiceAccounts default to `automountServiceAccountToken: false`.
- Versioned ConfigMaps and Secrets: `env` and `env_from` references use the hashed name.
- Secret `data` values are base64-encoded by default (`b64_encode: false` opts out); the `__SHELLVAR_INDIRECT_` rewrite is gone.
- Key lookup for `configMapKeyRef`/`secretKeyRef` without a name also searches `string_data` and `directory` files.
- ClusterRole, ClusterRoleBinding and webhook configuration names are prefixed with the component namespace.
- Service webhooks with `failurePolicy: Fail` need a CA bundle or the cert-manager CA injection annotation (new `webhook_annotations`); webhooks default to a `namespaceSelector` excluding their own namespace.
- Generated ReferenceGrants for cross-namespace TLS secrets name those secrets; the services redirect route attaches to the existing HTTP listener.
- Standalone PersistentVolumes are written outside namespace directories.
- A Service without ports and two resources with the same output file fail the compile.
- Removed: the `istio.enabled` Ingress switch, the VPA `istio-proxy` container policy, the legacy `generators.<gateway section>` location, container `security` (now a compile error naming `security_context`) and the `NameSpace` class.
- Ships the JSON Schemas of every emitted kind except GKE BackendConfig; the kadet-hub gate validates the fixture output against them.
- The inventory schema `schema.json` for `parameters.components` is not shipped.
