# Changelog

## 1.0.4

Built for Multus CNI 4.3.2. Its NetworkAttachmentDefinition CRD is unchanged, so the shipped schema and rendered output are unchanged. Multus 4.3.2 still builds with network-attachment-definition-client v1.7.6. Of the Multus files the README cites, only `docs/how-to-use.md` changes at v4.3.2, by a `--force-config-watch` section outside the cited one, and their links move to that tag.

## 1.0.3

Ships the upstream NOTICE of the schemas and CRDs it vendors in their group directory (Apache-2.0 section 4(d)). Rendered output is unchanged.

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the Multus CNI 4.3.1 NetworkAttachmentDefinition schema under `schemas/`; the kadet-hub gate validates the compiled output against it (QA-7). Fixtures set `parameters.kapitan.vars.target`.

New `resource_name` shorthand for the `k8s.v1.cni.cncf.io/resourceName` annotation that Multus uses to pass device plugin or DRA device IDs to the CNI plugin. Sources are linked in the README.
