# Terraform Google Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/terraform-google/) page.

Kapitan kadet generator that renders Terraform JSON for Google Cloud with the `hashicorp/google` provider, pinned to **8.7.0**:

- **network**: a custom-mode VPC network, its subnets with flow logs, Private Google Access and optional GKE secondary ranges, one Cloud Router and Cloud NAT per subnet region, and ingress firewall rules for IAP SSH, load balancer health checks and internal traffic
- **buckets**: Cloud Storage buckets with uniform bucket-level access, public access prevention, versioning, soft delete, lifecycle rules and IAM members

Names, CIDRs and references are derived in Python, so the output is concrete Terraform you can review. The compile fails unless every primary and secondary range is a valid IPv4 network and no two ranges in one network overlap.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/terraform-google@sha256:<digest>
        output_path: lib/terraform-google
    compile:
      - input_type: kadet
        input_paths:
          - lib/terraform-google
        output_path: terraform/
        output_type: json
```

`output_type: json` is required. Without it Kapitan writes YAML, which Terraform ignores. Run `terraform init` and `terraform plan` in `compiled/<target>/terraform/`; the provider authenticates from its usual environment (Application Default Credentials).

### Example

```yaml
parameters:
  generators:
    terraform-google:
      project: example-project
      region: europe-west3
      default_labels:
        managed-by: kapitan
      network:
        main:
          subnets:
            gke:
              region: europe-west3
              cidr: 10.20.0.0/20
              gke:
                pods: 10.32.0.0/14
                services: 10.36.0.0/20
            data:
              region: europe-west4
              cidr: 10.21.0.0/20
              secondary_ranges:
                batch: 10.24.0.0/20
          firewall:
            health_checks: true
      buckets:
        logs:
          name: example-project-logs
          location: EU
          labels:
            data-class: internal
          lifecycle_rules:
            - action:
                type: SetStorageClass
                storage_class: NEARLINE
              condition:
                age: 30
            - action:
                type: Delete
              condition:
                age: 0
                matches_prefix:
                  - tmp/
          iam:
            roles/storage.objectViewer:
              - group:platform@example.com
```

## Inventory Contract

All keys live under `parameters.generators.terraform-google`. A missing required key or an impossible value fails the compile with a `ValueError` naming the entry.

### Provider

| Key | Default | Description |
|---|---|---|
| `project` | required | Provider `project`; every resource inherits it. |
| `region` | not set | Provider `region`. |
| `default_labels` | not set | Provider `default_labels`; of the rendered resources only buckets carry labels. |

### `network.<name>`

| Key | Default | Description |
|---|---|---|
| `project` | provider project | Set on every resource of this network, for example a Shared VPC host project. |
| `routing_mode` | `GLOBAL` | `GLOBAL` or `REGIONAL`. |
| `delete_default_routes_on_create` | `false` | Deletes the default internet route; Cloud NAT egress needs it. |
| `mtu` | not set | Emitted only when set. |
| `subnets.<subnet>.region` | required | Subnet region. |
| `subnets.<subnet>.cidr` | required | Primary IPv4 range. |
| `subnets.<subnet>.private_google_access` | `true` | `private_ip_google_access`. |
| `subnets.<subnet>.flow_logs.enabled` | `true` | `false` omits `log_config`. |
| `subnets.<subnet>.flow_logs.aggregation_interval` | `INTERVAL_5_SEC` | |
| `subnets.<subnet>.flow_logs.flow_sampling` | `0.5` | |
| `subnets.<subnet>.flow_logs.metadata` | `INCLUDE_ALL_METADATA` | |
| `subnets.<subnet>.secondary_ranges` | `{}` | `<range name>: <cidr>`. |
| `subnets.<subnet>.gke` | not set | `{pods: <cidr>, services: <cidr>}` adds the secondary ranges `<subnet>-pods` and `<subnet>-services`. |
| `nat.enabled` | `true` | One router and NAT per distinct subnet region. |
| `nat.source_ranges` | `ALL_SUBNETWORKS_ALL_IP_RANGES` | Or `ALL_SUBNETWORKS_ALL_PRIMARY_IP_RANGES`. |
| `nat.log_filter` | `ERRORS_ONLY` | `ALL`, `ERRORS_ONLY` or `TRANSLATIONS_ONLY`; `null` disables NAT logging. |
| `firewall.iap_ssh` | `true` | TCP 22 from the IAP TCP forwarding range `35.235.240.0/20`. |
| `firewall.health_checks` | `false` | All TCP ports from `35.191.0.0/16`. |
| `firewall.internal` | `true` | All protocols from every primary and secondary range of the network. |

All firewall rules are `INGRESS` with priority 1000, apply to every instance in the network and log with `INCLUDE_ALL_METADATA`.

The health check rule allows only `35.191.0.0/16`, the one range Google's [health check page](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts) currently lists for Application Load Balancers, proxy Network Load Balancers and internal passthrough Network Load Balancers. The older `130.211.0.0/22` is no longer listed. External passthrough Network Load Balancers probe from additional ranges listed on that page; add your own rule for those.

A subnet without secondary ranges omits `secondary_ip_range` instead of sending an empty list. Removing the last secondary range from the inventory therefore leaves it in place in Google Cloud.

### `buckets.<key>`

| Key | Default | Description |
|---|---|---|
| `name` | the key | Globally unique bucket name. |
| `location` | required | Region, dual-region or multi-region, for example `EU`. |
| `storage_class` | `STANDARD` | |
| `uniform_bucket_level_access` | `true` | |
| `public_access_prevention` | `enforced` | |
| `versioning` | `true` | |
| `soft_delete_retention_seconds` | `604800` | Seven days; `0` disables soft delete. |
| `force_destroy` | `false` | |
| `labels` | `{}` | Merged with the provider's `default_labels`. |
| `lifecycle_rules` | `[]` | List of `{action: {type, storage_class}, condition: {...}}`, passed through as `lifecycle_rule` blocks. |
| `iam` | `{}` | `<role>: [<member>, ...]`; one `google_storage_bucket_iam_member` per role and member. |

The provider drops a lifecycle condition whose value is `0` unless the matching `send_*_if_zero` flag is set. The generator sets `send_age_if_zero`, `send_days_since_custom_time_if_zero`, `send_days_since_noncurrent_time_if_zero` and `send_num_newer_versions_if_zero` whenever `age`, `days_since_custom_time`, `days_since_noncurrent_time` or `num_newer_versions` is `0`.

## Output

| File | Content |
|---|---|
| `providers.tf.json` | `terraform` block (`required_version >= 1.5.0`, `hashicorp/google` `8.7.0`) and the `provider "google"` block. |
| `network-<name>.tf.json` | Network, subnets, routers, NATs and firewall rules; outputs `network_<name>_id`, `network_<name>_self_link`, `network_<name>_subnet_ids` (map subnet to id). |
| `bucket-<key>.tf.json` | Bucket and IAM members; outputs `bucket_<key>_name`, `bucket_<key>_url`. |

Terraform resource and output names are the inventory keys lowercased with every character outside `[a-z0-9_]` replaced by `_`, prefixed with `_` when they would start with a digit. Subnets are named `<network>_<subnet>`, routers and NATs `<network>_<region>`, firewall rules `<network>_allow_iap_ssh`, `<network>_allow_health_checks` and `<network>_allow_internal`, IAM members `<key>_<role without roles/>_<member>`. Two keys that map to the same name fail the compile. Google Cloud names are `<network>-<region>` for routers and NATs and `<network>-allow-iap-ssh`, `<network>-allow-health-checks` and `<network>-allow-internal` for firewall rules.

## Resources

| Resource | Registry docs |
|---|---|
| `google_compute_network` | [compute_network](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/compute_network) |
| `google_compute_subnetwork` | [compute_subnetwork](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/compute_subnetwork) |
| `google_compute_router` | [compute_router](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/compute_router) |
| `google_compute_router_nat` | [compute_router_nat](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/compute_router_nat) |
| `google_compute_firewall` | [compute_firewall](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/compute_firewall) |
| `google_storage_bucket` | [storage_bucket](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/storage_bucket) |
| `google_storage_bucket_iam_member` | [storage_bucket_iam](https://registry.terraform.io/providers/hashicorp/google/8.7.0/docs/resources/storage_bucket_iam) |

The network bundle follows the layout of [terraform-google-modules/network](https://github.com/terraform-google-modules/terraform-google-network) and [terraform-google-modules/cloud-nat](https://github.com/terraform-google-modules/terraform-google-cloud-nat), with Private Google Access on by default as in Cloud Foundation Fabric [net-vpc](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric/tree/master/modules/net-vpc); custom-mode networks and per-subnet Private Google Access are what Google's [VPC design guide](https://docs.cloud.google.com/architecture/best-practices-vpc-design) recommends. The bucket defaults follow Google's guidance on [uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access) and [public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention).

Resource arguments follow the provider documentation (MPL-2.0); the examples here are written for this generator.
