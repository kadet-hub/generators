# KubeVirt Generator

Published on [kadet-hub](https://kadet-hub.org/generators/kubevirt/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kubevirt/) page.

Kapitan kadet generator for [KubeVirt](https://kubevirt.io/), its Containerized Data Importer ([CDI](https://github.com/kubevirt/containerized-data-importer)) and the [KubeVirt CSI driver](https://github.com/kubevirt/csi-driver). Built for KubeVirt 1.9.0, CDI 1.66.1 and KubeVirt CSI driver main@3a1a099. The `v1beta1` APIs it emits need KubeVirt 1.7.0 or later: `snapshot.kubevirt.io/v1beta1` is served since 1.3.0, `clone.kubevirt.io/v1beta1` since 1.5.0 and `pool.kubevirt.io/v1beta1` since 1.7.0 (checked in `crds.go` at each release tag).

A VirtualMachine entry with `image`, `disks` and `cloudinit` expands into matching disks, volumes, `dataVolumeTemplates` and a pod network, so a short block yields a VM that KubeVirt admits. The other kinds take reference shorthands. Secrets for `cloudinit_secret_ref` belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kubevirt@sha256:<digest>
        output_path: lib/kubevirt
    compile:
      - output_path: manifests/kubevirt/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/kubevirt
```

### Inventory Contract

All keys live under `parameters.generators.kubevirt`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `virtual_machines.<name>` | VirtualMachine `kubevirt.io/v1` | `<namespace>/<name>-vm` |
| `virtual_machine_instances.<name>` | VirtualMachineInstance `kubevirt.io/v1` | `<namespace>/<name>-vmi` |
| `virtual_machine_instance_migrations.<name>` | VirtualMachineInstanceMigration `kubevirt.io/v1` | `<namespace>/<name>-vmim` |
| `virtual_machine_instance_replica_sets.<name>` | VirtualMachineInstanceReplicaSet `kubevirt.io/v1` | `<namespace>/<name>-vmirs` |
| `virtual_machine_pools.<name>` | VirtualMachinePool `pool.kubevirt.io/v1beta1` | `<namespace>/<name>-vmpool` |
| `virtual_machine_clones.<name>` | VirtualMachineClone `clone.kubevirt.io/v1beta1` | `<namespace>/<name>-vmclone` |
| `virtual_machine_snapshots.<name>` | VirtualMachineSnapshot `snapshot.kubevirt.io/v1beta1` | `<namespace>/<name>-vmsnapshot` |
| `virtual_machine_restores.<name>` | VirtualMachineRestore `snapshot.kubevirt.io/v1beta1` | `<namespace>/<name>-vmrestore` |
| `kubevirt_operators.<name>` | KubeVirt `kubevirt.io/v1` | `<name>-kv` |
| `data_volumes.<name>` | DataVolume `cdi.kubevirt.io/v1beta1` | `<namespace>/<name>-dv` |
| `data_sources.<name>` | DataSource `cdi.kubevirt.io/v1beta1` | `<namespace>/<name>-ds` |
| `object_transfers.<name>` | ObjectTransfer `cdi.kubevirt.io/v1beta1` | `<name>-ot` |
| `csi` | KubeVirt CSI driver, infra or tenant side | see [CSI driver](#csi-driver) |

Every resource accepts `namespace`, `labels`, `annotations` and `spec`; on the cluster-scoped ObjectTransfer, `namespace` only sets the default source namespace. Precedence is generator defaults < `spec` < flat keys: `spec` is deep-merged over the defaults, the flat keys are merged on top, and a flat key that overrides a `spec` value logs a warning. `spec_strategy: replace` keeps `spec` and the flat keys but drops the generator defaults.

| Kind | Flat keys |
|---|---|
| VirtualMachine | `run_strategy`, `running`, `instancetype`, `preference`, `image`, `disks`, `disk_bus`, `cloudinit`, `cloudinit_secret_ref`, `interfaces`, `networks`, `machine_type`, `machine`, `cpu`, `memory`, `resources`, `tolerations`, `affinity`, `template_metadata` |
| VirtualMachineInstance | the VM keys from `image` to `resources` |
| VirtualMachineInstanceReplicaSet | VMI keys, `replicas`, `selector`, `template_metadata` |
| VirtualMachinePool | VM keys or `virtual_machine_template`, `replicas`, `selector` |
| VirtualMachineInstanceMigration | `vmi_name` |
| VirtualMachineClone | `source`, `target` |
| VirtualMachineSnapshot | `source` |
| VirtualMachineRestore | `target`, `snapshot_name` |
| DataVolume | `source`, `size` or `storage`, `pvc`, `content_type`, `preallocation` |
| DataSource | `pvc_name`, `pvc_namespace` |
| ObjectTransfer | `source`, `target` |

Shorthands:

| Input | Result |
|---|---|
| `image: <ref>` | containerDisk volume `containerdisk` plus a virtio disk |
| `disks: [{name, size, source}]` | `dataVolumeTemplates` entry `<vm>-<disk>` (`dvt_name` overrides), dataVolume volume, virtio disk; without `source` the DataVolume is blank |
| `disks: [{name, blank: 5Gi}]` | emptyDisk volume |
| `disks: [{name, type: cdrom}]` | CD-ROM, read-only, bus left to KubeVirt |
| `cloudinit: <userData>` | cloudInitNoCloud volume and disk `cloudinitdisk` |
| `cloudinit_secret_ref: <secret>` | cloudInitNoCloud `secretRef` volume and disk `cloudinit` |
| `memory: 2Gi` | `domain.memory.guest: 2Gi` |
| `instancetype` / `preference: <name>` | `{name: <name>}`; KubeVirt defaults the kind to the cluster-wide one |
| clone, snapshot, restore `source` / `target: <vm>` | `{apiGroup: kubevirt.io, kind: VirtualMachine, name: <vm>}` |
| ObjectTransfer `source: <dv>` | `{kind: DataVolume, name: <dv>, namespace: <own namespace>}` |
| `size: 10Gi` (DataVolume) | `storage.resources.requests.storage: 10Gi` |

A disk `size` on a VMI or VMIRS is ignored with a warning, because only VirtualMachine and VirtualMachinePool have `dataVolumeTemplates`; the volume then references DataVolume `<name>-<disk>`, which must exist.

### Defaults

| Default | Where | Reason |
|---|---|---|
| none for the run strategy | VM, pool template | The compile fails without `run_strategy` (`Always`, `RerunOnFailure`, `Once`, `Manual`, `Halted`), `spec.runStrategy` or the deprecated `running`, which passes through. KubeVirt [rejects a VM without one](https://github.com/kubevirt/kubevirt/blob/v1.9.0/pkg/virt-api/webhooks/validating-webhook/admitters/vms-admitter.go), and the generator does not start VMs implicitly. |
| disk bus `virtio` | generated disks, pool disks and LUNs | KubeVirt [defaults to SATA](https://github.com/kubevirt/kubevirt/blob/v1.9.0/pkg/defaults/amd64.go). CD-ROMs keep KubeVirt's default, it [rejects virtio](https://github.com/kubevirt/kubevirt/blob/v1.9.0/pkg/storage/admitters/disks.go) for them. |
| interface `default` with `masquerade`, network `default` on the pod network | VM, VMI, VMIRS, pool | Each list only when unset. KubeVirt's own default binding is `bridge`; masquerade is the [documented](https://kubevirt.io/user-guide/network/interfaces_and_networks/) binding for the pod network and keeps live migration possible. |
| `replicas: 1`, 2 cores, 2Gi guest memory, `app.kubernetes.io/instance` and `managed-by` template labels, soft pod anti-affinity on the instance label | pool | CPU and memory are skipped when an `instancetype` is set, which KubeVirt rejects in combination. |
| selector `app.kubernetes.io/instance: <name>` copied into the template labels | VMIRS, pool | KubeVirt rejects a selector that does not match the template labels. |
| `source.pvc.namespace` = the DataSource namespace | DataSource | Required by the CDI CRD. |
| `metadata.namespace: kubevirt` | KubeVirt | The namespace of the upstream [kubevirt-cr.yaml](https://github.com/kubevirt/kubevirt/releases/tag/v1.9.0); virt-operator only reconciles the CR in its own namespace. Override with `namespace`. |

The machine type is not set; KubeVirt takes it from its cluster configuration per architecture.

ObjectTransfer is cluster-scoped and emitted without a namespace. CDI 1.66.1 marks it "Deprecated for removal in v1"; upstream plans to remove the kind.

### Example

```yaml
parameters:
  generators:
    kubevirt:
      namespace: vms
      virtual_machines:
        app-vm:
          run_strategy: Always
          instancetype: u1.medium
          preference: ubuntu
          disks:
            - name: rootdisk
              size: 20Gi
              source:
                registry:
                  url: docker://quay.io/containerdisks/ubuntu:24.04
            - name: data
              size: 10Gi
          cloudinit_secret_ref: app-vm-userdata
          spec:
            template:
              spec:
                evictionStrategy: LiveMigrate
      virtual_machine_pools:
        web-pool:
          replicas: 3
          run_strategy: Always
          labels:
            tier: web
          image: quay.io/containerdisks/ubuntu:24.04
          cloudinit_secret_ref: web-userdata
      virtual_machine_snapshots:
        app-vm-nightly:
          source: app-vm
      data_volumes:
        ubuntu-image:
          size: 20Gi
          source:
            registry:
              url: docker://quay.io/containerdisks/ubuntu:24.04
      data_sources:
        ubuntu:
          pvc_name: ubuntu-image
      kubevirt_operators:
        kubevirt:
          spec:
            workloadUpdateStrategy:
              workloadUpdateMethods:
                - LiveMigrate
```

### CSI driver

`csi` renders the KubeVirt CSI driver in its split deployment, after `deploy/` at commit [3a1a099](https://github.com/kubevirt/csi-driver/tree/3a1a099330045754011803e3d53cd8276ff21723/deploy). The controller runs in the infra cluster, in the namespace of the tenant cluster's VMs: it creates DataVolumes there and hotplugs them into the VMs with its own ServiceAccount, and its CSI sidecars reach the tenant cluster API through a kubeconfig Secret. The node plugin runs in the tenant cluster. A target renders one side, chosen by `role`.

| Key | Role | Default | Meaning |
|---|---|---|---|
| `role` | | required | `infra` or `tenant` |
| `namespace` | both | infra: the generator `namespace` fallback chain; tenant: `kubevirt-csi-driver` | |
| `image` | both | the pinned driver image | driver image of the controller and the node plugin |
| `tenant_kubeconfig_secret` | infra | required | name of the Secret in `namespace` whose key `value` holds the tenant kubeconfig, the layout of Cluster API's `<cluster>-kubeconfig` Secrets; the generator never renders its content |
| `infra_cluster_labels` | infra | required | map of labels the controller puts on this tenant cluster's DataVolumes (`--infra-cluster-labels`) |
| `service_account` | infra | `kubevirt-csi` | name of the controller's ServiceAccount, Role and RoleBinding |
| `storage_classes.<name>` | tenant | none | StorageClass; `default: true` marks it default, `infra_storage_class` sets the infra class of its DataVolumes (`infraStorageClassName`, unset: the infra default) |
| `volume_snapshot_classes.<name>` | tenant | none | VolumeSnapshotClass; `default` and `deletion_policy` (`Delete`) |

Unknown keys fail the compile.

| Role | Output keys |
|---|---|
| infra | `<namespace>/<service_account>-sa`, `-role`, `-rolebinding`; `<namespace>-<service_account>-clusterrole`, `-clusterrolebinding` (read PersistentVolumes); `<namespace>/kubevirt-csi-controller-deployment` |
| tenant | `<namespace>-namespace`; `csi.kubevirt.io-csidriver`; `<namespace>/kubevirt-csi-node-daemonset`; per component `node` and `controller`: `<namespace>/kubevirt-csi-<component>-sa`, `kubevirt-csi-<component>-clusterrole`, `-clusterrolebinding`; `<name>-storageclass`, `<name>-volumesnapshotclass` |

The tenant kubeconfig can be the cluster's admin kubeconfig, as Cluster API Provider KubeVirt creates it, or one for the ServiceAccount `kubevirt-csi-controller-sa`, which holds only what the sidecars need; its token comes from `kubectl create token` or a `kubernetes.io/service-account-token` Secret, which the generator does not render. Tenant nodes have to name their VM: providerID `kubevirt://<vm>` with the annotation `cluster.x-k8s.io/cluster-namespace`, as Cluster API Provider KubeVirt sets them, or the annotations `csi.kubevirt.io/infra-vm-name` and `csi.kubevirt.io/infra-vm-namespace`. A VolumeSnapshotClass needs the external-snapshotter CRDs and snapshot-controller in the tenant cluster, which the generator does not render, and the infra cluster a default VolumeSnapshotClass for the driver of each infra storage class: without `infraStorageClassEnforcement` the controller always takes the infra default.

| Default | Where | Reason |
|---|---|---|
| driver image by digest, sidecars by tag and digest as upstream pins them | both | Upstream deploys `:latest` with `imagePullPolicy: Always`. quay.io has no tag per commit; the digest is the `latest` build of 3a1a099 (image label `multi.GIT_SHA`), linux/amd64 only. quay.io removes a digest once `latest` moves on (the previous one already returns 404), so mirror the image and set `image`. |
| non-root UID and GID 1001, RuntimeDefault seccomp, no privilege escalation, read-only root filesystem, all capabilities dropped | controller | Pod Security restricted; upstream sets the same since commit 1522252. |
| `privileged` and UID 0 for the `csi-driver` container, namespace label `pod-security.kubernetes.io/enforce: privileged` | node plugin | Bidirectional mount propagation into `/var/lib/kubelet` and access to the hotplugged disks in `/dev` need it. The registrar and livenessprobe sidecars run without capabilities and with a read-only root filesystem. |
| `strategy: Recreate` | controller | One replica and no leader election in the sidecars; a rolling update would run two controllers. |
| `--enable-vmi-hotplug-fallback=false` | controller | KubeVirt 1.9 deprecates `HotplugVolumes` for `DeclarativeHotplugVolumes`, on by default, under which virt-api rejects the fallback's removevolume call on a VM-owned VMI; upstream's README prescribes the flag for it. |
| liveness probe on the `csi-driver` container | controller | Upstream runs the livenessprobe sidecar, but no probe calls it. |
| no nodeSelector, tolerations or priority class | controller | Upstream pins it to control-plane nodes with `system-cluster-critical`, taken over from the tenant-side deployment, but tolerates the `node-role.kubernetes.io/master` taint removed in Kubernetes 1.25 instead of `node-role.kubernetes.io/control-plane`. In the infra cluster it is a tenant's workload. |
| `datavolumes/source` create in the Role | infra | CDI admits a DataVolume with a snapshot source only if its creator holds this right in the source namespace; without it, restoring a snapshot fails. Volume clones use `dataSourceRef` and do not need it. |
| ClusterRole `kubevirt-csi-controller` | tenant | Upstream's `kubevirt-csi-controller-cr` cut to the rules the four sidecars' own RBAC lists at their pinned tags, plus `volumesnapshotcontents/status` update for csi-snapshotter, which upstream grants only to a ServiceAccount no pod uses. Dropped: the OpenShift SCC rule, `volumesnapshots/status` and the `update` verbs on PersistentVolumes, VolumeAttachments and status subresources. |
| ClusterRole `kubevirt-csi-node`: `get` nodes and the OpenShift `privileged` SCC | tenant | The node service reads only its own Node; upstream also grants writes on PersistentVolumes, claims, VolumeAttachments and Nodes. |
| no preStop hook | registrar | Upstream's hook runs `/bin/sh`, which the distroless image lacks; the registrar removes its socket on SIGTERM. |
| `allowVolumeExpansion: true` | StorageClass | The driver and its resizer sidecar expand volumes, and KubeVirt 1.9 grows the disk of a running VM (`ExpandDisks` is GA); upstream's test setup sets it too. The infra storage class has to allow expansion as well. |
| default class only with `default: true` | StorageClass, VolumeSnapshotClass | Upstream marks its StorageClass default, which takes over PVCs without `storageClassName` when the tenant has another default. |

The controller takes its settings as flags instead of upstream's `driver-config` ConfigMap. `infraStorageClassEnforcement` is not supported, so the tenant can request any infra storage class in its StorageClasses.

```yaml
# infra cluster target
parameters:
  generators:
    kubevirt:
      namespace: tenant-a
      csi:
        role: infra
        tenant_kubeconfig_secret: tenant-a-kubeconfig
        infra_cluster_labels:
          csi-driver/cluster: tenant-a
---
# tenant cluster target
parameters:
  generators:
    kubevirt:
      csi:
        role: tenant
        storage_classes:
          kubevirt:
            default: true
            infra_storage_class: rook-ceph-block
        volume_snapshot_classes:
          kubevirt: {}
```

## Schemas

`schemas/` holds the CRD schemas of KubeVirt 1.9.0 and CDI 1.66.1, the VolumeSnapshotClass CRD and schema from the KubeVirt CSI driver at 3a1a099, and the Kubernetes 1.37.1 schemas of the built-in kinds the CSI driver uses (all Apache-2.0); `schemas/sources.yaml` lists the pinned sources.
