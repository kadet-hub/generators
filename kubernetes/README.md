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

The Gateway `services` shorthand turns `hostname`, `namespace`, `tls_secret`, `backend` and optional `cluster_issuer`/`issuer` into an HTTPS listener, an HTTP to HTTPS redirect route (not for `type: grpc`) and the backend route. A listener without `allowed_routes.namespaces_from` admits the namespaces of the routes the generator renders for it: `Same` when they all live in the Gateway's namespace, otherwise a `Selector` on `kubernetes.io/metadata.name` listing them. The upstream default is `Same` ([AllowedRoutes](https://gateway-api.sigs.k8s.io/reference/spec/#allowedroutes)); `All` would let any namespace attach routes to the listener's hostnames. Routes rendered elsewhere need `allowed_routes` set explicitly.

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
