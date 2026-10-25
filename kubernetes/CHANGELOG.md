# Changelog

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
