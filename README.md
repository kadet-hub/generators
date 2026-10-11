# kadet-hub generators

Kapitan kadet generators published on [kadet-hub](https://kadet-hub.org).

| Generator | Renders |
|---|---|
| [external-secrets](external-secrets/) ([catalog](https://kadet-hub.org/generators/external-secrets/)) | External Secrets Operator SecretStores, ClusterSecretStores and ExternalSecrets |
| [keda](keda/) ([catalog](https://kadet-hub.org/generators/keda/)) | KEDA ScaledObjects, ScaledJobs and TriggerAuthentications |
| [terraform-azurerm](terraform-azurerm/) ([catalog](https://kadet-hub.org/generators/terraform-azurerm/)) | Terraform JSON for Azure: resource group, VNet with derived subnets, NSGs and associations, and hardened storage accounts with CAF names (hashicorp/azurerm 5.9.0) |

Each directory is one generator with its own manifest (`kapitan-generator.yaml`),
changelog and fixture project under `tests/fixtures`. Releases are tagged
`<generator>-v<semver>`. To use one, pin it by digest as described in
[Using marketplace generators](https://github.com/kadet-hub/registry/blob/main/docs/consumers.md);
the registry itself is [kadet-hub/registry](https://github.com/kadet-hub/registry).
