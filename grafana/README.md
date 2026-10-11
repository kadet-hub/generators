# Grafana Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/grafana/) page.

Built for Grafana Operator 5.25.0 (`grafana.integreatly.org/v1beta1`, the only served and storage version of every kind, not deprecated). The bundled JSON Schemas come from the operator's CRDs at that release, which are Apache-2.0; Grafana itself is not used.

Kapitan kadet generator for the [Grafana Operator](https://grafana.github.io/grafana-operator/) custom resources. It emits only these custom resources; dashboards and datasources are not rendered as ConfigMaps.

- **Grafana**: a Grafana instance, with persistence and Ingress shorthands
- **GrafanaDashboard**, **GrafanaLibraryPanel**, **GrafanaFolder**, **GrafanaDatasource**: content imported into matching instances
- **GrafanaAlertRuleGroup**, **GrafanaContactPoint**, **GrafanaNotificationPolicy**, **GrafanaNotificationPolicyRoute**, **GrafanaNotificationTemplate**, **GrafanaMuteTiming**: Grafana-managed alerting
- **GrafanaServiceAccount**: a Grafana service account with tokens

Secrets that `valuesFrom` or the Ingress TLS reference come from External Secrets, cert-manager or the `kubernetes` generator.

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/grafana@sha256:<digest>
        output_path: lib/grafana
    compile:
      - output_path: manifests/grafana/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/grafana
```

`input_params: {function: generate_manifests}` on the compile entry renders only the instances, as in kapitan-generators.

## Inventory contract

All keys live under `parameters.generators.grafana`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `instance_selector` | | Default `instanceSelector` of every kind that has one, see below. |
| `instances.<name>` | Grafana | `<namespace>/<name>-grafana-instance` |
| `dashboards.<name>` | GrafanaDashboard | `<namespace>/<name>-dashboard` |
| `library_panels.<name>` | GrafanaLibraryPanel | `<namespace>/<name>-librarypanel` |
| `folders.<name>` | GrafanaFolder | `<namespace>/<name>-folder` |
| `datasources.<name>` | GrafanaDatasource | `<namespace>/<name>-datasource` |
| `alert_rule_groups.<name>` | GrafanaAlertRuleGroup | `<namespace>/<name>-alertrulegroup` |
| `contact_points.<name>` | GrafanaContactPoint | `<namespace>/<name>-contactpoint` |
| `notification_policies.<name>` | GrafanaNotificationPolicy | `<namespace>/<name>-notificationpolicy` |
| `notification_policy_routes.<name>` | GrafanaNotificationPolicyRoute | `<namespace>/<name>-notificationpolicyroute` |
| `notification_templates.<name>` | GrafanaNotificationTemplate | `<namespace>/<name>-notificationtemplate` |
| `mute_timings.<name>` | GrafanaMuteTiming | `<namespace>/<name>-mutetiming` |
| `service_accounts.<name>` | GrafanaServiceAccount | `<namespace>/<name>-serviceaccount` |

Every entry accepts `namespace`, `labels`, `annotations` and `spec`, which passes through unchanged. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands. A flat key that overrides a `spec` value logs a warning; on Grafana instances the flat keys merge deeply into `spec`, on the other kinds a flat key replaces the whole `spec` field.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged:

| Kind | Flat keys |
|---|---|
| all kinds except NotificationPolicyRoute | `resync_period`, `suspend`, `allow_cross_namespace_import` |
| all kinds except NotificationPolicyRoute and ServiceAccount | `instance_selector` |
| Dashboard, LibraryPanel | `json`, `gzip_json`, `url`, `configmap_ref`, `grafana_com`, `jsonnet`, `jsonnet_lib`, `folder_ref`, `folder_uid`, `uid`, `datasources`, `plugins`, `envs`, `env_from`, `content_cache_duration`, `url_authorization`; Dashboard also `folder` |
| Datasource | `datasource` (required), `values_from`, `plugins`, `uid` |
| Folder | `title`, `parent_folder_ref`, `parent_folder_uid`, `permissions`, `uid` |
| AlertRuleGroup | `interval` (required), `rules` (required), `group_name` (`spec.name`), `folder_ref`, `folder_uid`, `editable` |
| ContactPoint | `receivers`, `point_name` (`spec.name`), `editable`; `type`, `settings`, `uid`, `values_from`, `disable_resolve_message` become one `receivers` entry, see below |
| NotificationPolicy | `route` (required), `editable` |
| NotificationPolicyRoute | `receiver`, `route_selector`, `matchers`, `object_matchers`, `match_re`, `group_by`, `group_wait`, `group_interval`, `repeat_interval`, `continue`, `mute_time_intervals`, `active_time_intervals`, `routes`, `provenance` |
| NotificationTemplate | `name`, `template`, `editable` |
| MuteTiming | `name`, `time_intervals`, `editable` |
| ServiceAccount | `instance_name`, `role` (`Admin`, `Editor` or `Viewer`), `name`, `tokens`, `is_disabled` |

The ServiceAccount CRD has no `allowCrossNamespaceImport`, so `allow_cross_namespace_import` on a service account fails QA-7.

### Defaults and shorthands

| Input | Result |
|---|---|
| `instance_selector: {<label>: <value>}`, per entry or generator-wide | `instanceSelector: {matchLabels: {<label>: <value>}}` |
| entry key of a Folder | `spec.title` |
| entry key of a MuteTiming or NotificationTemplate | `spec.name` |
| ContactPoint `type`, `settings`, `uid`, `values_from`, `disable_resolve_message` | one entry in `spec.receivers` with `type`, `settings`, `uid`, `valuesFrom`, `disableResolveMessage` |
| matcher `type: "="`, `"!="`, `"=~"`, `"!~"` (or `equal`, `not_equal`, `regex`, `not_regex`) on a NotificationPolicyRoute | `isEqual` and `isRegex` |

`instanceSelector` is [required by every content and alerting CRD](https://github.com/grafana/grafana-operator/tree/v5.25.0/config/crd/bases) and is a Kubernetes LabelSelector, so a bare label map is rejected. A selector that contains `matchLabels` or `matchExpressions` passes through. An entry without a selector, per entry, in `spec` or generator-wide, fails the compile. The generator never defaults `instanceSelector: {}`, which matches every instance, and never sets `allowCrossNamespaceImport`, which lets instances in other namespaces import the resource; both need to be in the inventory.

The top-level ContactPoint fields `type`, `settings`, `uid`, `valuesFrom` and `disableResolveMessage` are [deprecated in favour of `spec.receivers[]`](https://github.com/grafana/grafana-operator/blob/v5.25.0/api/v1beta1/grafanacontactpoint_types.go), whose entries carry the same fields, so the generator emits them as one receiver. Flat `receivers` wins over these keys and logs a warning. The same fields in `spec` pass through unchanged. A receiver without `settings` fails QA-7; the API type requires it.

MuteTiming and NotificationTemplate [require `spec.name`](https://github.com/grafana/grafana-operator/tree/v5.25.0/config/crd/bases), the name Grafana shows and other resources reference, for example in `mute_time_intervals`.

The generator leaves operator defaults out: AlertRuleGroup `spec.name` and ContactPoint `spec.name` default to the resource name in the operator. ServiceAccount `role` and `instance_name` have no default; an entry without them fails QA-7, since a role is an access decision.

### Grafana instances

| Key | Result |
|---|---|
| `image` | image of the `grafana` container; without it the operator's default applies, `docker.io/grafana/grafana:13.1.3` at 5.25.0, or `spec.version` |
| `config` | `spec.config`, the `grafana.ini` sections |
| `persistence.enabled`, `.size` (default `1Gi`), `.storageclass` | a ReadWriteOnce `spec.persistentVolumeClaim` mounted as the data volume |
| `ingress.enabled`, `.hostname` (required), `.ingress_class` (default `nginx`), `.annotations`, `.labels` | `spec.ingress` with TLS Secret `<name>-grafana-tls-secret` |

The generator sets no container `securityContext` or `readinessProbe`, so the operator's apply: user and group 10001, read-only root filesystem, all capabilities dropped, and a readiness probe with `failureThreshold: 1` ([deployment_reconciler.go](https://github.com/grafana/grafana-operator/blob/v5.25.0/controllers/reconcilers/grafana/deployment_reconciler.go)). `spec.deployment` changes them; containers and volumes merge by name, as the operator merges them into its Deployment.

Persistence follows the [upstream example](https://github.com/grafana/grafana-operator/blob/v5.25.0/examples/grafana/persistent_volume/resources.yaml): the operator names the claim `<name>-pvc` ([resources.go](https://github.com/grafana/grafana-operator/blob/v5.25.0/controllers/resources/resources.go)) and mounts the volume `grafana-data` at `/var/lib/grafana` ([deployment_reconciler.go](https://github.com/grafana/grafana-operator/blob/v5.25.0/controllers/reconcilers/grafana/deployment_reconciler.go)), so the generator replaces that volume's `emptyDir` with the claim. It also sets the Deployment `strategy: Recreate`, because a rolling update cannot start the new pod while the old one holds the ReadWriteOnce volume, and a default `fsGroup: 10001`, the operator's group, so that Grafana can write to it; `spec.deployment` overrides the `fsGroup`. Without `storageclass` the claim uses the cluster's default StorageClass.

The Ingress backend is the operator's Service `<name>-service` on `server.http_port` from `config` or `spec.config`, default 3000 ([service_reconciler.go](https://github.com/grafana/grafana-operator/blob/v5.25.0/controllers/reconcilers/grafana/service_reconciler.go)). The operator does not create the TLS Secret; an annotation like `cert-manager.io/cluster-issuer` does.

The generator sets no admin credentials and no anonymous access. Without `security.admin_user` and `security.admin_password` in `config`, the operator creates `<name>-admin-credentials` with user `admin` and a random password ([admin_secret_reconciler.go](https://github.com/grafana/grafana-operator/blob/v5.25.0/controllers/reconcilers/grafana/admin_secret_reconciler.go)). Own credentials belong in a Secret, read through `spec.deployment` env with `spec.disableDefaultAdminSecret: true` as in the [upstream example](https://github.com/grafana/grafana-operator/blob/v5.25.0/examples/grafana/credential_secret/resources.yaml), not in `config`, which stores them in the CR in plain text.

## Example

```yaml
parameters:
  generators:
    grafana:
      namespace: monitoring
      instance_selector:
        dashboards: grafana
      instances:
        main:
          labels:
            dashboards: grafana
          persistence:
            enabled: true
            size: 10Gi
          ingress:
            enabled: true
            hostname: grafana.example.com
            annotations:
              cert-manager.io/cluster-issuer: letsencrypt
      datasources:
        prometheus:
          uid: prometheus
          datasource:
            name: Prometheus
            type: prometheus
            access: proxy
            url: http://prometheus-operated.monitoring.svc:9090
            isDefault: true
      folders:
        infrastructure:
          title: Infrastructure
      dashboards:
        node-exporter-full:
          folder_ref: infrastructure
          grafana_com:
            id: 1860
      contact_points:
        oncall-slack:
          receivers:
            - type: slack
              settings:
                recipient: "#oncall"
              valuesFrom:
                - targetPath: url
                  valueFrom:
                    secretKeyRef:
                      name: grafana-slack-webhook
                      key: url
      notification_policies:
        root:
          route:
            receiver: oncall-slack
            group_by: [grafana_folder, alertname]
      mute_timings:
        maintenance:
          time_intervals:
            - weekdays: [saturday]
      service_accounts:
        dashboard-reader:
          instance_name: main
          role: Viewer
```

`tests/fixtures/inventory/targets/complete.yml` covers every kind, both selector forms, a cross-namespace import, the legacy `generate_manifests` function and flat keys overriding `spec`.
