# KubeVirt Generator

Published on [kadet-hub](https://kadet-hub.org/generators/kubevirt/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kubevirt/) page.

Kapitan kadet generator for [KubeVirt](https://kubevirt.io/), its Containerized Data Importer ([CDI](https://github.com/kubevirt/containerized-data-importer)) and the [KubeVirt CSI driver](https://github.com/kubevirt/csi-driver). Built for KubeVirt 1.9.1, CDI 1.66.1, KubeVirt CSI driver main@e13603a and external-snapshotter 8.7.0. The `v1beta1` APIs it emits need KubeVirt 1.7.0 or later: `snapshot.kubevirt.io/v1beta1` is served since 1.3.0, `clone.kubevirt.io/v1beta1` since 1.5.0 and `pool.kubevirt.io/v1beta1` since 1.7.0 (checked in `crds.go` at each release tag).

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
| none for the run strategy | VM, pool template | The compile fails without `run_strategy` (`Always`, `RerunOnFailure`, `Once`, `Manual`, `Halted`), `spec.runStrategy` or the deprecated `running`, which passes through. KubeVirt [rejects a VM without one](https://github.com/kubevirt/kubevirt/blob/v1.9.1/pkg/virt-api/webhooks/validating-webhook/admitters/vms-admitter.go), and the generator does not start VMs implicitly. |
| disk bus `virtio` | generated disks, pool disks and LUNs | KubeVirt [defaults to SATA](https://github.com/kubevirt/kubevirt/blob/v1.9.1/pkg/defaults/amd64.go). CD-ROMs keep KubeVirt's default, it [rejects virtio](https://github.com/kubevirt/kubevirt/blob/v1.9.1/pkg/storage/admitters/disks.go) for them. |
| interface `default` with `masquerade`, network `default` on the pod network | VM, VMI, VMIRS, pool | Each list only when unset. KubeVirt's own default binding is `bridge`; masquerade is the [documented](https://kubevirt.io/user-guide/network/interfaces_and_networks/) binding for the pod network and keeps live migration possible. |
| `replicas: 1`, 2 cores, 2Gi guest memory, `app.kubernetes.io/instance` and `managed-by` template labels, soft pod anti-affinity on the instance label | pool | CPU and memory are skipped when an `instancetype` is set, which KubeVirt rejects in combination. |
| selector `app.kubernetes.io/instance: <name>` copied into the template labels | VMIRS, pool | KubeVirt rejects a selector that does not match the template labels. |
| `source.pvc.namespace` = the DataSource namespace | DataSource | Required by the CDI CRD. |
| `metadata.namespace: kubevirt` | KubeVirt | The namespace of the upstream [kubevirt-cr.yaml](https://github.com/kubevirt/kubevirt/releases/tag/v1.9.1); virt-operator only reconciles the CR in its own namespace. Override with `namespace`. |

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

`csi` renders the KubeVirt CSI driver in its split deployment, after `deploy/` at commit [e13603a](https://github.com/kubevirt/csi-driver/tree/e13603a1527794ac9599765e622029c284431e23/deploy). The controller runs in the infra cluster, in the namespace of the tenant cluster's VMs: it creates DataVolumes there and hotplugs them into the VMs with its own ServiceAccount, and its CSI sidecars reach the tenant cluster API through a kubeconfig Secret. The node plugin runs in the tenant cluster. A target renders one side, chosen by `role`.

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
| `snapshot_controller` | tenant | `false` | `true` renders the snapshot-controller and the `snapshot.storage.k8s.io` CRDs, see [Snapshot controller](#snapshot-controller) |

Unknown keys fail the compile, and so do `snapshot_classes` naming a class outside `allowed_storage_classes` and `snapshot_classes` together with `allow_default_storage_class`.

| Role | Output keys |
|---|---|
| infra | `<namespace>/<service_account>-sa`, `-role`, `-rolebinding`; `<namespace>-<service_account>-clusterrole`, `-clusterrolebinding` (read PersistentVolumes); `<namespace>/kubevirt-csi-controller-deployment` |
| tenant | `<namespace>-namespace`; `csi.kubevirt.io-csidriver`; `<namespace>/kubevirt-csi-node-daemonset`; per component `node` and `controller`: `<namespace>/kubevirt-csi-<component>-sa`, `kubevirt-csi-<component>-clusterrole`, `-clusterrolebinding`; `<namespace>/kubevirt-csi-controller-sa-token-secret`; `<name>-storageclass`, `<name>-volumesnapshotclass`; with `snapshot_controller`: `<crd name>-crd`, `<namespace>/snapshot-controller-sa`, `-deployment`, `<namespace>/snapshot-controller-leaderelection-role`, `-rolebinding`, `snapshot-controller-runner-clusterrole`, `-clusterrolebinding` |

#### Driver image

Upstream publishes the driver only as `quay.io/kubevirt/kubevirt-csi-driver:latest` and deletes a digest once `latest` moves on (the previous one already returns 404), so `image` has no default. Mirror

```
quay.io/kubevirt/kubevirt-csi-driver@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409
```

the `latest` build of 3a1a099 (image label `multi.GIT_SHA`, linux/amd64 only), into a registry both clusters can pull from, and set `image` to the mirror by digest. The fixtures use the quay.io reference above, which works only while it is `latest`.

`latest` is still that build, because upstream removed its image workflow in [#393](https://github.com/kubevirt/csi-driver/pull/393), and no published image contains a later commit. That leaves out the fix of [#397](https://github.com/kubevirt/csi-driver/pull/397). In the 3a1a099 build the controller panics in `ControllerUnpublishVolume` when a VMI outlives its VM, and the volume stays on the VMI. An image built from e13603a has the fix. Its `USER 1001` changes nothing here, because the output sets the UID of the driver container on both sides. The sidecars are pinned by tag and digest as upstream pins them at e13603a.

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

#### Snapshot controller

`snapshot_controller: true` renders the VolumeSnapshotClass, VolumeSnapshotContent and VolumeSnapshot CRDs and the snapshot-controller with its RBAC into the tenant cluster, after `client/config/crd` and `deploy/kubernetes/snapshot-controller` of [external-snapshotter v8.7.0](https://github.com/kubernetes-csi/external-snapshotter/tree/v8.7.0), the release of the csi-snapshotter sidecar. The KubeVirt CSI driver keeps copies of these files in `deploy/tenant/base`, but applies them only in its e2e setup, and they still name controller v8.6.0. The CRDs are the files in `schemas/snapshot.storage.k8s.io/crds/`, which the gate installs to check the output and the upstream workflow regenerates on a new release.

One key covers CRDs and controller, because RKE2 ships both as charts, and k3s v1.37.1+k3s1, kind v1.37.0 and kubeadm ship neither. Leave it off where a snapshot-controller already runs, since a second one in another namespace does not share its leader lease. The VolumeGroupSnapshot CRDs are not rendered, as the driver does not implement group snapshots, so the controller waits 30 seconds for them at start and then turns that feature off.

#### Prerequisites

Tenant nodes have to name their VM: providerID `kubevirt://<vm>` with the annotation `cluster.x-k8s.io/cluster-namespace`, as Cluster API Provider KubeVirt sets them, or the annotations `csi.kubevirt.io/infra-vm-name` and `csi.kubevirt.io/infra-vm-namespace`. A VolumeSnapshotClass needs the external-snapshotter CRDs and snapshot-controller in the tenant cluster, which `snapshot_controller` renders where the cluster has neither.

Plain `kubectl apply -R` on the tenant output needs two runs, or the Namespace and the `-crd` files applied first, because it applies the files in `<namespace>/` before the Namespace file and resolves the kind of every object before it creates any. Argo CD and Flux order Namespaces and CRDs before the objects that need them.

In `<namespace>/` plain `kubectl apply -R` also creates the Secret `kubevirt-csi-controller-sa-token` before its ServiceAccount `kubevirt-csi-controller-sa`, because `-sa-token-secret.yaml` sorts before `-sa.yaml`. The token controller deletes a token Secret whose ServiceAccount does not exist yet, while kubectl reports it as created. Apply `kubevirt-csi-controller-sa.yaml` first, or apply once more after the ServiceAccount exists, then check that `kubectl -n kubevirt-csi-driver get secret kubevirt-csi-controller-sa-token` finds the Secret. Argo CD and Flux apply ServiceAccounts before Secrets.

#### Defaults

| Default | Where | Reason |
|---|---|---|
| UID and GID 1001 | controller | Upstream sets the same through its `plain-kubernetes` component since [#392](https://github.com/kubevirt/csi-driver/pull/392), because the sidecar images run as root by default and do not start under `runAsNonRoot` without a UID. Its base leaves the UID unset for OpenShift, whose `restricted-v2` SCC rejects a fixed one. |
| namespace label `pod-security.kubernetes.io/enforce: privileged`, registrar and livenessprobe without capabilities and with a read-only root filesystem | node plugin | The `csi-driver` container is `privileged` and runs as UID 0, as upstream's does, for Bidirectional mount propagation into `/var/lib/kubelet` and access to the hotplugged disks in `/dev`. Only the `privileged` Pod Security level admits it. Upstream renders no Namespace and sets no security context on the sidecars. |
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
| `namespace` instead of `kube-system` | snapshot-controller | Its leader-election Role grants create, update and delete on every Lease in its namespace, which in `kube-system` includes the leader leases of kube-controller-manager and kube-scheduler. |
| image v8.7.0 | snapshot-controller | Upstream's manifest at the v8.7.0 tag still names v8.6.0, because upstream bumps it only after a release. v8.7.0 is the release of the CRDs and of csi-snapshotter. |
| `runAsNonRoot` with UID and GID 1001, seccomp `RuntimeDefault`, no capabilities, read-only root filesystem | snapshot-controller | Upstream sets no security context, and the image runs as UID 0 unless the pod sets one. 1001 is the controller's UID. |

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
        snapshot_controller: true
        storage_classes:
          kubevirt:
            default: true
            infra_storage_class: rook-ceph-block
        volume_snapshot_classes:
          kubevirt:
            infra_snapshot_class: csi-rbdplugin-snapclass
```

## Schemas

`schemas/` holds the CRD schemas of KubeVirt 1.9.1 and CDI 1.66.1, the three `snapshot.storage.k8s.io` CRDs of external-snapshotter 8.7.0 with the VolumeSnapshotClass schema, and the Kubernetes 1.37.1 schemas of the built-in kinds the CSI driver uses (all Apache-2.0); `schemas/sources.yaml` lists the pinned sources.
