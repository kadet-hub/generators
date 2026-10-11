# terraform-aws Generator

Published on kadet-hub ([catalog](https://kadet-hub.org/generators/terraform-aws/)): pin a released version by digest from its catalog page.

Kapitan kadet generator that renders a Terraform root module in [JSON syntax](https://developer.hashicorp.com/terraform/language/syntax/json) for AWS, pinned to `hashicorp/aws` **6.68.0**:

- **`vpc`**: a VPC with a public and a private subnet per Availability Zone, route tables, an internet gateway, optional NAT gateways and a default security group without rules. Subnet CIDRs are computed at compile time, so the compiled files and the plan show concrete ranges.
- **`s3_bucket`**: a bucket with Block Public Access, ACLs disabled, default encryption, versioning and a bucket policy that denies requests without TLS.

Run `terraform init` and `terraform plan` in the compiled directory. Credentials are not part of the inventory or the output; the provider reads them from its usual environment at plan time.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/terraform-aws@sha256:<digest>
        output_path: lib/terraform-aws
    compile:
      - input_type: kadet
        input_paths:
          - lib/terraform-aws
        output_path: terraform/
        output_type: json
```

`output_type: json` is required. Without it Kapitan writes YAML, which Terraform ignores. Every output key ends in `.tf`, so Kapitan writes `*.tf.json` files.

### Example

```yaml
parameters:
  generators:
    terraform-aws:
      region: eu-central-1
      default_tags:
        Environment: production
      vpc:
        prod:
          cidr: 10.10.0.0/16
          azs: [eu-central-1a, eu-central-1b, eu-central-1c]
          nat: per_az
          tags:
            Team: platform
      s3_bucket:
        audit-logs:
          bucket: example-audit-logs-eu-central-1
          kms_key_arn: arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000
```

With the subnet defaults, `prod` gets public subnets 10.10.0.0/24 to 10.10.2.0/24 and private subnets 10.10.100.0/24 to 10.10.102.0/24, one NAT gateway with an Elastic IP in each public subnet, and one private route table per AZ.

## Inventory Contract

All keys live under `parameters.generators.terraform-aws`. Unknown keys and values of the wrong type fail the compile.

| Key | Default | Effect |
|---|---|---|
| `region` | required | `provider.aws.region` |
| `default_tags` | none | `provider.aws.default_tags.tags` |
| `vpc.<name>` | | one VPC bundle, file `network-<name>.tf.json` |
| `s3_bucket.<name>` | | one bucket bundle, file `bucket-<name>.tf.json` |

Bundle names must match `[a-z][a-z0-9_-]*`. With `-` replaced by `_` they become the Terraform resource names (`<n>` below). Two names that map to the same Terraform address fail the compile.

### `vpc`

| Key | Default | Effect |
|---|---|---|
| `cidr` | required | IPv4 VPC CIDR, /16 to /28 |
| `azs` | required | list of Availability Zone names; one public and one private subnet each |
| `subnet_newbits` | `8` | bits added to the VPC prefix for each subnet (/16 + 8 = /24) |
| `public_offset` | `0` | public subnet *i* is subnet number `public_offset + i` of the VPC CIDR |
| `private_offset` | `100` | private subnet *i* is subnet number `private_offset + i` |
| `public_subnets` | `true` | public subnets, public route table with 0.0.0.0/0 to the internet gateway |
| `nat` | `none` | `none`, `single`, `per_az` or `regional`, see below |
| `enable_dns_hostnames` | `true` | VPC attribute |
| `enable_dns_support` | `true` | VPC attribute |
| `lock_default_sg` | `true` | adopt the VPC's default security group and remove all its rules |
| `tags` | `{}` | added to every resource of the bundle; the generator sets `Name`, and `Tier` (`public` or `private`) on subnets |

Subnet numbering matches Terraform's `cidrsubnet(cidr, subnet_newbits, index)`. The compile fails if an index does not fit into the VPC CIDR, if the subnets would be smaller than /28, or if the public and private ranges overlap. Subnets never map public IPs on launch.

| `nat` | NAT resources | Private route tables |
|---|---|---|
| `none` | none | one shared, no default route |
| `single` | one Elastic IP and NAT gateway in the first public subnet | one shared, 0.0.0.0/0 to that NAT gateway |
| `per_az` | one Elastic IP and NAT gateway per public subnet | one per AZ, 0.0.0.0/0 to the NAT gateway in the same AZ |
| `regional` | one regional NAT gateway (`availability_mode = "regional"`, addresses managed by AWS) | one shared, 0.0.0.0/0 to the regional NAT gateway |

`single` and `per_az` need `public_subnets: true`. `regional` works without public subnets, but the internet gateway is still emitted: AWS creates a route table for a [regional NAT gateway](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateways-regional.html) with a default route to the VPC's internet gateway.

The default `none` creates nothing that is billed per hour. AWS recommends a NAT gateway in each Availability Zone, because resources in other AZs lose internet access when the AZ of a shared NAT gateway is down ([NAT gateway basics](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-basics.html)). `per_az` and `regional` follow that; `single` trades it for cost.

### `s3_bucket`

| Key | Default | Effect |
|---|---|---|
| `bucket` | required | bucket name, checked against the S3 naming rules (3 to 63 characters, lowercase letters, digits, `.` and `-`) |
| `versioning` | `true` | versioning status `Enabled`; `false` emits no versioning resource |
| `kms_key_arn` | `null` | `null`: SSE-S3 (`AES256`); a key ARN: SSE-KMS with that key and S3 Bucket Keys enabled |
| `deny_insecure_transport` | `true` | bucket policy denying `s3:*` on the bucket and its objects when `aws:SecureTransport` is `false` |
| `force_destroy` | `false` | let `terraform destroy` delete a bucket that still holds objects |
| `tags` | `{}` | bucket tags |

Changing `versioning` from `true` to `false` on an existing bucket destroys the versioning resource, which suspends versioning; S3 keeps the existing object versions.

## Output

| File | Content |
|---|---|
| `providers.tf.json` | the only `terraform` block: `required_version = ">= 1.5.0"`, `hashicorp/aws` pinned to `6.68.0`; the `aws` provider block |
| `network-<name>.tf.json` | resources of `vpc.<name>`; outputs `<n>_vpc_id`, `<n>_public_subnet_ids`, `<n>_private_subnet_ids` |
| `bucket-<name>.tf.json` | resources of `s3_bucket.<name>`; outputs `<n>_bucket_id`, `<n>_bucket_arn` |

Resources of a `vpc` bundle; `<i>` is the index in `azs`. `single` uses index 0, so switching from `single` to `per_az` keeps the existing NAT gateway.

| Resource | Terraform name | Emitted |
|---|---|---|
| [aws_vpc](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/vpc) | `<n>` | always |
| [aws_internet_gateway](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/internet_gateway) | `<n>` | `public_subnets: true` or `nat: regional` |
| [aws_subnet](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/subnet) | `<n>_public_<i>`, `<n>_private_<i>` | per AZ; public ones with `public_subnets: true` |
| [aws_route_table](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/route_table) | `<n>_public`, `<n>_private` or `<n>_private_<i>` | per AZ for `nat: per_az`, otherwise one private table |
| [aws_route](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/route) | `<n>_public_internet`, `<n>_private_nat`, `<n>_private_nat_<i>` | 0.0.0.0/0 to the internet gateway or NAT gateway |
| [aws_route_table_association](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/route_table_association) | `<n>_public_<i>`, `<n>_private_<i>` | one per subnet |
| [aws_eip](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/eip) | `<n>_nat_<i>` | `nat: single` or `per_az` |
| [aws_nat_gateway](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/nat_gateway) | `<n>_<i>`, `<n>_regional` | `nat` other than `none` |
| [aws_default_security_group](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/default_security_group) | `<n>` | `lock_default_sg: true` |

Resources of an `s3_bucket` bundle, all named `<n>`:

| Resource | Emitted |
|---|---|
| [aws_s3_bucket](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket) | always |
| [aws_s3_bucket_public_access_block](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket_public_access_block) | always, all four settings `true` |
| [aws_s3_bucket_ownership_controls](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket_ownership_controls) | always, `BucketOwnerEnforced` |
| [aws_s3_bucket_versioning](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket_versioning) | `versioning: true` |
| [aws_s3_bucket_server_side_encryption_configuration](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket_server_side_encryption_configuration) | always |
| [aws_s3_bucket_policy](https://registry.terraform.io/providers/hashicorp/aws/6.68.0/docs/resources/s3_bucket_policy) | `deny_insecure_transport: true`, after the public access block |

## Defaults

The `vpc` defaults follow [terraform-aws-modules/vpc](https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws): DNS hostnames and DNS support enabled, no public IPs on launch, the default security group adopted without rules, NAT off, and `Name` tags of the form `<name>-<tier>-<az>`.

For `s3_bucket`, the public access block and object ownership values match [terraform-aws-modules/s3-bucket](https://registry.terraform.io/modules/terraform-aws-modules/s3-bucket/aws). Versioning and the TLS-only policy, which the module leaves off, are on by default here, following the [Amazon S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html).

Resource arguments follow the provider documentation (MPL-2.0); the examples here are written for this generator.
