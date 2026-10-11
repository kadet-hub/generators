# kadet-hub generators

Kapitan kadet generators published on [kadet-hub](https://kadet-hub.org).

| Generator | Renders |
|---|---|
| [argocd](argocd/) ([catalog](https://kadet-hub.org/generators/argocd/)) | Argo CD Applications, ApplicationSets and AppProjects, with an in-cluster destination shorthand and one Application per target publishing a Kapitan topic |
| [certmanager](certmanager/) ([catalog](https://kadet-hub.org/generators/certmanager/)) | cert-manager Certificates, Issuers and ClusterIssuers with Let's Encrypt and CA bootstrap shorthands, and trust-manager Bundles |
| [cilium](cilium/) ([catalog](https://kadet-hub.org/generators/cilium/)) | Cilium network policies with port and DNS shorthands, LB-IPAM pools and L2 announcement policies |
| [external-secrets](external-secrets/) ([catalog](https://kadet-hub.org/generators/external-secrets/)) | External Secrets Operator SecretStores, ClusterSecretStores and ExternalSecrets |
| [keda](keda/) ([catalog](https://kadet-hub.org/generators/keda/)) | KEDA ScaledObjects, ScaledJobs and TriggerAuthentications |
| [keycloak](keycloak/) ([catalog](https://kadet-hub.org/generators/keycloak/)) | Keycloak Operator Keycloak instances, realm imports and OIDC and SAML clients, with database credential and CR reference defaults |
| [kyverno](kyverno/) ([catalog](https://kadet-hub.org/generators/kyverno/)) | Kyverno ClusterPolicies, Policies, PolicyExceptions and cleanup policies with a match_kinds shorthand |
| [linkerd](linkerd/) ([catalog](https://kadet-hub.org/generators/linkerd/)) | Linkerd Servers, AuthorizationPolicies, mTLS and network authentications, HTTPRoutes and ServiceProfiles with refs and group defaults |
| [loki](loki/) ([catalog](https://kadet-hub.org/generators/loki/)) | Loki Operator LokiStacks with storage and schema defaults, and alerting and recording rules bound to their stack |
| [multus](multus/) ([catalog](https://kadet-hub.org/generators/multus/)) | Multus CNI NetworkAttachmentDefinitions from structured CNI config, with a resource_name shorthand |
| [opentelemetry-operator](opentelemetry-operator/) ([catalog](https://kadet-hub.org/generators/opentelemetry-operator/)) | OpenTelemetry Operator collectors, Instrumentations, TargetAllocators and OpAMPBridges, with target allocator wiring |
| [prometheus-operator](prometheus-operator/) ([catalog](https://kadet-hub.org/generators/prometheus-operator/)) | Prometheus Operator Prometheus, PrometheusAgent, Alertmanager, ThanosRuler, Probe and ScrapeConfig resources with selector and storage shorthands |
| [rabbitmq](rabbitmq/) ([catalog](https://kadet-hub.org/generators/rabbitmq/)) | RabbitMQ clusters, users, permissions, vhosts, queues, exchanges, policies, federations and shovels with cluster references |
| [terraform-aws](terraform-aws/) ([catalog](https://kadet-hub.org/generators/terraform-aws/)) | Terraform JSON for AWS: VPC with derived subnets, routing and NAT, and hardened S3 buckets (hashicorp/aws 6.68.0) |
| [terraform-azurerm](terraform-azurerm/) ([catalog](https://kadet-hub.org/generators/terraform-azurerm/)) | Terraform JSON for Azure: resource group, VNet with derived subnets, NSGs and associations, and hardened storage accounts with CAF names (hashicorp/azurerm 5.9.0) |
| [terraform-google](terraform-google/) ([catalog](https://kadet-hub.org/generators/terraform-google/)) | Terraform JSON for Google Cloud: custom-mode VPC with subnets, Cloud NAT and baseline firewall, and hardened GCS buckets (hashicorp/google 8.6.0) |
| [terraform-opentelekomcloud](terraform-opentelekomcloud/) ([catalog](https://kadet-hub.org/generators/terraform-opentelekomcloud/)) | Terraform JSON for Open Telekom Cloud: VPC with derived subnets, NAT gateway and SNAT, and KMS-encrypted OBS buckets (opentelekomcloud/opentelekomcloud 1.37.10) |
| [thanos](thanos/) ([catalog](https://kadet-hub.org/generators/thanos/)) | Thanos Operator ThanosQuery, Receive, Ruler, Store and Compact sharing one object storage setting |
| [velero](velero/) ([catalog](https://kadet-hub.org/generators/velero/)) | Velero BackupStorageLocations, VolumeSnapshotLocations, Schedules, Backups and Restores |

Each directory is one generator with its own manifest (`kapitan-generator.yaml`),
changelog and fixture project under `tests/fixtures`. Releases are tagged
`<generator>-v<semver>`. To use one, pin it by digest as described in
[Using marketplace generators](https://github.com/kadet-hub/registry/blob/main/docs/consumers.md);
the registry itself is [kadet-hub/registry](https://github.com/kadet-hub/registry).

`./check <generator>` runs the gate's ruff rules and sandbox compile locally (needs docker);
the `check` workflow runs it for every generator a pull request changes.
