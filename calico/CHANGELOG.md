# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Calico 3.33.0 (Tigera operator 1.44.0). Ships the Installation, APIServer, ImageSet, Goldmane and Whisker CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7). The ImageSet schema now comes from the operator CRD instead of a CRDs catalog snapshot.
- `variant` is no longer defaulted to `Calico`; without it the operator fills in the variant it runs as.
- A `cni` block without `type` gets the operator's default for `kubernetes_provider` (`AzureVNET` for AKS, `AmazonVPC` for EKS, `GKE` for GKE, `Calico` otherwise) instead of always `Calico`.
- `calico_network.linux_dataplane` accepts `Nftables`, as the CRD does.
- Keys in a flat `cni` block that the generator does not model, such as `specVersion` or `installMode`, pass through verbatim like those in `calico_network`. Before, they were dropped. A `cni.type` from `spec.cni` now ranks above the provider default.
- New opt-in `goldmane` and `whisker` keys render the Goldmane and Whisker resources; `whisker` without `goldmane` logs a warning.
- Whisker `notifications` defaults to `Disabled` (upstream `Enabled` calls an external API for banner text); a value from the flat key or `spec` wins.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. The ImageSet fixture uses the v3.33.0 image names and digests; `calico/cni` no longer exists in that release.
