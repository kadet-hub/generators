# Changelog

## 0.1.5

Pins hashicorp/google 8.10.0 instead of 8.9.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/google 8.10.0". The extracts of both versions are the same, and the 8.10.0 release notes name none of the seven resource types the generator emits. Rendered output differs only in the provider version.

## 0.1.4

Pins hashicorp/google 8.9.0 instead of 8.7.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/google 8.9.0". Of the release notes of 8.8.0, 8.8.1 and 8.9.0, two entries touch the emitted types: `google_compute_firewall` gains the computed `firewall_id` and `google_compute_router` the computed `router_id`, which the generator does not set. Between the two extracts the `google_compute_subnetwork` descriptions of `purpose` and `role` also change, and the generator sets neither. `schemas/terraform/NOTICE` no longer names the extract's version. Rendered output differs only in the provider version.

## 0.1.3

Ships the upstream licence and copyright notice of its provider schema extract: `license: MPL-2.0` in `schemas/sources.yaml` and `schemas/terraform/NOTICE`. Rendered output is unchanged.

## 0.1.2

- Pins hashicorp/google 8.7.0 instead of 8.6.0 in `providers.tf.json` and ships its provider schema extract under `schemas/terraform/`, so the catalog shows "Built for hashicorp/google 8.7.0". The 8.7.0 release notes change none of the arguments the generator sets: the `google_compute_subnetwork` fix forces recreation on changes to `ipv6_access_type`, `ip_collection` or `external_ipv6_prefix`, which the generator does not emit. Between the two extracts the provider block gains `gemini_data_analytics_custom_endpoint` and three subnetwork IPv6 descriptions change. Rendered output differs only in the provider version.

## 0.1.1

- Ships the hashicorp/google 8.6.0 provider schema extract under `schemas/terraform/`, so the kadet-hub gate checks every argument of the output against it (QA-8) and the catalog shows "Built for hashicorp/google 8.6.0".

## 0.1.0

- First release: `network` (VPC network, subnets, Cloud Router and NAT per region, firewall rules) and `buckets` (Cloud Storage buckets with IAM members). Pins hashicorp/google 8.6.0.
