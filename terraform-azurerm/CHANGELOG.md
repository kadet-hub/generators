# Changelog

## 0.1.5

Pins hashicorp/azurerm 5.13.0 instead of 5.12.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/azurerm 5.13.0". Of the seven resource types the generator emits, the 5.13.0 release notes name only `azurerm_storage_account`. It gains the optional `smb_oauth_enabled`, which the generator does not set and which is the only difference between the two extracts. Its `customer_managed_key` check now also accepts `FileStorage` accounts on the `V2` billing model, and the generator emits `StorageV2` accounts without a customer-managed key. Of the resource sources of the seven types only `storage_account_resource.go` changes, for these two entries. Rendered output differs only in the provider version.

## 0.1.4

Pins hashicorp/azurerm 5.12.0 instead of 5.10.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/azurerm 5.12.0". The provider block and the schemas of the seven resource types the generator emits are the same in both versions, and the release notes of 5.11.0 and 5.12.0 name none of these types. Their resource sources, `storage_container_resource.go` included, change only in the copyright year, so containers still go through Azure Resource Manager. `schemas/terraform/NOTICE` no longer names the extract's version. Rendered output differs only in the provider version.

## 0.1.3

Ships the upstream licence and copyright notice of its provider schema extract: `license: MPL-2.0` in `schemas/sources.yaml` and `schemas/terraform/NOTICE`. Rendered output is unchanged.

## 0.1.2

- Pins hashicorp/azurerm 5.10.0 instead of 5.9.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/azurerm 5.10.0". The provider block and the schemas of the seven resource types the generator emits are the same in both versions. Of the 5.10.0 release notes only the `azurerm_subnet` fix for a plan difference when `service_endpoint` entries are reordered touches the output, and the generator emits at most one entry. `storage_container_resource.go` is unchanged, so containers still go through Azure Resource Manager. Rendered output differs only in the provider version.

## 0.1.1

- Ships the hashicorp/azurerm 5.9.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/azurerm 5.9.0".

## 0.1.0

- First release: `network` (resource group, virtual network, subnets with derived prefixes, network security groups) and `storage` (storage account, private containers). Pins hashicorp/azurerm 5.9.0.
