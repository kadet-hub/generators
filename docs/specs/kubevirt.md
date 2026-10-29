# kubevirt generator

Status: Draft
Code: `kubevirt/`
Verified against: feat/kubevirt-csi-snapshot-controller @ 3726e7f

## Problem and decision

The generator has shipped without a spec. This spec starts with the
documented apply order of the CSI tenant output, the first behavior that
depends on how a consumer applies the files. The rest of the generator is
described in `kubevirt/README.md` and gets requirements here when a change
touches it.

## CSI tenant output

The tenant role renders the ServiceAccount `kubevirt-csi-controller-sa` as
`<namespace>/kubevirt-csi-controller-sa.yaml` and its token Secret
`kubevirt-csi-controller-sa-token` as
`<namespace>/kubevirt-csi-controller-sa-token-secret.yaml`. `kubectl apply -R`
walks the files in byte order, and `-` sorts before `.`, so it applies the
Secret first. The token controller deletes a `kubernetes.io/service-account-token`
Secret whose ServiceAccount it cannot find, even with a live lookup
(`syncSecret` in `pkg/controller/serviceaccount/tokens_controller.go` at
Kubernetes v1.37.1). The apply still reports the Secret as created.

Renaming the output keys to change the order was rejected for the same
reason as for the Namespace and CRDs: it changes every consumer's file paths
and does not fix ordering for tools that apply differently. Argo CD and Flux
sort ServiceAccounts before Secrets (gitops-engine `sync_tasks.go`, fluxcd/pkg
`ssa/sort.go`).

- KV-1: The README MUST state that plain `kubectl apply -R` can create the
  token Secret before its ServiceAccount, that the token controller then
  deletes it, and that applying the ServiceAccount first or applying again
  once the ServiceAccount exists keeps the Secret.

  - Test: manual: on kind, `kubectl apply -R` of the two files into an
    existing namespace, then `kubectl get secret kubevirt-csi-controller-sa-token`
  - Since: #100

## CSI driver image

Upstream publishes the driver only as `quay.io/kubevirt/kubevirt-csi-driver:latest`
and deletes a digest once `latest` moves on. kadet-hub/registry copies that
image unchanged into `ghcr.io/kadet-hub/mirror/kubevirt-csi-driver`, tagged by
its source commit (registry PUB-13). Its upstream sources are referenced, not
hosted (registry DEC-16 in `docs/specs/publishing.md`).

- KV-2: Without `csi.image`, both roles MUST render the driver image
  `ghcr.io/kadet-hub/mirror/kubevirt-csi-driver:3a1a099330045754011803e3d53cd8276ff21723@sha256:44c98353e6137455d6a393ad13e04f60e10ee49fdcd00cf078f7f7084714f409`.

  `csi.image` still overrides it, for consumers who mirror into their own
  registry. The fixtures set no `image`, so `./check kubevirt` compiles
  the default.

  - Test: `./check kubevirt` (fixtures `csi-infra`, `csi-tenant`)
  - Since: this change

## CSI sidecar images

Until 1.3.2 the sidecars were pinned to the tags upstream's manifests use
at csi-driver e13603a. Those images carry known vulnerabilities with fixes
in later kubernetes-csi releases: trivy 0.76.1 counted 77 to 103 advisory
IDs per sidecar, 2 of them critical, against 17 for livenessprobe v2.20.0.
The generator now follows the kubernetes-csi releases.

- KV-4: The CSI sidecar images MUST be pinned by tag and digest, each at
  a kubernetes-csi release whose `deploy/kubernetes/rbac.yaml` grants
  nothing beyond what the tenant ClusterRole holds and which accepts every
  flag the generator passes.

  The digest is the multi-arch index digest of the tag. Each image is
  one string literal `<repository>:<tag>@sha256:<digest>`.

  - Test: manual: `diff` of `deploy/kubernetes/rbac.yaml` between the old
    and new tag, `grep` of the passed flags in the release's `cmd/`
    sources; `./check kubevirt` (fixtures `csi-infra`, `csi-tenant`)
  - Since: this change

## KubeVirt CR spec

The KubeVirt CRD marks `spec` as required (`kubevirt.io/schemas/kubevirt_v1.json`,
from KubeVirt 1.9.1), so the API server rejects a KubeVirt CR without it with
`spec: Required value`. No field inside `spec` is required, so an empty
mapping deploys the operator with its defaults. The other kinds the generator
renders always get a `spec` mapping built from their flat keys.

- KV-3: The KubeVirt CR MUST always render `spec`. Without `spec` in the
  inventory, or with `spec: null`, it MUST render `spec: {}`.

  - Test: `./check kubevirt` (fixture `minimal`, QA-7 schema check)
  - Since: this change

## Implementation inventory

| Item | Value |
|---|---|
| Code | `kubevirt/csi.py` (tenant role, output keys `<namespace>/kubevirt-csi-controller-sa`, `<namespace>/kubevirt-csi-controller-sa-token-secret`) |
| Code | `kubevirt/csi.py` (`render`, default `csi.image`) |
| Sidecar images | `kubevirt/csi.py` (`PROVISIONER`, `ATTACHER`, `SNAPSHOTTER`, `RESIZER`, `LIVENESSPROBE`, `REGISTRAR`, `SNAPSHOT_CONTROLLER`) |
| Docs | `kubevirt/README.md`, section Prerequisites under CSI driver; section Driver image |
| Fixture | `kubevirt/tests/fixtures`, targets `csi-tenant`, `csi-infra` |
| Code | `kubevirt/__init__.py` (`KubeVirt.body`, `spec` default) |
| Fixture | `kubevirt/tests/fixtures`, target `minimal` (`kubevirt_operators.kubevirt` without `spec`) |
