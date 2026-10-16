# Changelog

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
