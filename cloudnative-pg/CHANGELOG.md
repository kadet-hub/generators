# Changelog

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub. Targets CloudNativePG 1.30.1 and the Barman Cloud Plugin 0.15.1 and ships their CRD schemas under `schemas/` for QA-7. PodMonitors come from the prometheus-operator generator; the README has the inventory snippet.
