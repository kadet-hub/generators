# Terraform azurerm Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/terraform-azurerm/) page.

Kapitan kadet generator that renders Terraform JSON (`*.tf.json`) for the Azure provider [`hashicorp/azurerm`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs), pinned to **5.10.0**:

- **network**: a resource group, a virtual network, one subnet per entry with its prefix derived from the address space, and per subnet a network security group with its association.
- **storage**: a storage account locked down to Microsoft Entra ID and private access, plus private blob containers.

Names follow the [Cloud Adoption Framework naming convention](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming) with the [recommended abbreviations](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations). Subnet prefixes are computed at compile time, so the compiled output shows every CIDR.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/terraform-azurerm@sha256:<digest>
        output_path: lib/terraform-azurerm
    compile:
      - output_path: terraform/
        input_type: kadet
        output_type: json
        input_paths:
          - lib/terraform-azurerm
```

`output_type: json` is required: without it Kapitan writes YAML, which Terraform ignores. Run `terraform init` and `terraform plan` in the compiled `terraform/` directory.

### Provider and authentication

`providers.tf.json` holds the only `terraform` block (`required_version >= 1.5.0`, `hashicorp/azurerm` `5.10.0`) and the `provider "azurerm"` block with an empty `features` block. It sets `storage_use_azuread = true` when any storage account keeps `shared_access_key_enabled: false`, because the provider otherwise uses Shared Key for storage data plane requests.

The output contains no `subscription_id` and no credentials. Since provider 4.0 the subscription is required for `plan` and `apply`; set `ARM_SUBSCRIPTION_ID` (or select a default subscription in the `az` CLI) and authenticate the way the provider documents. `terraform validate` does not need it.

### Inventory Contract

All keys live under `parameters.generators.terraform-azurerm`. `network` and `storage` are maps from a key to one bundle. The key, mapped to `[a-z0-9_]`, names the output file and the Terraform resources (`azurerm_subnet.<network>_<subnet>`, `azurerm_storage_container.<storage>_<container>`). Compilation fails when two entries map to the same Terraform name or the same storage account name.

`network.<key>`:

| Key | Default | Meaning |
|---|---|---|
| `workload` | required | Workload component of the names |
| `environment` | required | Environment component, for example `prod` |
| `location` | required | Azure region, for example `westeurope` |
| `location_short` | `location` | Region component of the names, for example `weu` |
| `instance` | `"001"` | Instance component; quote it, YAML reads `001` as the number 1 |
| `address_space` | required | One IPv4 CIDR for the virtual network |
| `tags` | `{}` | Tags on the resource group, virtual network and network security groups |
| `subnets` | required | Ordered map of subnet name to the settings below |

`network.<key>.subnets.<name>`:

| Key | Default | Meaning |
|---|---|---|
| `newbits` | required unless `prefix` | Bits added to the address space prefix length; `newbits: 8` on a `/16` gives a `/24` |
| `prefix` | `null` | Explicit CIDR; overrides `newbits` |
| `nsg` | `true` | Create a network security group and associate it with the subnet |
| `security_rules` | `[]` | [`security_rule`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/network_security_group#security_rule) objects with the provider's argument names; `name`, `priority`, `direction`, `access` and `protocol` are required, omitted arguments are sent as `null`. Needs `nsg: true` |
| `default_outbound_access_enabled` | `false` | `false` makes the subnet private |
| `private_endpoint_network_policies` | `"Enabled"` | `Disabled`, `Enabled`, `NetworkSecurityGroupEnabled` or `RouteTableEnabled` |

Prefix derivation: explicit prefixes are reserved first. Then, in the order the subnets appear in the inventory, each `newbits` subnet gets the first aligned block of its size that overlaps no subnet allocated so far. Appending a `newbits` subnet keeps the existing prefixes; inserting one earlier, reordering, or adding an explicit prefix that overlaps a derived one moves derived prefixes, which replaces those subnets. Compilation fails for subnets smaller than `/29`, prefixes outside the address space, overlapping prefixes, and when no free block of the requested size is left. Resources are emitted sorted by name.

The network security group always carries `security_rule`, an empty list when no rules are given, so rules added outside Terraform are removed on the next apply.

`storage.<key>`:

| Key | Default | Meaning |
|---|---|---|
| `workload`, `environment`, `location` | required | As for `network` |
| `location_short` | `location` | As for `network` |
| `instance` | `"001"` | As for `network` |
| `resource_group` | | Key under `network`; the account goes into that network's resource group |
| `resource_group_name` | | Name of an existing resource group; set exactly one of the two |
| `account_replication_type` | `"ZRS"` | `LRS`, `GRS`, `RAGRS`, `ZRS`, `GZRS` or `RAGZRS` |
| `public_network_access` | `"Disabled"` | `Enabled`, `Disabled` or `SecuredByPerimeter` |
| `shared_access_key_enabled` | `false` | `false` allows only Microsoft Entra ID authorization |
| `infrastructure_encryption_enabled` | `false` | Changing it replaces the account |
| `versioning_enabled` | `true` | Blob versioning |
| `delete_retention_days` | `7` | Blob soft delete, 1 to 365 days |
| `container_delete_retention_days` | `7` | Container soft delete, 1 to 365 days |
| `ip_rules` | `[]` | Public IPv4 addresses or CIDRs the firewall admits; a single address without prefix, CIDRs up to `/30`; ranges that include RFC 1918 addresses are rejected |
| `allowed_subnets` | `[]` | Subnet names of the `resource_group` network the firewall admits; those subnets get the `Microsoft.Storage` service endpoint, which covers accounts in the virtual network's region. Not allowed with `resource_group_name` |
| `containers` | `[]` | Names of private blob containers |
| `tags` | `{}` | Tags on the storage account |

Fixed storage account arguments: `account_tier = "Standard"`, `account_kind = "StorageV2"`, `https_traffic_only_enabled = true`, `min_tls_version = "TLS1_2"`, `allow_nested_items_to_be_public = false`, `default_to_oauth_authentication = true`, `cross_tenant_replication_enabled = false`, `local_user_enabled = false`, `network_rules { default_action = "Deny", bypass = ["AzureServices"], ip_rules, virtual_network_subnet_ids }`. Containers use `container_access_type = "private"`.

`network_rules` always carries `ip_rules` and `virtual_network_subnet_ids`, as empty lists when unset, because the provider documentation requires one of them whenever the block is present. The firewall governs the public endpoint, so both lists only admit traffic with `public_network_access: Enabled`.

### Names

| Resource | Name |
|---|---|
| Resource group | `rg-<workload>-<environment>-<location_short>-<instance>` |
| Virtual network | `vnet-<workload>-<environment>-<location_short>-<instance>` |
| Subnet | `snet-<subnet>-<workload>-<environment>-<location_short>-<instance>` |
| Network security group | `nsg-<subnet>-<workload>-<environment>-<location_short>-<instance>` |
| Storage account | `st<workload><environment><location_short><instance>`, lowercased, hyphens and other characters removed |

Storage account names are globally unique and limited to 3 to 24 characters; a longer derived name fails the compilation with a message. Set `location_short` to keep it short.

### Output files

| File | Content |
|---|---|
| `providers.tf.json` | `terraform` block with `required_providers`, `provider "azurerm"` |
| `network-<key>.tf.json` | Resource group, virtual network, subnets, network security groups and associations; outputs `<key>_resource_group_name`, `<key>_virtual_network_id`, `<key>_subnet_ids` (map of subnet name to ID) |
| `storage-<key>.tf.json` | Storage account and containers; outputs `<key>_storage_account_id`, `<key>_storage_account_name` |

### Example

```yaml
parameters:
  generators:
    terraform-azurerm:
      network:
        shop:
          workload: shop
          environment: prod
          location: westeurope
          location_short: weu
          address_space: 10.40.0.0/16
          tags:
            owner: shop-team
          subnets:
            web:
              newbits: 8
              security_rules:
                - name: allow-https-inbound
                  priority: 100
                  direction: Inbound
                  access: Allow
                  protocol: Tcp
                  source_port_range: "*"
                  destination_port_range: "443"
                  source_address_prefix: Internet
                  destination_address_prefix: VirtualNetwork
            app:
              newbits: 8
            endpoints:
              prefix: 10.40.255.0/27
              nsg: false
      storage:
        shop:
          workload: shop
          environment: prod
          location: westeurope
          location_short: weu
          resource_group: shop
          containers:
            - invoices
            - uploads
```

This compiles to `rg-shop-prod-weu-001`, `vnet-shop-prod-weu-001` with `snet-web-shop-prod-weu-001` (`10.40.0.0/24`), `snet-app-shop-prod-weu-001` (`10.40.1.0/24`) and `snet-endpoints-shop-prod-weu-001` (`10.40.255.0/27`), network security groups for `web` and `app`, and the storage account `stshopprodweu001` with two containers.

## Defaults and guidance

The subnet defaults (private subnets, `private_endpoint_network_policies = "Enabled"`), the required security rule arguments and the storage account defaults (ZRS, no public network access, no Shared Key, no local users, HTTPS only, TLS 1.2, no anonymous nested access, no cross-tenant replication, firewall default `Deny` with the `AzureServices` bypass) mirror the Azure Verified Modules [avm-res-network-virtualnetwork](https://github.com/Azure/terraform-azurerm-avm-res-network-virtualnetwork), [avm-res-network-networksecuritygroup](https://github.com/Azure/terraform-azurerm-avm-res-network-networksecuritygroup) and [avm-res-storage-storageaccount](https://github.com/Azure/terraform-azurerm-avm-res-storage-storageaccount). Blob and container soft delete and Microsoft Entra ID authorization in the portal (`default_to_oauth_authentication`) follow Microsoft's [security recommendations for Blob storage](https://learn.microsoft.com/en-us/azure/storage/blobs/security-recommendations). Blob versioning is this generator's default.

- **Private subnets**: Microsoft recommends disabling [default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access). Virtual machines in a private subnet need an explicit egress method to reach the internet, typically a NAT gateway; this version does not render one.
- **No public network access**: with `public_network_access: Disabled` the account is reachable only through a private endpoint or by trusted Azure services. This version renders no private endpoints.
- **Containers through Azure Resource Manager**: containers reference the account by `storage_account_id`, which the provider (5.10.0 source) creates, updates and deletes through the Resource Manager API instead of the storage data plane, so this should work while public network access is disabled. Not verified by an apply.

## Terraform resources

Resource arguments follow the provider documentation (MPL-2.0); the examples here are written for this generator.

- [`azurerm_resource_group`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/resource_group)
- [`azurerm_virtual_network`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/virtual_network)
- [`azurerm_subnet`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/subnet)
- [`azurerm_network_security_group`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/network_security_group)
- [`azurerm_subnet_network_security_group_association`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/subnet_network_security_group_association)
- [`azurerm_storage_account`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/storage_account)
- [`azurerm_storage_container`](https://registry.terraform.io/providers/hashicorp/azurerm/5.10.0/docs/resources/storage_container)

Subnets are standalone `azurerm_subnet` resources; the virtual network never carries inline `subnet` blocks, which would conflict with them.
