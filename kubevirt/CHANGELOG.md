# Changelog

## 1.3.0

`csi.image` is optional and defaults to `ghcr.io/kadet-hub/mirror/kubevirt-csi-driver:3a1a099330045754011803e3d53cd8276ff21723@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409`, kadet-hub's unmodified copy of the quay.io `latest` build of 3a1a099. Targets that set `image` render the same output. The README's Driver image section links the image's upstream sources.

## 1.2.0

Adds `csi.snapshot_controller` for the tenant role. `true` renders the snapshot-controller of external-snapshotter v8.7.0 with its RBAC and the VolumeSnapshotClass, VolumeSnapshotContent and VolumeSnapshot CRDs, so a tenant VolumeSnapshotClass works without a separate install. The controller runs in the CSI namespace with a restricted security context. The README's CSI defaults list where it differs from upstream's manifest. On the infra role the key fails the compile. Output without the key stays the same.

The `snapshot.storage.k8s.io` schema group now names external-snapshotter 8.7.0 (`client/config/crd`) as its source instead of the KubeVirt CSI driver's copy, and adds the VolumeSnapshotContent and VolumeSnapshot CRDs. All three files are upstream's byte for byte, and the output renders them from there.

## 1.1.2

Built for the KubeVirt CSI driver at main@e13603a. Upstream now deploys what `csi` already rendered. Since kubevirt/csi-driver#392 its controller runs with the restricted security context, with UID and GID 1001 from the `plain-kubernetes` component, and the node plugin's `csi-driver` container as UID 0. Since kubevirt/csi-driver#396 it pins csi-snapshotter v8.7.0. The rendered output stays the same, and the README's CSI defaults keep only the remaining differences. The VolumeSnapshotClass CRD and schema move to e13603a, whose file is external-snapshotter's v8.7.0 CRD and differs from the shipped one only in descriptions.

The driver image is still the `latest` build of 3a1a099. Upstream removed its image workflow (kubevirt/csi-driver#393), so the controller fix of kubevirt/csi-driver#397 is in no published image.

## 1.1.1

Built for KubeVirt 1.9.1. Its CRD validations are unchanged from 1.9.0, so the shipped schemas and the rendered output stay the same. The fixtures use the `cirros-container-disk-demo:v1.9.1` image, the same digest as `v1.9.0`.

## 1.1.0

Adds `csi`, the KubeVirt CSI driver in its split deployment at upstream commit 3a1a099: `role: infra` renders the controller with its RBAC into the namespace of a tenant cluster's VMs, optionally restricted to `allowed_storage_classes` with `snapshot_classes`; `role: tenant` renders the node plugin, CSIDriver, StorageClasses, VolumeSnapshotClasses, and the ServiceAccount, RBAC and token Secret for the controller's tenant kubeconfig. `csi.image` is required, because upstream publishes only a moving `latest` tag; the README names the digest to mirror. The sidecars are pinned by tag and digest, csi-snapshotter at v8.7.0 instead of upstream's v4.2.1, which cannot create snapshots with the external-snapshotter v8 CRDs. The README's CSI defaults list where the output differs from upstream's manifests and why.

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
