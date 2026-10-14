# Changelog

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Targets Rook 1.21.0 and ships its CRD schemas (`deploy/examples/crds.yaml`) under `schemas/` for QA-7, replacing the CRDs-catalog schemas of the previous repository.
- CephCluster defaults `dataDirHostPath` to `/var/lib/rook`, the value of Rook's example cluster, and fails the compile without `cephVersion.image` unless `external.enable` is set.
- CephFilesystem defaults `metadataServer` to one active MDS with an active standby, CephNFS `server.active` to 1 and CephRBDMirror `count` to 1; the CRD requires these fields.
- A `rados` flat key on CephNFS is ignored with a warning; Rook deprecated the field and overwrites it.
