# Changelog

## 0.1.3

Ships the upstream licence and copyright notice of its provider schema extract: `license: MPL-2.0` in `schemas/sources.yaml` and `schemas/terraform/NOTICE`. Rendered output is unchanged.

## 0.1.2

- Pins hashicorp/azurerm 5.10.0 instead of 5.9.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/azurerm 5.10.0". The provider block and the schemas of the seven resource types the generator emits are the same in both versions. Of the 5.10.0 release notes only the `azurerm_subnet` fix for a plan difference when `service_endpoint` entries are reordered touches the output, and the generator emits at most one entry. `storage_container_resource.go` is unchanged, so containers still go through Azure Resource Manager. Rendered output differs only in the provider version.

## 0.1.1

- Ships the hashicorp/azurerm 5.9.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/azurerm 5.9.0".

## 0.1.0

- First release: `network` (resource group, virtual network, subnets with derived prefixes, network security groups) and `storage` (storage account, private containers). Pins hashicorp/azurerm 5.9.0.
