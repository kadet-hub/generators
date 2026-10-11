# Changelog

## 0.1.1

- Ships the hashicorp/google 8.6.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/google 8.6.0".

## 0.1.0

- First release: `network` (VPC network, subnets, Cloud Router and NAT per region, firewall rules) and `buckets` (Cloud Storage buckets with IAM members). Pins hashicorp/google 8.6.0.
