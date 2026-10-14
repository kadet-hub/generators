# Changelog

## 1.0.3

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.2

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.1

Ships the upstream CRD schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).

## 1.0.0

First release on kadet-hub.
