# cloudnative-pg Generator

Published on [kadet-hub](https://kadet-hub.org/generators/cloudnative-pg/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/cloudnative-pg/) page.

Kapitan kadet generator for [CloudNativePG](https://cloudnative-pg.io/) PostgreSQL clusters. Built for CloudNativePG 1.30.1 and the Barman Cloud Plugin 0.15.1. It renders Cluster, Database, Pooler, ScheduledBackup and Backup (`postgresql.cnpg.io/v1`) and the plugin's ObjectStore (`barmancloud.cnpg.io/v1`). PodMonitors come from the prometheus-operator generator, see [Monitoring](#monitoring). Backups go through the [Barman Cloud Plugin](https://cloudnative-pg.io/plugin-barman-cloud/), which replaces the in-tree `barmanObjectStore` deprecated since CloudNativePG 1.26. The operator, the plugin and the Secrets with object store credentials are installed separately.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/cloudnative-pg@sha256:<digest>
        output_path: lib/cloudnative-pg
    compile:
      - output_path: manifests/cloudnative-pg/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/cloudnative-pg
```

### Example

```yaml
parameters:
  generators:
    cloudnative-pg:
      namespace: databases
      object_stores:
        app-db-store:
          configuration:
            destinationPath: s3://pg-backups/app-db
            endpointURL: https://s3.example.com
            s3Credentials:
              accessKeyId:
                name: app-db-s3
                key: ACCESS_KEY_ID
              secretAccessKey:
                name: app-db-s3
                key: ACCESS_SECRET_KEY
            wal:
              compression: gzip
          retention_policy: 30d
      clusters:
        app-db:
          image_name: ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie
          storage: 50Gi
          backup:
            object_store: app-db-store
      databases:
        app:
          cluster: app-db
          owner: app
      poolers:
        app-db-pooler-rw:
          cluster: app-db
          pool_mode: transaction
      scheduled_backups:
        app-db-daily:
          cluster: app-db
          schedule: 0 3 * * *
```

This yields a three-instance Cluster that archives WAL to `app-db-store`, the `app` database, a PgBouncer pooler in transaction mode on the `-rw` service, and a daily plugin backup at 03:00:00.

### Inventory Contract

All keys live under `parameters.generators.cloudnative-pg`. Each entry becomes one resource named after its key, or after its `name` if it sets one. A reference such as `cluster: <name>` names the resource. Two entries of a section with the same name in one namespace fail the compile. The namespace resolves from the entry's `namespace`, then `parameters.generators.cloudnative-pg.namespace`, then `parameters.namespace`, then `default`.

| Key | Kind |
|---|---|
| `clusters.<name>` | Cluster |
| `databases.<name>` | Database |
| `poolers.<name>` | Pooler |
| `scheduled_backups.<name>` | ScheduledBackup |
| `backups.<name>` | Backup |
| `object_stores.<name>` | ObjectStore |

Every entry accepts `labels`, `annotations` and `spec`, the raw CRD spec for fields without a flat key. Precedence is generator defaults, then `spec`, then flat keys and shorthands; a flat key replaces the whole `spec` field of the same name and logs a warning.

Flat keys are the snake_case spelling of top-level CRD `spec` fields; their values pass through unchanged, in CRD camelCase:

| Kind | Flat keys |
|---|---|
| Cluster | `instances`, `image_name`, `image_catalog_ref`, `storage`, `wal_storage`, `postgresql`, `bootstrap`, `resources`, `affinity`, `monitoring`, `managed`, `plugins`, `replica`, `external_clusters`, `certificates` |
| Database | `cluster`, `database_name` (`spec.name`), `owner`, `ensure`, `database_reclaim_policy`, `encoding`, `locale`, `template`, `extensions`, `schemas` |
| Pooler | `cluster`, `instances`, `type`, `pgbouncer`, `template`, `service_template` |
| ScheduledBackup | `cluster`, `schedule`, `method`, `plugin_configuration`, `target`, `online`, `immediate`, `suspend`, `backup_owner_reference` |
| Backup | `cluster`, `method`, `plugin_configuration`, `target`, `online` |
| ObjectStore | `configuration`, `retention_policy`, `instance_sidecar_configuration` |

Shorthands:

| Input | Result |
|---|---|
| `cluster: <name>` | `cluster: {name: <name>}` |
| Cluster `storage: <size>`, `wal_storage: <size>` | `storage: {size: <size>}`, `walStorage: {size: <size>}` |
| Cluster `backup: {object_store: <store>, server_name: <name>}` | a `plugins` entry `barman-cloud.cloudnative-pg.io` with `isWALArchiver: true` and the parameters `barmanObjectName` and, if set, `serverName`, as in the plugin's [usage guide](https://github.com/cloudnative-pg/plugin-barman-cloud/blob/v0.15.1/web/docs/usage.md#configuring-wal-archiving); other plugins stay |
| Pooler `pool_mode: <mode>` | `pgbouncer.poolMode: <mode>` |
| ScheduledBackup five-field `schedule` | a leading `0` seconds field; CloudNativePG uses a six-field cron ([backup.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/backup.md#cron-schedule)) |

When a major PostgreSQL upgrade changes `image_name`, change `backup.server_name` with it, so the new major version archives to a new path ([postgres_upgrades.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/postgres_upgrades.md)).

### Defaults

The generator fills these only where the inventory leaves them unset:

| Kind | Default | Why |
|---|---|---|
| Cluster | `instances: 3` | A primary and two standbys, as in [cluster-example.yaml](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/samples/cluster-example.yaml); the CRD default of 1 has no failover. |
| Database | `name: <entry key>` | `spec.name`, the PostgreSQL database name, is required by the CRD. |
| Pooler | `pgbouncer: {}` | Required by the CRD, which defaults `poolMode` to `session` ([connection_pooling.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/connection_pooling.md)). |
| ScheduledBackup, Backup | `method: plugin`, `pluginConfiguration: {name: barman-cloud.cloudnative-pg.io}` | The CRD default `barmanObjectStore` is deprecated since 1.26 ([backup.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/backup.md#backup-methods)); `pluginConfiguration` is set only for `method: plugin`. |
| ScheduledBackup | `backupOwnerReference: self` | The Backups it creates are deleted with it; the CRD default `none` is the legacy behaviour ([backup.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/backup.md#backup-owner-reference-specbackupownerreference)). |

A Cluster without `storage` size or a `pvcTemplate` storage request fails the compile, since the operator's admission rejects it. A `backup` without `object_store` fails, and so does an ObjectStore with `configuration.serverName`, which the plugin requires empty ([parameters.md](https://github.com/cloudnative-pg/plugin-barman-cloud/blob/v0.15.1/web/docs/parameters.md)). A Pooler named like its Cluster or the Cluster's `-rw`, `-ro` or `-r` Service fails, since the Pooler's Service of the same name would patch the Cluster's; name it like the upstream `pooler-example-rw`. A Cluster whose `backup.object_store` is an ObjectStore of this inventory in another namespace fails, since the plugin reads it from the Cluster's namespace. A Backup or ScheduledBackup using the Barman Cloud Plugin for a Cluster of this inventory without the plugin fails, and so does `backup` together with `spec.backup.barmanObjectStore`, which the webhook rejects. The in-tree `barmanObjectStore`, removed in CloudNativePG 1.31.0 ([release notes](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/release_notes/v1.30.md)), and `monitoring.enablePodMonitor` still pass through, with a warning. Database `owner`, ObjectStore `configuration.destinationPath` and ScheduledBackup `schedule` have no default and fail schema validation when missing.

Pooler `instances` stays at the CRD default of 1. Nothing grants access or exposure by default: `enableSuperuserAccess` stays at the CRD default `false`, the Cluster and Pooler Services stay `ClusterIP`, and a LoadBalancer or extra service is set through `managed.services` or `service_template`. Without `image_name` the operator picks its default image, `ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie` at 1.30.1, and an operator upgrade can change it. ObjectStore `retention_policy` has no default, so backups are kept until you set one. A Backup is an immutable one-shot request; keep it in the inventory only until it has run.

### Monitoring

CloudNativePG 1.30 deprecates `monitoring.enablePodMonitor` in favour of a PodMonitor you own ([monitoring.md](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/docs/src/monitoring.md)). Render it with the [prometheus-operator](https://kadet-hub.org/generators/prometheus-operator/) generator in the Cluster's namespace; it must select `cnpg.io/cluster: <name>` and scrape port `metrics`. For `app-db`:

```yaml
parameters:
  generators:
    prometheus_operator:
      pod_monitors:
        app-db:
          namespace: databases
          selector:
            cnpg.io/cluster: app-db
          pod_metrics_endpoints:
            - metrics
```

With `monitoring.tls.enabled: true` on the Cluster, the endpoint scrapes over HTTPS with the cluster CA (`app-db-ca`, or the Secret in `certificates.serverCASecret`) and the server name `app-db-rw`:

```yaml
parameters:
  generators:
    prometheus_operator:
      pod_monitors:
        app-db:
          namespace: databases
          selector:
            cnpg.io/cluster: app-db
          pod_metrics_endpoints:
            - port: metrics
              scheme: https
              tlsConfig:
                ca:
                  secret:
                    name: app-db-ca
                    key: ca.crt
                serverName: app-db-rw
```

## Output Files

| Output key | Kind |
|---|---|
| `<namespace>/<name>-cluster` | `postgresql.cnpg.io/v1` Cluster |
| `<namespace>/<name>-database` | `postgresql.cnpg.io/v1` Database |
| `<namespace>/<name>-pooler` | `postgresql.cnpg.io/v1` Pooler |
| `<namespace>/<name>-scheduledbackup` | `postgresql.cnpg.io/v1` ScheduledBackup |
| `<namespace>/<name>-backup` | `postgresql.cnpg.io/v1` Backup |
| `<namespace>/<name>-objectstore` | `barmancloud.cnpg.io/v1` ObjectStore |

`v1` is the only served version and the storage version of every kind at CloudNativePG 1.30.1 and the Barman Cloud Plugin 0.15.1; none is deprecated. The compiled output is validated against the upstream CRD schemas in `schemas/`.
