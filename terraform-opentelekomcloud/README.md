# terraform-opentelekomcloud

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/terraform-opentelekomcloud/) page.

Kapitan kadet generator that renders Terraform JSON for [Open Telekom Cloud](https://www.open-telekom-cloud.com/):

- **network**: a VPC, its subnets with CIDRs derived in Python, and optionally a NAT gateway with an EIP and one SNAT rule per egress subnet
- **bucket**: a private OBS bucket with versioning, KMS server-side encryption (own key, given key or OBS default key) and a lifecycle rule

The output pins `opentelekomcloud/opentelekomcloud` **1.37.10** and needs Terraform >= 1.5.0.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/terraform-opentelekomcloud@sha256:<digest>
        output_path: lib/terraform-opentelekomcloud
    compile:
      - input_type: kadet
        input_paths:
          - lib/terraform-opentelekomcloud
        output_path: terraform/
        output_type: json
```

`output_type: json` is required: without it Kapitan writes YAML, which Terraform ignores.

The provider authenticates at plan time from its usual environment, for example `OS_USERNAME`, `OS_PASSWORD` and `OS_DOMAIN_NAME`, or `OS_ACCESS_KEY` and `OS_SECRET_KEY`. Credentials never go into the inventory or the output.

### Example

```yaml
parameters:
  generators:
    terraform-opentelekomcloud:
      tenant_name: eu-de_myproject
      region: eu-de
      network:
        platform:
          cidr: 10.20.0.0/16
          tags:
            env: prod
          subnets:
            kubernetes: {}              # 10.20.2.0/24
            database:
              cidr: 10.20.200.0/24
            jumphost:                   # 10.20.1.0/24, no internet egress
              egress: false
          nat:
            spec: "1"
            bandwidth_mbit: 200
            subnet: kubernetes
      bucket:
        tf-state:
          bucket: myproject-tf-state
          tags:
            env: prod
```

## Inventory Contract

All keys live under `parameters.generators.terraform-opentelekomcloud`.

| Key | Default | Meaning |
|---|---|---|
| `tenant_name` | required | Project name, e.g. `eu-de_myproject`. Not a secret. |
| `auth_url` | `https://iam.eu-de.otc.t-systems.com/v3` | IAM endpoint. |
| `region` | unset | Provider region. |
| `network.<name>.cidr` | required | VPC CIDR. |
| `network.<name>.tags` | `{}` | Tags on every resource of the network. |
| `network.<name>.dns` | `[100.125.4.25, 100.125.129.199]` | Subnet DNS servers. |
| `network.<name>.subnets.<subnet>` | required, at least one | One subnet; its keys below are optional. |
| `network.<name>.subnets.<subnet>.newbits` | `8` | Prefix length added to the VPC prefix. |
| `network.<name>.subnets.<subnet>.index` | position in sorted order | Which block of that size to take. |
| `network.<name>.subnets.<subnet>.cidr` | `null` | Explicit CIDR; overrides `newbits` and `index`. |
| `network.<name>.subnets.<subnet>.egress` | `true` | Add an SNAT rule for this subnet. |
| `network.<name>.nat.enabled` | `true` | Render NAT gateway, EIP and SNAT rules. |
| `network.<name>.nat.spec` | `"0"` | NAT gateway size, see below. |
| `network.<name>.nat.bandwidth_mbit` | `100` | EIP bandwidth, 1 to 300 Mbit/s. |
| `network.<name>.nat.subnet` | first subnet in sorted order | Subnet the NAT gateway attaches to. |
| `bucket.<key>.bucket` | `<key>` | Bucket name. |
| `bucket.<key>.versioning` | `true` | Object versioning. |
| `bucket.<key>.kms.create_key` | `true` | Create a KMS key `<bucket>-obs` for the bucket. |
| `bucket.<key>.kms.pending_days` | `7` | Deletion delay of the created key, 7 to 1096. |
| `bucket.<key>.kms.key_id` | `null` | Existing KMS key ID of the base project; takes precedence over `create_key`. |
| `bucket.<key>.noncurrent_expiration_days` | `90` | Expire noncurrent versions; `null` disables. |
| `bucket.<key>.abort_multipart_days` | `7` | Abort incomplete multipart uploads; `null` disables. |
| `bucket.<key>.force_destroy` | `false` | Delete all objects on `terraform destroy`. |
| `bucket.<key>.tags` | `{}` | Tags on the bucket and the created key. |

Inventory keys become Terraform resource names after lower-casing and replacing every character outside `[a-z0-9_]` with `_` (a leading digit gets a `_` prefix). Two keys that map to the same name fail the compile.

### Network

A derived subnet is block `index` of size `/<vpc prefix + newbits>` inside the VPC, so `10.0.0.0/16` with the defaults gives `10.0.0.0/24`, `10.0.1.0/24` and so on. The gateway is the first host of the subnet. The compile fails when a subnet lies outside the VPC, is longer than `/28`, overlaps another subnet or does not fit (`index` too large).

The DNS defaults are the OTC-internal resolvers ([secondary DNS release note](https://www.t-cloud-public.com/en/support/release-notes/secondary-dns)). The first entry becomes `primary_dns`, the second `secondary_dns`, and `dns_list` is set only for more than two entries. Keep the primary OTC-internal: managed services such as CCE need it.

`nat.spec` selects the [NAT gateway size](https://docs.otc.t-systems.com/nat-gateway/umn/service_overview/nat_gateway_specifications.html) by its maximum SNAT connections:

| `spec` | Size | SNAT connections |
|---|---|---|
| `"0"` | Micro ([release note](https://www.open-telekom-cloud.com/en/support/release-notes/nat-gateway-micro-flavour-is-now-available-in-eu-de-and-eu-nl)) | 1,000 |
| `"1"` | Small | 10,000 |
| `"2"` | Medium | 50,000 |
| `"3"` | Large | 200,000 |
| `"4"` | Extra-large | 1,000,000 |

The EIP is a `5_bgp` address with a dedicated (`PER`) bandwidth. SNAT rules select subnets by `network_id`, not by CIDR.

### Bucket

The bucket is always `private` and encrypted with SSE-KMS. Once versioning has been enabled, a bucket can only suspend it, never return to unversioned. The KMS key alias is `<bucket>-obs` with `.` replaced by `-`, because KMS aliases allow only letters, digits and `:/_-`. With `create_key: false` and no `key_id`, OBS uses its default master key.

Created keys live in the base project, because OBS accepts only base-project KMS keys for encryption (see the `server_side_encryption` note in the [opentelekomcloud_obs_bucket](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/obs_bucket) docs). When `tenant_name` is a sub-project such as `eu-de_myproject` and a bucket creates a key, `providers.tf.json` gets a second provider block with alias `base` and `tenant_name` set to the part before the first `_` (`eu-de`), and every KMS key uses `provider = opentelekomcloud.base`. The credentials must have KMS rights in that base project. A `tenant_name` without `_` is already the base project and gets no alias.

The lifecycle rule `default` covers the whole bucket. Its 90 and 7 days are this generator's choice, not vendor defaults.

## Output

| Input | File | Resources |
|---|---|---|
| always | `providers.tf.json` | `terraform` block (required version, provider pin) and `provider "opentelekomcloud"`, plus alias `base` for KMS keys of a sub-project tenant |
| `network.<name>` | `network-<name>.tf.json` | VPC, subnets; with NAT: NAT gateway, EIP, SNAT rules |
| `bucket.<key>` | `bucket-<key>.tf.json` | OBS bucket; KMS key when created |

Terraform outputs, with `<name>` the sanitized key:

| Output | Value |
|---|---|
| `<name>_vpc_id` | VPC ID |
| `<name>_subnet_ids` | map of subnet key to subnet ID |
| `<name>_eip_address` | NAT EIP address, only with NAT |
| `<name>_bucket_name` | bucket name |
| `<name>_kms_key_id` | KMS key ID, unless OBS uses its default key |

Resource reference (provider 1.37.10):

- [opentelekomcloud_vpc_v1](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/vpc_v1)
- [opentelekomcloud_vpc_subnet_v1](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/vpc_subnet_v1)
- [opentelekomcloud_nat_gateway_v2](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/nat_gateway_v2)
- [opentelekomcloud_vpc_eip_v1](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/vpc_eip_v1)
- [opentelekomcloud_nat_snat_rule_v2](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/nat_snat_rule_v2)
- [opentelekomcloud_kms_key_v1](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/kms_key_v1)
- [opentelekomcloud_obs_bucket](https://registry.terraform.io/providers/opentelekomcloud/opentelekomcloud/1.37.10/docs/resources/obs_bucket)

The network defaults (OTC DNS pair, gateway on the first host, NAT spec `"0"`, 100 Mbit/s `PER` bandwidth on a `5_bgp` EIP, SNAT by network ID) mirror the community modules [iits-consulting/terraform-opentelekomcloud-vpc](https://github.com/iits-consulting/terraform-opentelekomcloud-vpc) and [iits-consulting/terraform-opentelekomcloud-snat](https://github.com/iits-consulting/terraform-opentelekomcloud-snat) (MPL-2.0).

Resource arguments follow the provider documentation (MPL-2.0); the examples here are written for this generator.
