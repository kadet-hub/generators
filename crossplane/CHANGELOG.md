# Changelog

## 1.0.2

Ships the NOTICE of provider-upjet-aws with the `aws.m.upbound.io` schemas and CRDs it vendors, in their group directory. Rendered output is unchanged.

## 1.0.1

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.0

First release on kadet-hub. Renders Crossplane v2 Providers, Functions, CompositeResourceDefinitions (`apiextensions.crossplane.io/v2`), Compositions and ProviderConfigs; ships the CRD schemas of Crossplane 2.4.2 and of the `aws.m.upbound.io` ProviderConfigs of Crossplane Provider AWS 2.9.0 for QA-7. Claims are not rendered, since v2 XRDs do not support them.
