# Velero Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/velero/) page.

Kapitan kadet generator for [Velero](https://velero.io/) resources (`velero.io/v1`). Built for Velero 1.18.4.

- **Backup**: one-shot backup of cluster resources and volumes
- **Schedule**: cron-driven Backup
- **Restore**: restore from a Backup or from the latest backup of a Schedule
- **BackupStorageLocation**: object storage target for backups
- **VolumeSnapshotLocation**: provider target for volume snapshots

Only these custom resources are rendered. The Velero install (Deployment, node agent, credentials Secret) belongs in the `helm` or `kubernetes` generator. One-shot request kinds (ServerStatusRequest, DownloadRequest, DeleteBackupRequest) are out of scope: a DeleteBackupRequest reconciled from Git deletes backups again on every sync. BackupRepository, PodVolumeBackup, PodVolumeRestore, DataUpload and DataDownload are created by Velero itself.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/velero@sha256:<digest>
        output_path: lib/velero
    compile:
      - output_path: manifests/velero/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/velero
```

### Inventory Contract

All keys live under `parameters.generators.velero`.

| Key | Kind | Output key |
|---|---|---|
| `backups.<name>` | Backup | `<namespace>/<name>-backup` |
| `schedules.<name>` | Schedule | `<namespace>/<name>-schedule` |
| `restores.<name>` | Restore | `<namespace>/<name>-restore` |
| `backup_storage_locations.<name>` | BackupStorageLocation | `<namespace>/<name>-bsl` |
| `volume_snapshot_locations.<name>` | VolumeSnapshotLocation | `<namespace>/<name>-vsl` |

Every entry accepts `namespace`, `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. Precedence is generator defaults < `spec` < flat keys: a flat key wins over the same field in `spec` and logs a warning.

Namespace: `namespace` on the entry, then `generators.velero.namespace`, then `velero`. `parameters.namespace` is not read: the Velero server only watches its install namespace, and `parameters.namespace` usually names a workload namespace.

Flat keys map to the camelCase CRD field of the same name (`included_namespaces` → `includedNamespaces`). Exceptions are noted.

| Kind | Flat keys |
|---|---|
| Backup | `included_namespaces`, `excluded_namespaces`, `included_resources`, `excluded_resources`, `label_selector`, `storage_location`, `volume_snapshot_locations`, `ttl`, `snapshot_volumes`, `default_volumes_to_fs_backup`, `snapshot_move_data`, `include_cluster_resources` |
| Schedule | `schedule`, `paused`, `skip_immediately`, `use_owner_references_in_backup`, `template` (Backup flat keys plus its own `spec` passthrough, rendered as `spec.template`) |
| Restore | `backup_name`, `schedule_name`, `included_namespaces`, `excluded_namespaces`, `namespace_mapping`, `restore_pvs` (→ `restorePVs`), `existing_resource_policy`, `preserve_node_ports` |
| BackupStorageLocation | `provider`, `bucket`, `prefix`, `ca_cert`, `ca_cert_ref` (→ `objectStorage.{bucket,prefix,caCert,caCertRef}`; `caCert` is deprecated upstream), `config`, `credential`, `default`, `access_mode`, `backup_sync_period`, `validation_frequency` |
| VolumeSnapshotLocation | `provider`, `config`, `credential` |

A Restore must set exactly one of `backup_name` and `schedule_name` (or `backupName`/`scheduleName` in `spec`), otherwise the compile fails with `ValueError: velero Restore '<name>': ...`. The Velero controller enforces the same rule at runtime.

### Defaults

The generator fills in two fields when the inventory sets them neither as a flat key nor in `spec`.

| Field | Default | Reason |
|---|---|---|
| BackupStorageLocation `default` | `true` if `backup_storage_locations` has exactly one entry | Backups without `storageLocation` go to the location marked default. Without one, Velero falls back to a location named `default` through the server flag [`--default-backup-storage-location`](https://github.com/velero-io/velero/blob/v1.18.4/pkg/cmd/server/config/config.go#L238), which is deprecated for removal in v2.0, and the [controller](https://github.com/velero-io/velero/blob/v1.18.4/pkg/controller/backup_storage_location_controller.go#L299-L301) warns that no default is set. See [locations](https://velero.io/docs/v1.18/locations/). |
| Schedule `template` | `{}` | The CRD requires it. An empty template backs up all namespaces ([Schedule API](https://velero.io/docs/v1.18/api-types/schedule/)). |

Set `default: false` on the single location when another location, for example one from the Velero Helm chart, is the default. If two locations are marked default, Velero keeps the one created last.

All other unset keys are not emitted, so the [Velero server flags](https://github.com/velero-io/velero/blob/v1.18.4/pkg/cmd/server/config/config.go#L233-L255) decide: `ttl` 720h, `defaultVolumesToFsBackup` and `snapshotMoveData` off, `backupSyncPeriod` and `validationFrequency` 1m. These keys are deliberately left without a generator default:

- `use_owner_references_in_backup` stays unset (`false`). With `true`, deleting the Schedule deletes its backups ([Schedule API](https://velero.io/docs/v1.18/api-types/schedule/)).
- `prefix` is not derived. Velero needs a dedicated bucket or a prefix ([locations](https://velero.io/docs/v1.18/locations/)), and changing the prefix of a location in use hides its existing backups.
- `config` keys of the AWS plugin are not derived from `s3Url`. `s3ForcePathStyle: "true"` is for path-style services such as MinIO and then requires `region` ([plugin v1.14.4](https://github.com/vmware-tanzu/velero-plugin-for-aws/blob/v1.14.4/backupstoragelocation.md)). `config` values are strings: write `"true"`, not `true`.
- VolumeSnapshotLocations get no default: with one location per provider, Velero uses it automatically ([locations](https://velero.io/docs/v1.18/locations/)).

`schedule` is a five-field cron expression. Prefix it with `CRON_TZ=<IANA zone>` to keep the run time across daylight saving changes ([backup reference](https://velero.io/docs/v1.18/backup-reference/)).

### Example

```yaml
parameters:
  generators:
    velero:
      backup_storage_locations:
        default:
          provider: aws
          bucket: velero-backups
          prefix: cluster-a
          config:
            region: eu-central-1
          credential:
            name: cloud-credentials
            key: cloud
      volume_snapshot_locations:
        default:
          provider: aws
          config:
            region: eu-central-1
      schedules:
        nightly:
          schedule: "CRON_TZ=Europe/Berlin 0 2 * * *"
          template:
            included_namespaces: ["*"]
            excluded_namespaces: [kube-system]
            ttl: 168h0m0s
            spec:
              itemOperationTimeout: 4h0m0s
      backups:
        pre-upgrade:
          included_namespaces: [apps]
          snapshot_move_data: true
      restores:
        apps-from-nightly:
          schedule_name: nightly
          included_namespaces: [apps]
          namespace_mapping:
            apps: apps-restored
          restore_pvs: true
```

This renders `velero/default-bsl` (marked default as the only location), `velero/default-vsl`, `velero/nightly-schedule`, `velero/pre-upgrade-backup` and `velero/apps-from-nightly-restore`.
