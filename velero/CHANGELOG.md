# Changelog

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the Velero 1.18.4 CRD schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7). Fixtures set `parameters.kapitan.vars.target`.

New defaults, overridable from the inventory and documented with sources in the README:

- A BackupStorageLocation that is the only entry in `backup_storage_locations` gets `default: true`, since Velero's fallback to a location named `default` is deprecated.
- A Schedule without `template` gets `template: {}` (all namespaces). Previously the CRD rejected the output.
