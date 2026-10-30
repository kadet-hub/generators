# Changelog

## 0.1.2

Ships the upstream licence and copyright notice of its provider schema extract: `license: MPL-2.0` in `schemas/sources.yaml` and `schemas/terraform/NOTICE`. Rendered output is unchanged.

## 0.1.1

- Ships the opentelekomcloud/opentelekomcloud 1.37.10 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for opentelekomcloud/opentelekomcloud 1.37.10".

## 0.1.0

- First release: `network` (VPC, subnets, NAT gateway, EIP, SNAT rules) and `bucket` (OBS bucket with KMS key and lifecycle rule). Pins opentelekomcloud/opentelekomcloud 1.37.10.
