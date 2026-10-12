# kadet-hub generators

Kapitan kadet generators published on [kadet-hub](https://kadet-hub.org).

| Generator | Renders |
|---|---|
| [argocd](argocd/) ([catalog](https://kadet-hub.org/generators/argocd/)) | Argo CD Applications, ApplicationSets and AppProjects, with an in-cluster destination shorthand and one Application per target publishing a Kapitan topic |
| [calico](calico/) ([catalog](https://kadet-hub.org/generators/calico/)) | Tigera operator Installation, APIServer, ImageSet, and opt-in Goldmane and Whisker, with provider-aware CNI defaults; Calico projectcalico.org/v3 network policies, network sets, IP pools and BGP resources, with selector and port shorthands |
| [certmanager](certmanager/) ([catalog](https://kadet-hub.org/generators/certmanager/)) | cert-manager Certificates, Issuers and ClusterIssuers with Let's Encrypt and CA bootstrap shorthands, and trust-manager Bundles |
| [cilium](cilium/) ([catalog](https://kadet-hub.org/generators/cilium/)) | Cilium network policies with port and DNS shorthands, LB-IPAM pools and L2 announcement policies |
| [external-secrets](external-secrets/) ([catalog](https://kadet-hub.org/generators/external-secrets/)) | External Secrets Operator SecretStores, ClusterSecretStores and ExternalSecrets |
| [grafana](grafana/) ([catalog](https://kadet-hub.org/generators/grafana/)) | Grafana Operator instances, dashboards, folders, datasources, alert rules, contact points, notification policies and more, with instance selector defaults |
| [k3d](k3d/) ([catalog](https://kadet-hub.org/generators/k3d/)) | k3d cluster configs (k3d.io/v1alpha5 Simple) with port, volume, env and registry shorthands |
| [keda](keda/) ([catalog](https://kadet-hub.org/generators/keda/)) | KEDA ScaledObjects, ScaledJobs and TriggerAuthentications |
| [keycloak](keycloak/) ([catalog](https://kadet-hub.org/generators/keycloak/)) | Keycloak Operator Keycloak instances, realm imports and OIDC and SAML clients, with database credential and CR reference defaults |
| [kind](kind/) ([catalog](https://kadet-hub.org/generators/kind/)) | kind cluster configs (kind.x-k8s.io/v1alpha4), with kindest/node images pinned by digest from `kubernetes_version` |
| [kmcp](kmcp/) ([catalog](https://kadet-hub.org/generators/kmcp/)) | kmcp MCPServers (kagent.dev/v1alpha1) with the transport and target-port defaults the controller requires, and secret refs for env |
| [kubevirt](kubevirt/) ([catalog](https://kadet-hub.org/generators/kubevirt/)) | KubeVirt VirtualMachines, pools, snapshots, clones and the KubeVirt CR, and CDI DataVolumes and DataSources |
| [kyverno](kyverno/) ([catalog](https://kadet-hub.org/generators/kyverno/)) | Kyverno ClusterPolicies, Policies, PolicyExceptions and cleanup policies with a match_kinds shorthand |
| [linkerd](linkerd/) ([catalog](https://kadet-hub.org/generators/linkerd/)) | Linkerd Servers, AuthorizationPolicies, mTLS and network authentications, HTTPRoutes and ServiceProfiles with refs and group defaults |
| [loki](loki/) ([catalog](https://kadet-hub.org/generators/loki/)) | Loki Operator LokiStacks with storage and schema defaults, and alerting and recording rules bound to their stack |
| [multus](multus/) ([catalog](https://kadet-hub.org/generators/multus/)) | Multus CNI NetworkAttachmentDefinitions from structured CNI config, with a resource_name shorthand |
| [opentelemetry-operator](opentelemetry-operator/) ([catalog](https://kadet-hub.org/generators/opentelemetry-operator/)) | OpenTelemetry Operator collectors, Instrumentations, TargetAllocators and OpAMPBridges, with target allocator wiring |
| [prometheus-operator](prometheus-operator/) ([catalog](https://kadet-hub.org/generators/prometheus-operator/)) | Every Prometheus Operator CRD kube-prometheus-stack installs: Prometheus, PrometheusAgent, Alertmanager, ThanosRuler, ServiceMonitors, PodMonitors, PrometheusRules, Probes and ScrapeConfigs, with selector, port and storage shorthands and a kube-prometheus-stack release label |
| [rabbitmq](rabbitmq/) ([catalog](https://kadet-hub.org/generators/rabbitmq/)) | RabbitMQ clusters, users, permissions, vhosts, queues, exchanges, policies, federations and shovels with cluster references |
| [talos](talos/) ([catalog](https://kadet-hub.org/generators/talos/)) | Talos Linux 1.14 machine configs in the multi-document form, per node with control-plane and worker variants, and KubeVirt userdata Secrets |
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

## Upstream updates

The `upstream` workflow runs `tools/upstream.py` every Monday at 03:00 UTC and on
dispatch. It compares each `schemas/sources.yaml` entry with the latest upstream
release, opens or updates a pull request on `upstream/<generator>` for the groups
whose schemas regenerate and pass `./check`, and an issue
`[upstream] <generator>: <software> <version>` for the rest
([spec](docs/specs/upstream.md)).
`GH_TOKEN=$(gh auth token) uv run --with pyyaml python3 tools/upstream.py --dry-run`
prints what it would open without writing anything.

The workflow needs a kadet-hub GitHub App installed on this repository with read
and write access to contents, pull requests and issues. Its client ID and private
key are the repository secrets `APP_CLIENT_ID` and `APP_PRIVATE_KEY`.
