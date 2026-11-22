# talos generator

Status: As-built
Code: `talos/`
Verified against: main @ fbe8c39

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

  A set image without a tag, such as `<repository>@sha256:<digest>`, fails
  the compile as well. Its Kubernetes version is unknown, so TAL-2 has no
  tag to give the other components.

  - Test: `talos/tests/test_multidoc.py::test_component_tags_must_agree`
  - Since: #130, #134 (image without a tag)

- TAL-2: On such a node, every component image the inventory does not set
  MUST be rendered with the upstream repository of that component and the
  tag of TAL-1, also when the component has no block in the inventory.

  The block is created, so the multi-document translation writes its
  document, or the image is set in a block that stays in the v1alpha1
  document. Control plane documents are dropped on workers as before.
  The derived image carries no digest, because the generator knows the
  digest only of its own default tag (TAL-4).

  - Test: `talos/tests/test_multidoc.py::test_missing_images_take_the_tag`
  - Since: #130

- TAL-3: On a node where the inventory sets no component image, the
  rendered config MUST be unchanged against 1.1.0, apart from the default
  image values of TAL-4.

  Talos then fills every image from its own default, one version for all.

  - Test: `talos/tests/test_multidoc.py::test_no_images_unchanged`;
    `./check talos` (fixture `minimal`)
  - Since: #130

## Default images

The default images were tags: the five component images at Kubernetes
1.37.1, `constants.DefaultKubernetesVersion` of Talos 1.14.3, and the
installer at Talos 1.14.3. A tag can be moved, and both versions had fixed
releases. trivy 0.76.1 counted 28 advisory IDs in kube-apiserver v1.37.1
and 19 in v1.37.2, and the installer v1.14.5 drops the one high Go stdlib
advisory of v1.14.3. Talos 1.14.5 still names Kubernetes 1.37.1 as its
default and supports 1.37.2.

- TAL-4: The default component images and the default installer image
  MUST be pinned by tag and digest. The component images MUST be the
  newest patch release of the Kubernetes minor version Talos names as
  `constants.DefaultKubernetesVersion` at the targeted release. The
  installer MUST be the image `talosctl gen config` writes at that
  release.

  The digest is the multi-arch index digest of the tag. Each default is
  one string literal `<repository>:<tag>@sha256:<digest>`. The targeted
  release is Talos 1.14.5, so the component images are Kubernetes 1.37.2.

  - Test: `talos/tests/test_multidoc.py::test_no_images_unchanged`;
    manual: `talosctl gen config` of v1.14.5 writes the same installer
    repository and tag; `reference.ParseNormalizedNamed` of
    distribution/reference v0.6.0, which Talos' `VersionFromImageRef`
    uses, reads the tag of each default
  - Since: #134

## Raw documents

Talos 1.14 has kinds without any v1alpha1 field, such as
`FilesystemTrimConfig`, `SecurityProfileConfig` and `UserVolumeConfig`.
The generator only translates v1alpha1 keys, so a cluster config that uses
these kinds could not be rendered from the inventory. The key `documents`
in `base` and in `nodes.<name>` takes a list of such documents and passes
them through. `patches` were considered. They are separate outputs, so
neither the node config nor its userdata Secret would contain them.

- TAL-5: The entries of a node's `documents` list MUST be appended
  unchanged and in list order after the documents the generator writes
  for that node, on every node type.

  The node's list replaces the one in `base`, as every list in the
  generator does. Kapitan refs inside an entry pass through as written.
  The key never reaches the v1alpha1 document. The userdata Secret carries
  the entries, because it wraps the rendered config. The worker filter of
  control plane kinds does not apply to them, so a control plane kind on a
  worker reaches Talos, which rejects it.

  - Test: `talos/tests/test_multidoc.py::test_documents_appended`;
    `./check talos` (fixture `complete`)
  - Since: #216

- TAL-6: The compile MUST fail, naming the node and the entry, when an
  entry of `documents` lacks `apiVersion` or `kind`.

  Talos picks the document type by these two fields, and the gate's
  schema check (QA-7) skips documents without them.

  - Test: `talos/tests/test_multidoc.py::test_documents_need_apiversion_and_kind`
  - Since: #216

- TAL-7: The compile MUST fail, naming the node and the entry, when an
  entry has the `kind` and `name` of a document the generator writes for
  that node.

  Such a document is set through the inventory key the generator
  translates into it (README, Translation to Talos 1.14 documents), and a
  raw entry must not duplicate or override it unnoticed. Kinds without a
  name, such as `HostnameConfig`, collide on the kind alone. On a worker
  the entries are compared with the documents left after the worker
  filter.

  - Test: `talos/tests/test_multidoc.py::test_documents_must_not_repeat_generated`
  - Since: #216

## Service account issuer

The generator writes `KubeServiceAccountConfig` with the control plane
endpoint as `issuer.issuerURL`, and Talos derives the API server's
`--service-account-issuer` and, without `accepted.audiences`,
`--api-audiences` from it (`pkg/machinery/config/types/k8s/service_account.go`, Talos 1.14.6).
A cluster that moves its endpoint, for example from an address to a DNS
name, therefore changes both at once. The API server then rejects every
token a pod still holds, signed for the old issuer and audience, until the
kubelet renews it. Cilium, operators and webhooks lose the API in that
window. Kubernetes keeps old tokens valid when the old issuer stays in
the list of accepted issuers, and Talos takes that list as
`accepted.issuers` and the audiences as `accepted.audiences`.

The inventory sets them as `cluster.serviceAccount.accepted`, a key
without a v1alpha1 counterpart, in the shape of the document. A separate
`issuerURL` key was considered. It would let the issuer stay while the
endpoint moves, but leave the cluster on the old URL for good.

- TAL-8: `cluster.serviceAccount.accepted` MUST reach
  `KubeServiceAccountConfig` as its `accepted` field unchanged.

  `issuers` and `audiences` pass through as written. Talos replaces its
  default audience, the issuer URL, with `audiences` when that list is
  set, so a list that keeps the old URL names the new one too. Output is
  unchanged for inventories without the key.

  - Test: `talos/tests/test_multidoc.py::test_service_account_accepted`;
    `./check talos` (fixture `complete`)
  - Since: #234

- TAL-9: The compile MUST fail, naming the node, when
  `cluster.serviceAccount.accepted` is set and the generator writes no
  `KubeServiceAccountConfig` for that node's config.

  The document needs `cluster.serviceAccount.key` and
  `cluster.controlPlane.endpoint`. Without the check the key would be
  dropped without a word, and the endpoint move it was meant for would
  break the tokens after all.

  - Test: `talos/tests/test_multidoc.py::test_service_account_accepted_needs_the_document`
  - Since: #234

## Implementation inventory

| Item | Value |
|---|---|
| Code | `talos/multidoc.py` (`_component_images`, called from `split`; `IMAGES`; `append_documents`; `_cluster_docs` writes `KubeServiceAccountConfig`), `talos/__init__.py` (`DEFAULT_INSTALLER_IMAGE`; `main` takes `documents` out of the merged node config and calls `append_documents`) |
| Unit tests | `talos/tests/test_multidoc.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider talos/tests` |
| Upstream repositories | `ghcr.io/siderolabs/kubelet`, `registry.k8s.io/kube-apiserver`, `registry.k8s.io/kube-controller-manager`, `registry.k8s.io/kube-scheduler`, `registry.k8s.io/kube-proxy` |
