# Changelog

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub. Built for Flux 2.9.6 (source-controller 1.9.6, kustomize-controller 1.9.6, helm-controller 1.6.5); ships the CRD schemas of those releases under `schemas/`, which the kadet-hub gate validates the compiled output against (QA-7).
