# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the Multus CNI 4.3.1 NetworkAttachmentDefinition schema under `schemas/`; the kadet-hub gate validates the compiled output against it (QA-7). Fixtures set `parameters.kapitan.vars.target`.

New `resource_name` shorthand for the `k8s.v1.cni.cncf.io/resourceName` annotation that Multus uses to pass device plugin or DRA device IDs to the CNI plugin. Sources are linked in the README.
