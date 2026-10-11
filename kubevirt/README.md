# KubeVirt Generator

Published on [kadet-hub](https://kadet-hub.org/generators/kubevirt/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kubevirt/) page.

Kapitan kadet generator for [KubeVirt](https://kubevirt.io/) and its Containerized Data Importer ([CDI](https://github.com/kubevirt/containerized-data-importer)). Built for KubeVirt 1.9.0 and CDI 1.66.1. The `v1beta1` APIs it emits need KubeVirt 1.7.0 or later: `snapshot.kubevirt.io/v1beta1` is served since 1.3.0, `clone.kubevirt.io/v1beta1` since 1.5.0 and `pool.kubevirt.io/v1beta1` since 1.7.0 (checked in `crds.go` at each release tag).

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

## Schemas

`schemas/` holds the CRD schemas of KubeVirt 1.9.0 and CDI 1.66.1 (Apache-2.0); `schemas/sources.yaml` lists the pinned sources.
