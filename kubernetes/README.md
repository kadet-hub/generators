# Kubernetes Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/kubernetes/)): pin a released version by digest from its catalog page.

Kapitan kadet generator for plain Kubernetes resources. One component block under `parameters.components` becomes a workload (Deployment, StatefulSet, DaemonSet, Job or CronJob) plus the resources derived from it: Services selecting its pods, ConfigMaps and Secrets mounted into it, a ServiceAccount with Role or ClusterRole bindings, HorizontalPodAutoscaler, PodDisruptionBudget, VerticalPodAutoscaler, NetworkPolicies, PersistentVolumeClaims and admission webhooks. Next to components it renders Ingresses (with GKE ManagedCertificates), Gateway API resources, standalone ConfigMaps, Secrets, ServiceAccounts and volumes, cluster and namespace policy kinds, and any other kind through a passthrough.

Built for Kubernetes 1.37.1, Gateway API 1.6.3, Vertical Pod Autoscaler 1.8.0 and GKE Managed Certificates 1.2.12.

ServiceMonitor, PodMonitor and PrometheusRule belong in the [prometheus-operator generator](https://kadet-hub.org/generators/prometheus-operator/) (`generators.prometheus_operator`); the component keys `service_monitors` and `prometheus_rules` and the section `generators.kubernetes.pod_monitors` are ignored with a warning naming it.

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kubernetes@sha256:<digest>
        output_path: lib/kubernetes
    compile:
      - output_path: manifests/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/kubernetes

  namespace: shop

  generators:
    manifest:
      default_config:           # merged into every component; component keys win
        recommended_labels: true
        security_profile: restricted
      resource_defaults:
        deployment:             # merged into components of this type
          revision_history_limit: 5

  components:
    web:
      image: registry.example.com/shop/web:1.4.2
      replicas: 2
      ports:
        http:
          container_port: 8080
          service_port: 80
      healthcheck:
        readiness:
          type: http
          port: http
          path: /ready
      resources:
        requests: {cpu: 100m, memory: 128Mi}
        limits: {memory: 256Mi}
      env:
        LOG_LEVEL: info
        CHECKOUT_URL:
          configMapKeyRef:
            key: checkout_url   # name resolved to the component's ConfigMap
      config_maps:
        config:
          mount: /etc/web
          data:
            checkout_url:
              value: https://shop.example.com/checkout
      service:
        type: ClusterIP
      hpa:
        min_replicas: 2
        max_replicas: 6
      pdb_min_available: 1
```

This renders `shop/web-deploy.yml` (Deployment with the ConfigMap volume, mount and env reference wired up, restricted security context), `shop/web-cm.yml`, `shop/web-svc.yml` (selector and ports from the container ports with a `service_port`) and `shop/web-scaling.yml` (HPA targeting the Deployment, PDB selecting its pods). `tests/fixtures/inventory/targets/complete.yml` uses every section below.

## Inputs

| Key | Renders |
|---|---|
| `components.<name>` | the component bundle, see below |
| `generators.manifest.default_config`, `.resource_defaults.<type>`, `applications.<app>.component_defaults` | defaults merged into components; `default_config.globals.config_maps` / `.secrets` add labels and annotations to every component ConfigMap or Secret |
| `ingresses.<name>` | Ingress (`networking.k8s.io/v1`); `managed_certificate` adds a GKE ManagedCertificate |
| `generators.kubernetes.gateway_classes`, `gateways`, `backend_tls_policies`, `reference_grants` | Gateway API GatewayClass, Gateway with HTTPRoute, GRPCRoute, TCPRoute, TLSRoute and UDPRoute, BackendTLSPolicy, ReferenceGrant |
| `generators.kubernetes.configs`, `secrets`, `service_accounts`, `persistent_volumes`, `persistent_volume_claims` | standalone ConfigMap, Secret, ServiceAccount, PersistentVolume, PersistentVolumeClaim |
| `generators.kubernetes.storage_classes`, `ingress_classes`, `runtime_classes`, `priority_classes`, `limit_ranges`, `resource_quotas` | the matching kind; flat keys are the snake_case spec fields, `default: true` sets the default-class annotation on StorageClass and IngressClass |
| `generators.kubernetes.manifests.<name>` | any kind: `api_version`, `kind`, `name`, `namespace`, `labels`, `annotations` and the remaining fields under `body` |
| `generators.kubernetes.namespace`, `namespace` | default namespace (Gateway API resources check `generators.kubernetes.namespace` first), else `default` |

Component keys, by what they produce:

| Area | Keys |
|---|---|
| workload | `type` (`deployment` default, `statefulset`, `daemonset`, `job`), `schedule` (makes a Job a CronJob), `replicas`, `update_strategy`, `revision_history_limit`, `min_ready_seconds`, `deployment_progress_deadline_seconds`, `backoff_limit`, `completions`, `parallelism`, `active_deadline_seconds`, `ttl_seconds_after_finished`, `concurrency_policy`, `suspend`, `starting_deadline_seconds`, `labels`, `annotations`, `pod_labels`, `pod_annotations`, `recommended_labels` |
| containers | `image`, `pull_policy`, `command`, `args`, `env`, `env_from`, `ports`, `healthcheck` (`startup`, `liveness`, `readiness`; type `http`, `tcp`, `command`, `grpc`), `resources`, `lifecycle`, `security_context`, `volume_mounts`, `additional_containers`, `init_containers` |
| pod | `volumes`, `volume_claims` (StatefulSet templates), `service_account`, `automount_service_account_token`, `enable_service_links`, `image_pull_secrets`, `dns_policy`, `grace_period`, `restart_policy`, `node_selector`, `tolerations`, `affinity`, `prefer_pods_in_different_nodes`, `prefer_pods_in_different_zones`, `prefer_pods_in_node_with_expression`, `priority_class_name`, `resource_claims`, `host_network`, `host_pid`, `host_ipc` |
| security | `security_profile` (`baseline`, `restricted`), `read_only_root_filesystem`, `workload_security_context`, `network_policies` |
| config | `config_maps`, `secrets` (`data`, `string_data` from `value`, `template` or `file`; `items`, `mount`, `versioned`) |
| services | `service`, `additional_services` |
| RBAC | `service_account.create`, `role`, `cluster_role` (rules and an optional `binding`) |
| scaling | `hpa`, `pdb_min_available`, `auto_pdb`, `vpa` (update mode) |
| other | `persistent_volumes`, `persistent_volume_claims`, `webhooks` (Mutating), `validating_webhooks`, `webhook_annotations`, `backend_config` (GKE BackendConfig) |

`labels` go on the workload and its pod template; `pod_labels` only on the pod template. Selectors use the `name` label only. `service_account.create` renders a ServiceAccount, `service_account.enabled` only sets `serviceAccountName`; either sets it, to `service_account.name` or the component name, and Role and ClusterRole bindings bind that name.

Probes are rendered only for the `healthcheck` entries that set a `type`, never on init containers. With `hpa` set, the workload has no `replicas`, so applying the manifest does not reset the HPA's count ([HPA docs](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#migrating-deployments-and-statefulsets-to-horizontal-autoscaling)). A Job's pod template is immutable: changing the image or a versioned ConfigMap of an existing Job needs the Job deleted first, or `ttl_seconds_after_finished`. `backoff_limit` defaults to `1`, as documented before the migration.

Secret `data` values are base64-encoded unless the entry sets `b64_encode: false`; `string_data` stays plain. A Kapitan ref (`?{...}`) passes through unchanged, so a ref used in `data` must hold a base64 value. With `versioned: true` the ConfigMap or Secret name gets a content hash, and the volumes, `env` and `env_from` references of the component follow it.

A Service needs at least one container port with a `service_port`, except `headless` and `ExternalName` Services. Two resources that map to the same output file fail the compile.

For PersistentVolumes and PersistentVolumeClaims, `spec` is merged over the generator defaults first, then the flat keys are applied; a flat key that overrides a `spec` value logs a warning.

The Gateway `services` shorthand turns `hostname`, `namespace`, `tls_secret`, `backend` and optional `cluster_issuer`/`issuer` into an HTTPS listener, an HTTP to HTTPS redirect route (not for `type: grpc`) and the backend route. `redirect_status_code` sets the redirect's `statusCode`, default 301. 301 and 302 are Core support; 303, 307 and 308 are Extended and need an implementation that supports them ([statusCode][gw-status]). Any other value fails the compile. A listener without `allowed_routes.namespaces_from` admits the namespaces of the routes the generator renders for it: `Same` when they all live in the Gateway's namespace, otherwise a `Selector` on `kubernetes.io/metadata.name` listing them. The upstream default is `Same` ([AllowedRoutes](https://gateway-api.sigs.k8s.io/reference/spec/#allowedroutes)); `All` would let any namespace attach routes to the listener's hostnames. Routes rendered elsewhere need `allowed_routes` set explicitly.

## Security defaults

The generator sets no `privileged`, host namespace, `hostPath` or added capability default, and only sets a Service `type` that the inventory names, so nothing is exposed through `LoadBalancer` or `NodePort` unless configured. `security_profile: restricted` fills the [Pod Security Standards restricted](https://kubernetes.io/docs/concepts/security/pod-security-standards/#restricted) fields that are unset: pod `runAsNonRoot: true` and `seccompProfile.type: RuntimeDefault`, and on every container `allowPrivilegeEscalation: false` and `capabilities.drop: [ALL]`. A rendered value the chosen profile forbids is kept and logged as a warning naming the field. The profile is opt-in, per component or through `default_config`, because `runAsNonRoot` stops images that run as root.

Pods and generated ServiceAccounts get `automountServiceAccountToken: false` ([Opt out of API credential automounting](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#opt-out-of-api-credential-automounting)). A component that calls the API sets `automount_service_account_token: true`; a standalone ServiceAccount takes `service_account.automount_service_account_token`.

A service webhook with `failurePolicy: Fail` (the API default) needs `clientConfig.caBundle` or `webhook_annotations` with `cert-manager.io/inject-ca-from`, else the compile fails. Each webhook without a `namespaceSelector` excludes the namespace of its own Service, so the webhook cannot block its own pods. ClusterRoles, ClusterRoleBindings and webhook configurations are named `<namespace>-<component>`.

The generator also warns about images without a pinned tag, containers without CPU and memory requests or a memory limit, ports without a readiness probe and PodDisruptionBudgets that allow no eviction.

## Output files

Each resource set goes to `<namespace>/<name>-<suffix>.yml` below the compile `output_path`; cluster-scoped kinds have no namespace directory. Component bundles without content are not written.

| Source | Suffix |
|---|---|
| component workload with its webhooks and BackendConfig | `deploy`, `sts`, `ds`, `job`, `cj` |
| component `config_maps` / `secrets` | `cm` / `secret` |
| component `service`, `additional_services` | `svc` |
| component ServiceAccount, Role, ClusterRole and bindings | `rbac` |
| component VPA, PDB, HPA | `scaling` |
| component NetworkPolicies | `security` |
| component `persistent_volumes` / `persistent_volume_claims` | `vol` |
| `ingresses` | `ingress`, `managed-certificate` |
| `gateways` | `gateway`; routes `gw-routes` in the route's namespace; generated ReferenceGrants `refgrant` in the target namespace |
| `gateway_classes` | `<name>-gatewayclass` |
| `reference_grants`, `backend_tls_policies` | `refgrant`, `btlspolicy` |
| standalone `secrets`, `configs`, `service_accounts`, `persistent_volume_claims` | `secret`, `config`, `sa`, `pvc` |
| standalone `persistent_volumes`, PVs from `create_pv` | `<name>-pv`, no namespace directory |
| `storage_classes`, `ingress_classes`, `runtime_classes`, `priority_classes` | `<name>-sc`, `-ingressclass`, `-runtimeclass`, `-pc` |
| `limit_ranges`, `resource_quotas` | `limits`, `quota` |
| `manifests` | `<kind lowercased>`; no namespace directory without `namespace` |

## API versions and schemas

Built-in kinds use the GA versions served by Kubernetes 1.37: `v1`, `apps/v1`, `batch/v1`, `autoscaling/v2`, `policy/v1`, `networking.k8s.io/v1`, `rbac.authorization.k8s.io/v1`, `storage.k8s.io/v1`, `node.k8s.io/v1`, `scheduling.k8s.io/v1`, `admissionregistration.k8s.io/v1`. Gateway API kinds use their storage versions in the 1.6 standard channel, `gateway.networking.k8s.io/v1` for every kind except ReferenceGrant (`v1beta1`); a route's `api_version` overrides it. VerticalPodAutoscaler is `autoscaling.k8s.io/v1`, ManagedCertificate `networking.gke.io/v1`, BackendConfig `cloud.google.com/v1`.

`schemas/` holds the JSON Schemas of these kinds: built-in kinds from [kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) v1.37.1-standalone-strict, CRD kinds from the upstream CRDs at the versions above, closed against unknown fields. BackendConfig is not schema-checked, because GKE publishes no BackendConfig CRD file; kinds rendered through `manifests` are checked only where `schemas/` has their schema.

## ingress-nginx annotations

For moving an Ingress from `ingresses.<name>` to `generators.kubernetes.gateways`, the table maps common [ingress-nginx annotations][inx] (controller v1.15.1, prefix `nginx.ingress.kubernetes.io/`) to the Gateway API 1.6.3 standard channel this generator renders, and to the generator keys below `generators.kubernetes` that render the field. Ingress and Gateway can run side by side during the move: the Ingress keeps its `annotations`, and the Gateway gets its own address ([ingress-nginx migration guide][gw-inx]). [ingress2gateway][i2g] v1.2.0 converts most of these annotations and warns about the rest.

| Annotation | Gateway API 1.6.3 standard | Generator |
|---|---|---|
| [`ssl-redirect`, `force-ssl-redirect`][inx-ssl] | [`RequestRedirect`][gw-redirect] filter with `scheme: https` on a route attached to the HTTP listener | `gateways.<gw>.services.<svc>` (301 or `redirect_status_code`, `http_redirect: false` drops it), or a `gateways.<gw>.routes` rule with `redirect.scheme` and `redirect.status_code` |
| [`rewrite-target`][inx-rewrite] | [`URLRewrite`][gw-redirect] filter, `path.type` `ReplacePrefixMatch` or `ReplaceFullPath` | none |
| [`backend-protocol`][inx-proto] | `GRPC`: [GRPCRoute][gw-grpc]; `HTTPS`: [BackendTLSPolicy][gw-btls]; `GRPCS`: both; `FCGI`: none | `type: grpc` on a `services` entry or route; `backend_tls_policies` |
| [`canary`, `canary-weight`][inx-canary] | two `backendRefs` with [`weight`][gw-split] in one rule; `canary-by-header` is a [`headers` match][gw-routing] | none |
| [`enable-cors`, `cors-*`][inx-cors] | [`CORS`][gw-cors] filter | none |
| [`use-regex`][inx-regex] | path match `type: RegularExpression` | `gateways.<gw>.routes.<route>.rules.<rule>.matches.<match>.type: RegularExpression` |
| [`proxy-body-size`][inx-body] | none | none |
| [`whitelist-source-range`][inx-ip] | none | none |
| [`auth-url`][inx-auth] | none; experimental channel: `ExternalAuth` filter ([GEP-1494][gep-1494]) | none |
| [`affinity`][inx-affinity], [`session-cookie-*`][inx-cookie] | none; experimental channel: rule `sessionPersistence` ([GEP-1619][gep-1619]) | none |
| [`server-snippet`][inx-server-snippet], [`configuration-snippet`][inx-snippet] | none | none |

A Gateway API field with "none" in the generator column is one the route keys cannot render: a route rule renders one backend, path (or gRPC method) matches and no filter other than `redirect`. That route goes in `generators.kubernetes.manifests` as `kind: HTTPRoute` with its spec under `body`, as do the implementation policies below. Experimental fields also need the experimental channel CRDs in the cluster.

ingress-nginx redirects to HTTPS with 308 ([ssl-redirect][inx-ssl]). The `services` shorthand defaults to 301, which does not guarantee that the client keeps the request method; `redirect_status_code: 308` on the service or `status_code: 308` on a route rule behaves like ingress-nginx ([redirects][gw-redirect]). The redirect route does not depend on TLS on the Gateway, so `ssl-redirect` and `force-ssl-redirect` map to the same route, and `ssl-redirect: "false"` means no redirect route. ingress2gateway adds the 308 redirect only for hosts with TLS on the Ingress and does not convert `force-ssl-redirect`.

`ReplacePrefixMatch` with an empty `replacePrefixMatch` strips the matched prefix: `/foo/bar` with prefix `/foo` becomes `/bar` ([API spec][gw-prefix]). That covers the common `path: /something(/|$)(.*)` with `rewrite-target: /$2` ([rewrite example][inx-rewrite-example]). Other capture group references have no equivalent; ingress2gateway converts `rewrite-target` to `ReplaceFullPath` and flags them. Path rewrites are Extended support.

BackendTLSPolicy (standard since v1.4.0) requires `validation.hostname` and a CA from `caCertificateRefs` or `wellKnownCACertificates`, so it always verifies the backend certificate ([BackendTLSPolicy][gw-btls]). `backend-protocol: HTTPS` alone does not, because `proxy-ssl-verify` defaults to `off` ([backend certificate authentication][inx-proxy-ssl]); ingress2gateway emits a BackendTLSPolicy only when `proxy-ssl-verify` and `proxy-ssl-server-name` are `on` and `proxy-ssl-secret` and `proxy-ssl-name` name the CA Secret and the hostname ([backend_tls.go][i2g-btls]).

Weights are proportional, not percentages: `canary-weight: "10"` with the default `canary-weight-total` of 100 is weight 90 on the main backend and 10 on the canary ([traffic splitting][gw-split]). ingress2gateway converts `canary-weight`, `canary-by-header` and `canary-by-header-value`, and warns on `canary-by-cookie` and `canary-by-header-pattern`.

The CORS filter is standard since v1.5.0 with Extended support ([CORS][gw-cors]) and has none of the ingress-nginx defaults. ingress-nginx allows origin `*`, allows credentials and caches preflights for 1728000 seconds ([CORS][inx-cors]); the filter has no default origins, methods or headers, sends `Access-Control-Allow-Credentials` only with `allowCredentials: true` and defaults `maxAge` to 5 seconds. Set `allowOrigins`, `allowMethods`, `allowHeaders`, `exposeHeaders`, `allowCredentials` and `maxAge` explicitly.

`RegularExpression` path matches have Implementation-specific support, so the regex dialect and case sensitivity are the implementation's ([extension points][gw-ext]). ingress-nginx matches case-insensitively, on every path of the host once one of its Ingresses sets `use-regex` ([use-regex][inx-regex]); ingress2gateway writes `(?i)<path>.*` ([regex.go][i2g-regex]).

Body size, IP ranges, external auth, session affinity and snippets need an implementation extension: a policy that targets the Gateway or route, or an `ExtensionRef` filter in the route ([extension points][gw-ext]). Examples from Envoy Gateway 1.9 and NGINX Gateway Fabric:

- `proxy-body-size`: Envoy Gateway BackendTrafficPolicy `requestBuffer.limit` ([request buffering][eg-buffer]), which ingress2gateway's envoy-gateway emitter renders ([buffer.go][i2g-eg-buffer]). Above the limit it answers 413 like ingress-nginx, but it buffers the whole request, so streaming gRPC and WebSocket routes can hang.
- `whitelist-source-range`, `denylist-source-range`: Envoy Gateway SecurityPolicy `authorization` rules with `principal.clientCIDRs` ([IP allowlist][eg-ip]), also rendered by the envoy-gateway emitter ([iprange.go][i2g-eg-ip]).
- `auth-url`: Envoy Gateway SecurityPolicy `extAuth` ([external authorization][eg-extauth]). ingress2gateway does not convert it.
- `affinity: cookie`: Envoy Gateway implements the experimental `sessionPersistence` ([session persistence][eg-session]); `session-cookie-name` becomes `sessionName`. ingress2gateway converts affinity only with its gce emitter ([gce.go][i2g-gce]).
- `server-snippet`, `configuration-snippet`: NGINX Gateway Fabric SnippetsFilter, NGINX syntax referenced through `extensionRef` ([snippets][ngf-snippets]), or Envoy Gateway EnvoyPatchPolicy, JSON patches to the generated Envoy configuration ([Envoy patch policy][eg-patch]). Both are disabled by default. ingress2gateway does not convert snippets.

[inx]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md
[inx-ssl]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#server-side-https-enforcement-through-redirect
[inx-rewrite]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#rewrite
[inx-rewrite-example]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/examples/rewrite/README.md
[inx-proto]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#backend-protocol
[inx-proxy-ssl]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#backend-certificate-authentication
[inx-canary]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#canary
[inx-cors]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#enable-cors
[inx-regex]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#use-regex
[inx-body]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#custom-max-body-size
[inx-ip]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#whitelist-source-range
[inx-auth]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#external-authentication
[inx-affinity]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#session-affinity
[inx-cookie]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#cookie-affinity
[inx-server-snippet]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#server-snippet
[inx-snippet]: https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/docs/user-guide/nginx-configuration/annotations.md#configuration-snippet
[gw-inx]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/getting-started/migrating-from-ingress-nginx.md
[gw-ext]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/getting-started/migrating-from-ingress.md#approach-to-extensibility
[gw-redirect]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/user-guides/http-redirect-rewrite.md
[gw-prefix]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/apis/v1/httproute_types.go#L1188-L1200
[gw-status]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/apis/v1/httproute_types.go#L1276-L1297
[gw-grpc]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/user-guides/grpc-routing.md
[gw-btls]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/reference/api-types/policy/backendtlspolicy.md
[gw-split]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/user-guides/traffic-splitting.md
[gw-routing]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/user-guides/http-routing.md
[gw-cors]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/site/content/en/guides/user-guides/http-cors.md
[gep-1494]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/geps/gep-1494/index.md
[gep-1619]: https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/geps/gep-1619/index.md
[i2g]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/providers/ingressnginx/README.md
[i2g-btls]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/providers/ingressnginx/backend_tls.go
[i2g-regex]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/providers/ingressnginx/regex.go
[i2g-eg-buffer]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/emitters/envoygateway/buffer.go
[i2g-eg-ip]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/emitters/envoygateway/iprange.go
[i2g-gce]: https://github.com/kubernetes-sigs/ingress2gateway/blob/v1.2.0/pkg/i2gw/emitters/gce/gce.go
[eg-buffer]: https://gateway.envoyproxy.io/v1.9/tasks/traffic/request-buffering/
[eg-ip]: https://gateway.envoyproxy.io/v1.9/tasks/security/restrict-ip-access/
[eg-extauth]: https://gateway.envoyproxy.io/v1.9/tasks/security/ext-auth/
[eg-session]: https://gateway.envoyproxy.io/v1.9/tasks/traffic/session-persistence/
[eg-patch]: https://gateway.envoyproxy.io/v1.9/tasks/extensibility/envoy-patch-policy/
[ngf-snippets]: https://docs.nginx.com/nginx-gateway-fabric/traffic-management/snippets/
