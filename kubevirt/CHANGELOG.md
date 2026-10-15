# Changelog

## 1.1.0

Adds `csi`, the KubeVirt CSI driver in its split deployment at upstream commit 3a1a099: `role: infra` renders the controller with its RBAC into the namespace of a tenant cluster's VMs, optionally restricted to `allowed_storage_classes` with `snapshot_classes`; `role: tenant` renders the node plugin, CSIDriver, StorageClasses, VolumeSnapshotClasses, and the ServiceAccount, RBAC and token Secret for the controller's tenant kubeconfig. `csi.image` is required, because upstream publishes only a moving `latest` tag; the README names the digest to mirror. The sidecars are pinned by tag and digest. The README's CSI defaults list where the output differs from upstream's manifests and why.

Ships the VolumeSnapshotClass CRD and schema of the CSI driver and the Kubernetes 1.37.1 schemas of the built-in kinds it renders.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the CRD schemas of KubeVirt 1.9.0 and CDI 1.66.1 under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).

Changes against the last kapitan-generators release:

- Precedence is generator defaults < `spec` < flat keys for every kind. `spec` without `spec_strategy` is now merged over the defaults instead of replacing the generated spec, and flat keys override `spec` with a warning. `spec_strategy: replace` only drops the generator defaults.
- Breaking: no default `runStrategy: Always` for VirtualMachines and pool templates any more; the compile fails unless `run_strategy`, `spec.runStrategy` or the deprecated `running` is set. To keep the old behaviour add `run_strategy: Always` to each entry.
- Breaking: no default machine type `q35` any more; KubeVirt takes it from its cluster configuration. To restore it add `machine_type: q35` to each entry.
- ObjectTransfer is emitted without `metadata.namespace` and under `<name>-ot`, as the kind is cluster-scoped; `namespace` still defaults the source namespace.
- VirtualMachinePool, VirtualMachineClone, VirtualMachineSnapshot and VirtualMachineRestore are emitted as `v1beta1`, the storage version in KubeVirt 1.9.0 (`v1alpha1` is still served); this needs KubeVirt 1.7.0 or later.
- The KubeVirt CR gets `metadata.namespace: kubevirt` unless `namespace` is set; it was emitted without a namespace although the CRD is namespaced.
- The pool anti-affinity default matches `app.kubernetes.io/instance`; the former `kubevirt.io/vmPoolName` label is not set by KubeVirt 1.9.0.
- Pool CPU and memory defaults are skipped when an `instancetype` is set, and an explicit pool `machine`/`machine_type` is kept.
- CD-ROM disks no longer get the virtio bus, which KubeVirt rejects for them.
- DataSource `source.pvc.namespace` defaults to the DataSource namespace, as the CRD requires it.
