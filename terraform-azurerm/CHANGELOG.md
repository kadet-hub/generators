# Changelog

## 0.1.1

- Ships the hashicorp/azurerm 5.9.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/azurerm 5.9.0".

## 0.1.0

- First release: `network` (resource group, virtual network, subnets with derived prefixes, network security groups) and `storage` (storage account, private containers). Pins hashicorp/azurerm 5.9.0.
