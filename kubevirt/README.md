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
| `image` | both | required | driver image of the controller and the node plugin, see [Driver image](#driver-image) |
| `namespace` | both | infra: the generator `namespace` fallback chain; tenant: `kubevirt-csi-driver` | |
| `tenant_kubeconfig_secret` | infra | required | name of the Secret in `namespace` whose key `value` holds the tenant kubeconfig, the layout of Cluster API's `<cluster>-kubeconfig` Secrets; the generator never renders its content |
| `infra_cluster_labels` | infra | required | map of labels the controller puts on this tenant cluster's DataVolumes (`--infra-cluster-labels`) |
| `service_account` | infra | `kubevirt-csi` | name of the controller's ServiceAccount, Role and RoleBinding |
| `allowed_storage_classes` | infra | unset: any infra storage class | list of the infra storage classes the tenant may name in `infra_storage_class` |
| `allow_default_storage_class` | infra | `false` | with `allowed_storage_classes`: also allow tenant StorageClasses without `infra_storage_class`, which get the infra default class |
| `snapshot_classes.<infra storage class>` | infra | none | with `allowed_storage_classes`: list of the infra VolumeSnapshotClasses for snapshots of that class's volumes |
| `storage_classes.<name>` | tenant | none | StorageClass; `default: true` marks it default, `infra_storage_class` sets the infra class of its DataVolumes (`infraStorageClassName`, unset: the infra default) |
| `volume_snapshot_classes.<name>` | tenant | none | VolumeSnapshotClass; `default`, `deletion_policy` (`Delete`) and `infra_snapshot_class` (`infraSnapshotClassName`), which picks one of the infra side's `snapshot_classes` |

Unknown keys fail the compile, and so do `snapshot_classes` naming a class outside `allowed_storage_classes` and `snapshot_classes` together with `allow_default_storage_class`.

| Role | Output keys |
|---|---|
| infra | `<namespace>/<service_account>-sa`, `-role`, `-rolebinding`; `<namespace>-<service_account>-clusterrole`, `-clusterrolebinding` (read PersistentVolumes); `<namespace>/kubevirt-csi-controller-deployment` |
| tenant | `<namespace>-namespace`; `csi.kubevirt.io-csidriver`; `<namespace>/kubevirt-csi-node-daemonset`; per component `node` and `controller`: `<namespace>/kubevirt-csi-<component>-sa`, `kubevirt-csi-<component>-clusterrole`, `-clusterrolebinding`; `<namespace>/kubevirt-csi-controller-sa-token-secret`; `<name>-storageclass`, `<name>-volumesnapshotclass` |

#### Driver image

Upstream publishes the driver only as `quay.io/kubevirt/kubevirt-csi-driver:latest` and deletes a digest once `latest` moves on (the previous one already returns 404), so `image` has no default. Mirror

```
quay.io/kubevirt/kubevirt-csi-driver@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409
```

the `latest` build of 3a1a099 (image label `multi.GIT_SHA`, linux/amd64 only), into a registry both clusters can pull from, and set `image` to the mirror by digest. The fixtures use the quay.io reference above, which works only while it is `latest`. The sidecars are pinned by tag and digest as upstream pins them at 3a1a099, except csi-snapshotter (see Defaults).

#### Storage class enforcement

Without `allowed_storage_classes` the controller runs as upstream deploys it: the tenant may name any infra storage class, and snapshots use the infra cluster's default VolumeSnapshotClass for the volume's driver. With it, the controller gets upstream's `infraStorageClassEnforcement` setting as the environment variable `INFRA_STORAGE_CLASS_ENFORCEMENT`: `allowAll: false`, `allowDefault` from `allow_default_storage_class`, `allowList` and one `storageSnapshotMapping` entry per `snapshot_classes` key. Without `allow_default_storage_class`, a snapshot needs a `snapshot_classes` entry for its volume's infra class and a tenant VolumeSnapshotClass whose `infra_snapshot_class` names one of its classes; with it, the controller ignores the mapping and takes the infra default.

#### Tenant kubeconfig

The tenant role renders the ServiceAccount `kubevirt-csi-controller-sa`, which holds only what the controller's sidecars need, and the Secret `kubevirt-csi-controller-sa-token` of type `kubernetes.io/service-account-token`, which the tenant cluster's token controller fills. Build the infra-side Secret from it; `<tenant-api>` is the tenant API server as the infra cluster's pods reach it:

```sh
# against the tenant cluster
kubectl -n kubevirt-csi-driver get secret kubevirt-csi-controller-sa-token -o jsonpath='{.data.ca\.crt}' | base64 -d > ca.crt
TOKEN=$(kubectl -n kubevirt-csi-driver get secret kubevirt-csi-controller-sa-token -o jsonpath='{.data.token}' | base64 -d)
kubectl config --kubeconfig=value set-cluster tenant --server=https://<tenant-api>:6443 --certificate-authority=ca.crt --embed-certs
kubectl config --kubeconfig=value set-credentials kubevirt-csi --token="$TOKEN"
kubectl config --kubeconfig=value set-context tenant --cluster=tenant --user=kubevirt-csi
kubectl config --kubeconfig=value use-context tenant
# against the infra cluster, the names of tenant_kubeconfig_secret and namespace
kubectl -n tenant-a create secret generic tenant-a-kubeconfig --from-file=value
```

The cluster's admin kubeconfig, which Cluster API Provider KubeVirt stores in the same layout, works too, but gives the controller cluster-admin on the tenant.

#### Prerequisites

Tenant nodes have to name their VM: providerID `kubevirt://<vm>` with the annotation `cluster.x-k8s.io/cluster-namespace`, as Cluster API Provider KubeVirt sets them, or the annotations `csi.kubevirt.io/infra-vm-name` and `csi.kubevirt.io/infra-vm-namespace`. A VolumeSnapshotClass needs the external-snapshotter CRDs and snapshot-controller in the tenant cluster, which the generator does not render.

#### Defaults

| Default | Where | Reason |
|---|---|---|
| non-root UID and GID 1001, RuntimeDefault seccomp, no privilege escalation, read-only root filesystem, all capabilities dropped | controller | Pod Security restricted; upstream sets the same since commit 1522252. |
| `privileged` and UID 0 for the `csi-driver` container, namespace label `pod-security.kubernetes.io/enforce: privileged` | node plugin | Bidirectional mount propagation into `/var/lib/kubelet` and access to the hotplugged disks in `/dev` need it. The registrar and livenessprobe sidecars run without capabilities and with a read-only root filesystem. |
| csi-snapshotter v8.7.0 instead of upstream's v4.2.1 | controller | v4.2.1 predates `sourceVolumeMode`, so the external-snapshotter v8 CRDs reject its VolumeSnapshotContent updates and no snapshot becomes ready ([kubevirt/csi-driver#395](https://github.com/kubevirt/csi-driver/issues/395)). v8.7.0 is the current external-snapshotter release. |
| `strategy: Recreate` | controller | One replica and no leader election in the sidecars; a rolling update would run two controllers. |
| `--enable-vmi-hotplug-fallback=false` | controller | KubeVirt 1.9 deprecates `HotplugVolumes` for `DeclarativeHotplugVolumes`, on by default, under which virt-api rejects the fallback's removevolume call on a VM-owned VMI; upstream's README prescribes the flag for it. |
| liveness probe on the `csi-driver` container | controller | Upstream runs the livenessprobe sidecar, but no probe calls it. |
| settings as flags and environment instead of upstream's `driver-config` ConfigMap | controller | The generator knows the values at compile time, and a changed value rolls the pod. |
| no nodeSelector, tolerations or priority class | controller | Upstream pins it to control-plane nodes with `system-cluster-critical`, taken over from the tenant-side deployment, but tolerates the `node-role.kubernetes.io/master` taint removed in Kubernetes 1.25 instead of `node-role.kubernetes.io/control-plane`. In the infra cluster it is a tenant's workload. |
| `datavolumes/source` create in the Role | infra | CDI admits a DataVolume with a snapshot source only if its creator holds this right in the source namespace; without it, restoring a snapshot fails. Volume clones use `dataSourceRef` and do not need it. |
| ClusterRole `kubevirt-csi-controller` | tenant | Upstream's `kubevirt-csi-controller-cr` cut to the rules the four sidecars' own RBAC lists at their pinned tags, plus `volumesnapshotcontents/status` for csi-snapshotter, which upstream grants only to a ServiceAccount no pod uses. Dropped: the OpenShift SCC rule, `volumesnapshots/status`, create and delete on VolumeSnapshotContents, and the `update` verbs on PersistentVolumes, VolumeAttachments and the status subresources. Without rules for `groupsnapshot.storage.k8s.io` csi-snapshotter turns VolumeGroupSnapshot off at start, which the driver does not implement. |
| ClusterRole `kubevirt-csi-node`: `get` nodes and the OpenShift `privileged` SCC | tenant | The node service reads only its own Node; upstream also grants writes on PersistentVolumes, claims, VolumeAttachments and Nodes. |
| no preStop hook | registrar | Upstream's hook runs `/bin/sh`, which the distroless image lacks; the registrar removes its socket on SIGTERM. |
| `allowVolumeExpansion: true` | StorageClass | The driver and its resizer sidecar expand volumes, and KubeVirt 1.9 grows the disk of a running VM (`ExpandDisks` is GA); upstream's test setup sets it too. The infra storage class has to allow expansion as well. |
| default class only with `default: true` | StorageClass, VolumeSnapshotClass | Upstream marks its StorageClass default, which takes over PVCs without `storageClassName` when the tenant has another default. |

#### Example

```yaml
# infra cluster target
parameters:
  generators:
    kubevirt:
      namespace: tenant-a
      csi:
        role: infra
        image: registry.example.com/kubevirt/kubevirt-csi-driver@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409
        tenant_kubeconfig_secret: tenant-a-kubeconfig
        infra_cluster_labels:
          csi-driver/cluster: tenant-a
        allowed_storage_classes:
          - rook-ceph-block
        snapshot_classes:
          rook-ceph-block:
            - csi-rbdplugin-snapclass
---
# tenant cluster target
parameters:
  generators:
    kubevirt:
      csi:
        role: tenant
        image: registry.example.com/kubevirt/kubevirt-csi-driver@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409
        storage_classes:
          kubevirt:
            default: true
            infra_storage_class: rook-ceph-block
        volume_snapshot_classes:
          kubevirt:
            infra_snapshot_class: csi-rbdplugin-snapclass
```

## Schemas

`schemas/` holds the CRD schemas of KubeVirt 1.9.0 and CDI 1.66.1, the VolumeSnapshotClass CRD and schema from the KubeVirt CSI driver at 3a1a099, and the Kubernetes 1.37.1 schemas of the built-in kinds the CSI driver uses (all Apache-2.0); `schemas/sources.yaml` lists the pinned sources.
