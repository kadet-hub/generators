# rook-ceph Generator

Published on [kadet-hub](https://kadet-hub.org/generators/rook-ceph/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/rook-ceph/) page.

Kapitan kadet generator for [Rook](https://rook.io/) Ceph resources (`ceph.rook.io/v1`). Built for Rook 1.21.0. It renders the custom resources the Rook operator reconciles into a Ceph cluster and its storage: CephCluster, CephBlockPool, CephFilesystem, CephObjectStore, CephObjectStoreUser, CephNFS, CephRBDMirror and CephClient. The operator itself, its CRDs and the CSI drivers come from Rook's Helm chart or `deploy/examples`; StorageClasses and ObjectBucketClaims belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/rook-ceph@sha256:<digest>
        output_path: lib/rook-ceph
    compile:
      - output_path: manifests/rook-ceph/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/rook-ceph
```

### Inventory Contract

All keys live under `parameters.generators.rook-ceph`. Each entry becomes one resource named after its key, or after its `name` if set. The namespace resolves from the entry's `namespace`, then `parameters.generators.rook-ceph.namespace`, then `parameters.namespace`, then `default`.

| Key | Kind | Output key |
|---|---|---|
| `clusters.<name>` | CephCluster | `<namespace>/<name>-cephcluster` |
| `block_pools.<name>` | CephBlockPool | `<namespace>/<name>-blockpool` |
| `filesystems.<name>` | CephFilesystem | `<namespace>/<name>-cephfs` |
| `object_stores.<name>` | CephObjectStore | `<namespace>/<name>-objectstore` |
| `object_store_users.<name>` | CephObjectStoreUser | `<namespace>/<name>-objectuser` |
| `nfs.<name>` | CephNFS | `<namespace>/<name>-nfs` |
| `rbd_mirrors.<name>` | CephRBDMirror | `<namespace>/<name>-rbdmirror` |
| `clients.<name>` | CephClient | `<namespace>/<name>-client` |

Every entry accepts `labels`, `annotations` and `spec`; the label `name` is always added. `spec` is the raw CRD spec for fields without a flat key. Precedence is generator defaults, then `spec`, then flat keys; a flat key replaces the whole `spec` field of the same name and logs a warning.

Flat keys are the snake_case spelling of top-level CRD `spec` fields; their values pass through unchanged, in CRD camelCase:

| Kind | Flat keys |
|---|---|
| CephCluster | `ceph_version`, `data_dir_host_path`, `mon`, `mgr`, `osd`, `storage`, `network`, `resources`, `placement`, `dashboard`, `monitoring`, `external`, `remove_osds_if_out_and_safe_to_remove`, `cleanup_policy`, `disruption_management`, `security`, `health_check`, `log_collector`, `priority_class_names`, `upgrade_policy`, `csi`, `wait_timeout_for_healthy_osd_in_minutes` |
| CephBlockPool | `failure_domain`, `replicated`, `erasure_coded`, `parameters`, `application` |
| CephFilesystem | `metadata_pool`, `data_pools`, `metadata_server`, `status_check`, `mirroring` |
| CephObjectStore | `metadata_pool`, `data_pool`, `gateway`, `zone`, `hosting`, `auth`, `security` |
| CephObjectStoreUser | `store`, `display_name`, `capabilities`, `quotas` |
| CephNFS | `server`, `security` |
| CephRBDMirror | `count`, `peers`, `resources`, `placement`, `priority_class_name` |
| CephClient | `caps`, `client_name` |

Two flat keys do more than rename. On CephCluster, `encrypted_device: true` sets `spec.storage.config.encryptedDevice: "true"`, the string Rook reads for dmcrypt OSDs; it applies to host-based OSDs only, OSDs on PVCs are encrypted with `encrypted: true` on their `storageClassDeviceSets` entry. On CephClient, `name` sets both `metadata.name` and `spec.name` (the CephX client name); `client_name` sets `spec.name` alone and wins over `name`.

A CephCluster without `ceph_version.image` (or `spec.cephVersion.image`) fails the compile unless `external.enable` is set, so a generator update never changes the Ceph version. Rook 1.21.0 ships `quay.io/ceph/ceph:v20.2.4` in its example; multisite object stores need RGW settings applied before upgrading to that release ([ceph-upgrade.md](https://github.com/rook/rook/blob/v1.21.0/Documentation/Upgrade/ceph-upgrade.md#supported-versions)). `storage.useAllNodes` with `useAllDevices` lets Rook claim every empty raw disk on every node.

New CephNFS installs on Rook 1.21 declare a CephBlockPool with `spec.name: .nfs` themselves, since the operator no longer creates it ([release notes](https://github.com/rook/rook/releases/tag/v1.21.0)); deleting that CR deletes the pool and the NFS exports in it.

### Defaults

The generator fills these only where the inventory leaves them unset:

| Kind | Default | Why |
|---|---|---|
| CephCluster | `dataDirHostPath: /var/lib/rook` | The CRD makes it optional, but Rook's example marks it "Must be specified"; without it the daemons keep mon data in an emptyDir ([cluster.yaml](https://github.com/rook/rook/blob/v1.21.0/deploy/examples/cluster.yaml#L37-L40), [spec.go](https://github.com/rook/rook/blob/v1.21.0/pkg/operator/ceph/controller/spec.go#L194-L200)). |
| CephFilesystem | `metadataServer: {activeCount: 1, activeStandby: true}` | `metadataServer.activeCount` is required by the CRD; values from [filesystem.yaml](https://github.com/rook/rook/blob/v1.21.0/deploy/examples/filesystem.yaml). |
| CephNFS | `server.active: 1` | Required by the CRD; [nfs.yaml](https://github.com/rook/rook/blob/v1.21.0/deploy/examples/nfs.yaml). |
| CephRBDMirror | `count: 1` | Required by the CRD; [rbdmirror.yaml](https://github.com/rook/rook/blob/v1.21.0/deploy/examples/rbdmirror.yaml). |

Mon and mgr counts, the msgr2 requirement and other settings the operator defaults are not emitted. CephClient `caps` has no default, since it grants access to the cluster; an entry without it fails schema validation. Rook's example also sets `security.cephx.csi.keyType: aes` for nodes with a Linux kernel older than 7.0; the generator leaves it to the inventory because it depends on the node kernel.

### Example

```yaml
parameters:
  generators:
    rook-ceph:
      namespace: rook-ceph
      clusters:
        rook-ceph:
          ceph_version:
            image: quay.io/ceph/ceph:v20.2.4
          mon:
            count: 3
            allowMultiplePerNode: false
          dashboard:
            enabled: true
            ssl: true
          spec:
            storage:
              useAllNodes: true
              useAllDevices: true
      block_pools:
        replicapool:
          failure_domain: host
          replicated:
            size: 3
        builtin-nfs:
          failure_domain: host
          replicated:
            size: 3
          spec:
            name: .nfs
      filesystems:
        myfs:
          metadata_pool:
            replicated:
              size: 3
          data_pools:
            - name: replicated
              replicated:
                size: 3
      object_stores:
        my-store:
          metadata_pool:
            replicated:
              size: 3
          data_pool:
            erasureCoded:
              dataChunks: 2
              codingChunks: 1
          gateway:
            port: 80
            instances: 1
      object_store_users:
        my-user:
          store: my-store
          display_name: my-user
      nfs:
        my-nfs: {}
      clients:
        rbd-app:
          client_name: app
          caps:
            mon: profile rbd
            osd: profile rbd pool=replicapool
```

`rook-ceph` gets `/var/lib/rook`, `myfs` one active MDS with a standby, and `my-nfs` one server.

## Output Files

| Output key | Kind |
|---|---|
| `<namespace>/<name>-cephcluster` | `ceph.rook.io/v1` CephCluster |
| `<namespace>/<name>-blockpool` | `ceph.rook.io/v1` CephBlockPool |
| `<namespace>/<name>-cephfs` | `ceph.rook.io/v1` CephFilesystem |
| `<namespace>/<name>-objectstore` | `ceph.rook.io/v1` CephObjectStore |
| `<namespace>/<name>-objectuser` | `ceph.rook.io/v1` CephObjectStoreUser |
| `<namespace>/<name>-nfs` | `ceph.rook.io/v1` CephNFS |
| `<namespace>/<name>-rbdmirror` | `ceph.rook.io/v1` CephRBDMirror |
| `<namespace>/<name>-client` | `ceph.rook.io/v1` CephClient |

`v1` is the served storage version of every kind at Rook 1.21.0; none is deprecated. The compiled output is validated against the upstream CRD schemas in `schemas/ceph.rook.io/`.
