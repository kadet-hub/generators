# talos generator

Status: Draft
Code: `talos/`
Verified against: main @ 01d9c3c

## Problem and decision

The generator has shipped without a spec. This spec starts with the
Kubernetes component images, the first behaviour where a gap in the
inventory led to a wrong config without any error. Everything else is
described in `talos/README.md` and gets requirements here when a change
touches it.

A Talos config names five Kubernetes component images: kubelet,
kube-apiserver, kube-controller-manager, kube-scheduler and kube-proxy.
Talos runs them as one Kubernetes version. Until 1.1.0, the generator
filled every component image the inventory did not set from a constant,
the Kubernetes default of the Talos release it was built for (1.37.1 at
Talos 1.14.3). A consumer that set four images to v1.36.4 and none for
kube-proxy got kube-proxy v1.37.1 in the same config. A component without
any block in the inventory had the same problem one step later: the
generator wrote no document, and Talos filled in its own default at
runtime.

The generator now derives one version per node from the images the
inventory sets and gives it to every component. Failing on every partly
set config was considered. It would break each consumer who sets only the
images they care about, and the derived version is what such a consumer
means. `talosctl gen config` behaves the same way and writes all five
images for one version.

## Kubernetes component images

- TAL-1: On a node where the inventory sets the image of at least one
  Kubernetes component, all set component images MUST have the same tag,
  or the compile MUST fail naming the node and each component with its
  tag.

  The components are `machine.kubelet`, `cluster.apiServer`,
  `cluster.controllerManager`, `cluster.scheduler` and `cluster.proxy`.
  The tag is the part after the last `:` of the image without its
  digest. The registry may differ per image, so mirrors stay possible.

  - Test: `talos/tests/test_multidoc.py::test_component_tags_must_agree`
  - Since: this change

- TAL-2: On such a node, every component image the inventory does not set
  MUST be rendered with the upstream repository of that component and the
  tag of TAL-1, also when the component has no block in the inventory.

  The block is created, so the multi-document translation writes its
  document, or the image is set in a block that stays in the v1alpha1
  document. Control plane documents are dropped on workers as before.

  - Test: `talos/tests/test_multidoc.py::test_missing_images_take_the_tag`
  - Since: this change

- TAL-3: On a node where the inventory sets no component image, the
  rendered config MUST be unchanged against 1.1.0.

  Talos then fills every image from its own default, one version for all.

  - Test: `talos/tests/test_multidoc.py::test_no_images_unchanged`;
    `./check talos` (fixture `minimal`)
  - Since: this change

## Implementation inventory

| Item | Value |
|---|---|
| Code | `talos/multidoc.py` (`_component_images`, called from `split`) |
| Unit tests | `talos/tests/test_multidoc.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider talos/tests` |
| Upstream repositories | `ghcr.io/siderolabs/kubelet`, `registry.k8s.io/kube-apiserver`, `registry.k8s.io/kube-controller-manager`, `registry.k8s.io/kube-scheduler`, `registry.k8s.io/kube-proxy` |
