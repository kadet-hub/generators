# Changelog

## 1.1.0

`name` on any entry names its resource and its output file, which before always took the entry's key. A recipe that may write only keys of its own name can then keep a resource name, such as the Cluster `app-db` whose claims and Secrets carry its name. Two entries of a section with the same name in one namespace now fail the compile; before, the later one replaced the earlier output file. Output is unchanged for inventories without `name` and without such a collision.

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub. Targets CloudNativePG 1.30.1 and the Barman Cloud Plugin 0.15.1 and ships their CRD schemas under `schemas/` for QA-7. PodMonitors come from the prometheus-operator generator; the README has the inventory snippet.
