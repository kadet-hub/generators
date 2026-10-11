# Changelog

## 0.1.1

- Ships the hashicorp/aws 6.68.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/aws 6.68.0".

## 0.1.0

- First release: `vpc` and `s3_bucket` bundles. Pins hashicorp/aws 6.68.0.
