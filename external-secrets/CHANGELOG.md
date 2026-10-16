# Changelog

## 1.0.4

Built for External Secrets Operator 2.12.0. The SecretStore and ClusterSecretStore schemas and CRDs gain the Conjur `auth.azure`, `auth.gcp` and `auth.iam` authenticators; nothing was removed or renamed, and the ExternalSecret and ClusterExternalSecret schemas are unchanged. Provider blocks pass through as before, so the new authenticators work without a generator change. Rendered output is unchanged.

## 1.0.3

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.2

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.1

Ships the upstream CRD schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).

## 1.0.0

First release on kadet-hub.
