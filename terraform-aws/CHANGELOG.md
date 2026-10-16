# Changelog

## 0.1.2

- Pins hashicorp/aws 6.69.1 instead of 6.68.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/aws 6.69.1". The release notes of 6.69.0 and 6.69.1 change none of the 15 resource types the generator emits; between the two extracts only the provider's `endpoints` block gains `pricingplanmanager`. Rendered output differs only in the provider version.

## 0.1.1

- Ships the hashicorp/aws 6.68.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/aws 6.68.0".

## 0.1.0

- First release: `vpc` and `s3_bucket` bundles. Pins hashicorp/aws 6.68.0.
