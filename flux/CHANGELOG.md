# Changelog

## 1.1.0

Built for Flux 2.10.0, which pins source-controller 1.10.1, kustomize-controller 1.10.1 and helm-controller 1.7.1.

- OCIRepositories render `provider: generic` and `timeout: 60s`, and HelmRelease chart templates of kind HelmChart render `chart.spec.version: "*"` and `chart.spec.reconcileStrategy: ChartVersion`, unless the inventory sets them. The CRDs defaulted these fields until source-controller 1.9 and helm-controller 1.6. Now the controllers apply the same values to an unset field, so behaviour is unchanged and the rendered objects state the values as the stored objects did before.
- Ships the source-controller 1.10.1, kustomize-controller 1.10.1 and helm-controller 1.7.1 schemas. OCIRepository requires `interval` and `url` through CEL rules instead of `required`. GitRepository and OCIRepository gain `status.sourceVerificationFingerprint`. Kustomization and HelmRelease `kubeConfig` take exactly one of `configMapRef` and `secretRef` in one rule instead of two.
- HelmRelease `chart` gains the kind `OCIRepository`, a chart template that takes `chart.spec.url` and the other OCIRepository fields. `spec.chart` passes it through. The generator has no shorthand for it.

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub. Built for Flux 2.9.6 (source-controller 1.9.6, kustomize-controller 1.9.6, helm-controller 1.6.5); ships the CRD schemas of those releases under `schemas/`, which the kadet-hub gate validates the compiled output against (QA-7).
