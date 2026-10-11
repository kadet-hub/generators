# kadet-hub generators

Kapitan kadet generators published on [kadet-hub](https://kadet-hub.org).

| Generator | Renders |
|---|---|
| [external-secrets](external-secrets/) ([catalog](https://kadet-hub.org/generators/external-secrets/)) | External Secrets Operator SecretStores, ClusterSecretStores and ExternalSecrets |
| [keda](keda/) ([catalog](https://kadet-hub.org/generators/keda/)) | KEDA ScaledObjects, ScaledJobs and TriggerAuthentications |
| [terraform-aws](terraform-aws/) ([catalog](https://kadet-hub.org/generators/terraform-aws/)) | Terraform JSON for AWS: VPC with derived subnets, routing and NAT, and hardened S3 buckets (hashicorp/aws 6.68.0) |
| [terraform-google](terraform-google/) ([catalog](https://kadet-hub.org/generators/terraform-google/)) | Terraform JSON for Google Cloud: custom-mode VPC with subnets, Cloud NAT and baseline firewall, and hardened GCS buckets (hashicorp/google 8.6.0) |

Each directory is one generator with its own manifest (`kapitan-generator.yaml`),
changelog and fixture project under `tests/fixtures`. Releases are tagged
`<generator>-v<semver>`. To use one, pin it by digest as described in
[Using marketplace generators](https://github.com/kadet-hub/registry/blob/main/docs/consumers.md);
the registry itself is [kadet-hub/registry](https://github.com/kadet-hub/registry).
