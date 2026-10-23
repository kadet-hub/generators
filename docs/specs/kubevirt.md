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

## Implementation inventory

| Item | Value |
|---|---|
| Code | `kubevirt/csi.py` (tenant role, output keys `<namespace>/kubevirt-csi-controller-sa`, `<namespace>/kubevirt-csi-controller-sa-token-secret`) |
| Docs | `kubevirt/README.md`, section Prerequisites under CSI driver |
| Fixture | `kubevirt/tests/fixtures`, target `csi-tenant` |
