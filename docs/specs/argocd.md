# argocd generator

Status: Draft
Code: `argocd/`, `conftest.py`
Verified against: main @ d2acfd0

## Problem and decision

The argocd generator had no spec. Its behaviour is described in
`argocd/README.md` and the CHANGELOG. This spec starts with the
installation of Argo CD itself and the Kapitan config management plugin.
Other behaviour moves in here when a change touches it.

Up to 1.0.4 the generator renders Applications, ApplicationSets and
AppProjects, and its README leaves the installation to Kapitan's `helm`
input. A config management plugin (CMP) lets Argo CD run `kapitan compile`
itself: a sidecar of the `argocd-repo-server` Deployment runs Argo CD's
`argocd-cmp-server` and the plugin's command, configured by a
`plugin.yaml` file. The `argocd-cmp` example in kadet-hub/examples (EX-24
there) installs Argo CD from its release manifest and adds that sidecar
with a strategic merge patch and a ConfigMap, applied by its `check`
script on kind. A project that compiles its Argo CD with Kapitan had no
way to render the same.

DEC-1: The generator renders Argo CD's release manifest
`manifests/install.yaml`, vendored at the release its schemas are built
for, and does not compose Argo CD from inventory keys. The manifest is
what Argo CD's own installation guide applies, and a reviewer can compare
the vendored file with upstream by checksum. cert-manager, cloudnative-pg
and kyverno render custom resources only and leave their operators to
upstream manifests or charts. The one installation a generator here
renders is kubevirt's CSI driver, composed in `kubevirt/csi.py`. This
generator takes its image pinning (IMG-1) but not the composition,
because Argo CD's manifest has 56 objects besides its CRDs and changes
with every release. The rejected options are in
[Alternatives](#alternatives).

## Installation

`generators.argocd.install` turns the installation on. The key counts
when it is a mapping, `install: {}` included, as calico's `goldmane` and
`whisker` do. `install: null` lets a target drop a class's installation.

The manifest of Argo CD 3.5.6 holds 59 documents: the CRDs of
Application, ApplicationSet and AppProject first, then 56 others. The
three CRDs are the files the generator already ships in
`schemas/argoproj.io/crds/` for QA-11 and QA-12 of the registry gate.
Loaded with PyYAML, each CRD document of `install.yaml` 3.5.6 equals its
shipped file, keys in the same order. The generator renders the CRDs from
those files, so the 1.39 MB ApplicationSet CRD exists once in the tree.
The other 56 documents are vendored in `argocd/manifests/install.yaml`:
the upstream file from the line after its third `---` to the end, byte for
byte. The whole upstream file is 1.9 MB, above the 1 MiB file limit of the
gate's SEC-5.

- ACD-1: With `install` set to a mapping, the generator MUST render every
  document of `install.yaml` of the release in `INSTALL_VERSION`, each to
  `install/<metadata.name>-<kind in lower case>`. Without `install`, or
  with `install: null`, it MUST render none of them, and the output of an
  inventory without `install` MUST stay byte-identical to 1.0.4.

  One file per document lets the mutate generator patch an object by kind
  and name. The `install/` directory holds only the installation, so it
  can be applied first, or synced by an Application of its own, apart from
  the Applications the same target renders.

  - Test: `argocd/tests/test_install.py::test_install_is_upstream`,
    `::test_no_install_renders_as_before`; fixture target `install`;
    `manual:` Kapitan 0.36.3 compiles fixture targets `minimal` and
    `complete` to the same output as 1.0.4, with both inventory backends
  - Since: this change

- ACD-2: A rendered document MUST equal its upstream document except in
  three places: a namespaced object gets `metadata.namespace`, a
  ServiceAccount subject of a ClusterRoleBinding gets the namespace in
  place of `argocd`, and every container and init container image gets
  its pinned digest. A document of a kind the generator does not list as
  namespaced or cluster-scoped, and an image without a pin, MUST fail the
  compile.

  The namespace is `generators.argocd.namespace`, `argocd` if unset, the
  default the Applications already use. Upstream's manifest sets no
  namespace on its objects and expects `kubectl apply -n`. Its three
  ClusterRoleBindings name their subjects in `argocd`, which kustomize's
  namespace transformer rewrites in the same way. The images are
  `quay.io/argoproj/argocd`, `ghcr.io/dexidp/dex` and
  `public.ecr.aws/docker/library/redis` at the tags of the manifest, each
  pinned by tag and digest as IMG-1 of [images.md](images.md) requires for
  default images. A newer manifest with another kind or another tag fails
  until the generator lists it.

  The installation renders no Namespace, as upstream's manifest has none.
  Settings such as `argocd-cm` data, replicas or a mirror registry go in
  with the mutate generator on the compile entry's output. The generator
  has no keys for them.

  - Test: `argocd/tests/test_install.py::test_install_is_upstream`,
    `::test_install_namespace`, `::test_unknown_kind_fails`,
    `::test_image_without_pin_fails`; fixture target `install`
  - Since: this change

- ACD-3: The compile with `install` MUST fail when the SHA-256 of
  `argocd/manifests/install.yaml` differs from `INSTALL_SHA256`, or when
  `INSTALL_VERSION` differs from the `version` of the `argoproj.io` entry
  in `schemas/sources.yaml`.

  The first condition ties the vendored file to the pin that names its
  upstream source, so an edit to it cannot pass without a new pin. The
  second keeps the CRDs, which `tools/upstream.py` regenerates, at the
  release of the rest of the manifest, which it does not regenerate. An
  Argo CD release that the upstream workflow proposes therefore fails
  `./check` on fixture target `install`, and the workflow opens an issue
  instead of a pull request (UPD-4). The maintainer then vendors the new
  manifest with the commands in the implementation inventory. Before this
  change the workflow opened a pull request for such a release (#66,
  #115).

  - Test: `argocd/tests/test_install.py::test_edited_manifest_fails`,
    `::test_version_mismatch_fails`; `manual:` the commands in the
    implementation inventory reproduce `argocd/manifests/install.yaml`
    from upstream and verify both checksums
  - Since: this change

DEC-2: The release manifest stays as upstream wrote it, apart from the
namespace and the image digests of ACD-2. The generator does not model
Argo CD's settings. The mutate generator already patches rendered output
by kind and name and fails when a patch matches nothing, which covers
`argocd-cm` and the other ConfigMaps without a second set of keys here.

The manifest grants the application controller and the server `*` on
every resource of every API group, through ClusterRoles. That matches the
`rbac-admin` capability of the gate's SEC-12, so the manifest declares
`output_capabilities: [rbac-admin]`. Only inventories with `install`
render such a rule.

## Kapitan config management plugin

`install.cmp` adds the plugin. Like `install`, it counts when it is a
mapping, and `null` drops it. Its container, volumes and `plugin.yaml`
are those of EX-24, which kadet-hub/examples tests on kind with Argo CD
3.6.1.

- ACD-4: With `install.cmp` set to a mapping, the generator MUST render
  the ConfigMap `kapitan-plugin` with the key `plugin.yaml`, and MUST add
  to the `argocd-repo-server` Deployment the container `kapitan` and the
  volumes `kapitan-plugin` (that ConfigMap) and `kapitan-tmp` (an
  `emptyDir`). Without `install.cmp` the Deployment MUST be upstream's.

  The container runs `/var/run/argocd/argocd-cmp-server`, which the repo
  server's init container copies into the volume `var-files`, as user 999
  with a read-only root filesystem, no privilege escalation, every
  capability dropped and the `RuntimeDefault` seccomp profile. It mounts
  `var-files`, `plugins` (the socket the repo server talks to),
  `plugin.yaml` from the ConfigMap and its own `/tmp`. The plugin has no
  `discover` section, so it renders only Applications that name it.

  - Test: `argocd/tests/test_install.py::test_cmp_golden` against
    `argocd/tests/golden/install-cmp.yaml`; fixture target `install-cmp`;
    `manual:` kind run of the implementation inventory
  - Since: this change

- ACD-5: `install.cmp.image` MUST be an image reference pinned by digest,
  `<repository>[:<tag>]@sha256:<64 hex digits>`. Any other value MUST fail
  the compile. Without it the container MUST run `KAPITAN_IMAGE`.

  The sidecar runs the code of every repository it renders, so the image
  must not change under a tag. `KAPITAN_IMAGE` is Kapitan 0.36.3, the
  release the generator's manifest requires and EX-24 runs.

  - Test: `argocd/tests/test_install.py::test_cmp_image_by_digest`,
    `::test_cmp_image_without_digest_fails`
  - Since: this change

- ACD-6: `install.cmp.resources` MUST become the container's `resources`
  unchanged. Without it the container MUST have no `resources`, as
  upstream's repo server container has none.
  - Test: `argocd/tests/test_install.py::test_cmp_resources`
  - Since: this change

- ACD-7: With `install.cmp` the compile MUST fail unless the pod template
  of `argocd-repo-server` sets `automountServiceAccountToken: false`.

  The sidecar shares the pod's service account. Upstream's manifest turns
  the token off for the whole pod, and the sidecar mounts none of its own,
  so the plugin has no identity to read or change cluster objects with.
  The generator checks the field and does not set it: a release that
  turns the token on for the repo server fails the compile instead of
  losing it silently.

  - Test: `argocd/tests/test_install.py::test_cmp_needs_pod_without_token`;
    `manual:` kind run of the implementation inventory, where the sidecar
    finds no `/var/run/secrets/kubernetes.io`
  - Since: this change

- ACD-8: A value of `install` or `install.cmp` that is neither a mapping
  nor `null`, a key under `install` other than `cmp`, and a key under
  `install.cmp` other than `image` and `resources` MUST fail the compile.

  A mistyped `image` would otherwise run the default image without a
  message, and `install: true` would read as turned on.

  - Test: `argocd/tests/test_install.py::test_unknown_keys_fail`
  - Since: this change

DEC-3: The Application selects the target, through its plugin env
`TARGET`, as in EX-24. The plugin compiles `$ARGOCD_ENV_TARGET`, prints
every YAML file below `compiled/<target>` and fails when there is none,
so an Application with automated prune never gets an empty desired state.
Without `TARGET` the command fails on the unset variable. One repo server
renders every Application, so a target under `install.cmp` would be the
same for all of them. An Application entry of this generator sets
`TARGET` through its `source`, which passes through unchanged.

## Verification

This repository's CI runs `./check` per changed generator and no
cluster. `./check` compiles the fixtures in the gate's sandbox and
dry-runs the output on kube-apiserver v1.37.1 (QA-10, QA-11): the
installation's built-in kinds, the CRDs, and the Applications against the
shipped CRDs. That is the CI proof for fixture targets `install` and
`install-cmp`. That Argo CD comes up, that the sidecar starts and finds
no token, and that the plugin renders, was shown once by hand on kind
(implementation inventory) and is not repeated in CI.

## Alternatives

| Option | Not taken because |
|---|---|
| A generator section that composes Argo CD's Deployments, Services and RBAC | It would re-implement 56 objects upstream maintains, drift from them with each release, and leave no file to compare with upstream |
| Argo CD's community Helm chart (argoproj/argo-helm) | Users can render it with Kapitan's `helm` input today. Inside this generator it would need `helm` as a declared binary and the chart as a declared chart, and its defaults are not the release manifest's |
| `install.yaml` vendored whole | 1.9 MB, above SEC-5's 1 MiB, and a second copy of the CRDs already shipped |
| Upstream's image tags without digests | IMG-1 requires default images by tag and digest |
| `tools/upstream.py` vendors the manifest on a new release | A change to shared tooling beyond this generator; OQ-1 |
| The generator sets `automountServiceAccountToken: false` | Would hide an upstream change to the repo server's token (ACD-7) |
| A target under `install.cmp` | One repo server serves every Application (DEC-3) |

## Open questions

- OQ-1: Should `tools/upstream.py` vendor `install.yaml` and pin the
  images of a new Argo CD release, so that the release comes as a pull
  request again? Until then each one is an issue (ACD-3).

## Implementation inventory

| Item | Value |
|---|---|
| Installation, plugin | `argocd/install.py` (`render`, ACD-1 to ACD-8), called from `main` in `argocd/__init__.py` |
| Pins | `argocd/install.py`: `INSTALL_VERSION` 3.5.6, `INSTALL_SOURCE` (`manifests/install.yaml` at commit `c2b1e3017e2cec86b122172e861dcd026453ae44`, tag v3.5.6), upstream SHA-256 `846c644bc81ce5557dd9048757a9c7353378f25c5eb811c77d32a9e907823599`, `INSTALL_SHA256` `da75c759694b305f80d4e860fc5ea03fa8eefb1db12fc387d719bae52d9fa054`, `INSTALL_IMAGES`, `KAPITAN_IMAGE` |
| Vendoring | `curl -fsSLo install.yaml <INSTALL_SOURCE>`, then `sha256sum install.yaml` gives the upstream SHA-256, and `awk 'f; /^---$/ && ++n == 3 {f = 1}' install.yaml > argocd/manifests/install.yaml` writes the vendored file; image digests from `skopeo inspect --raw docker://<image> \| sha256sum` |
| CRDs | `argocd/schemas/argoproj.io/crds/` (QA-12), regenerated by `tools/upstream.py` |
| Golden | `argocd/tests/golden/install-cmp.yaml` (ACD-4); the case without plugin compares with `argocd/manifests/install.yaml` itself |
| Unit tests | `argocd/tests/test_install.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider argocd/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `argocd/tests/fixtures`, targets `minimal`, `complete`, `install` and `install-cmp` |
| kind run | 2026-11-05, `kindest/node:v1.37.0`: `kubectl apply --server-side` of `install/` of fixture target `install-cmp` into namespace `argocd`; every Deployment and the StatefulSet ready; the sidecar runs as uid 999 and has no `/var/run/secrets/kubernetes.io`; an Application with plugin `kapitan` and `TARGET` `smoke`, a target that renders an AppProject with this generator from a Gitea in the cluster, Synced and Healthy with source type `Plugin` 17 s after it was created. The script is not part of this repository |
