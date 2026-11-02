# Changelog

## 0.1.3

Pins opentelekomcloud/opentelekomcloud 1.37.11 instead of 1.37.10 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for opentelekomcloud/opentelekomcloud 1.37.11". The extracts of both versions are the same, and the 1.37.11 release notes name none of the seven resource types the generator emits. `schemas/terraform/NOTICE` no longer names the extract's version. Rendered output differs only in the provider version.

## 0.1.2

Ships the upstream licence and copyright notice of its provider schema extract: `license: MPL-2.0` in `schemas/sources.yaml` and `schemas/terraform/NOTICE`. Rendered output is unchanged.

## 0.1.1

- Ships the opentelekomcloud/opentelekomcloud 1.37.10 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for opentelekomcloud/opentelekomcloud 1.37.10".

## 0.1.0

- First release: `network` (VPC, subnets, NAT gateway, EIP, SNAT rules) and `bucket` (OBS bucket with KMS key and lifecycle rule). Pins opentelekomcloud/opentelekomcloud 1.37.10.
