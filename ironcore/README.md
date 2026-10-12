# IronCore Generator

Published on [kadet-hub](https://kadet-hub.org/generators/ironcore/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/ironcore/) page.

Kapitan kadet generator for [IronCore](https://github.com/ironcore-dev/ironcore) IaaS resources. Built for IronCore 0.8.0 (`v1alpha1`, the only version of these groups at that release):

| Kind | API group |
|---|---|
| Machine | `compute.ironcore.dev/v1alpha1` |
| Volume | `storage.ironcore.dev/v1alpha1` |
| Network, NetworkInterface, VirtualIP, LoadBalancer, NATGateway, NetworkPolicy | `networking.ironcore.dev/v1alpha1` |

MachineClass, MachinePool, VolumeClass, VolumePool and IPAM Prefixes are operator-managed and only referenced. Secrets for ignition and disk encryption belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/ironcore@sha256:<digest>
        output_path: lib/ironcore
    compile:
      - output_path: manifests/ironcore/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/ironcore
```

### Inventory Contract

All keys live under `parameters.generators.ironcore`. The namespace resolves per resource: `namespace` on the resource, then `generators.ironcore.namespace`, then `parameters.namespace`, then `default`.

| Key | Kind | Output file |
|---|---|---|
| `networks.<name>` | Network | `<namespace>/<name>-network.yaml` |
| `network_interfaces.<name>` | NetworkInterface | `<namespace>/<name>-nic.yaml` |
| `virtual_ips.<name>` | VirtualIP | `<namespace>/<name>-vip.yaml` |
| `volumes.<name>` | Volume | `<namespace>/<name>-volume.yaml` |
| `machines.<name>` | Machine | `<namespace>/<name>-machine.yaml` |
| `load_balancers.<name>` | LoadBalancer | `<namespace>/<name>-lb.yaml` |
| `nat_gateways.<name>` | NATGateway | `<namespace>/<name>-natgw.yaml` |
| `network_policies.<name>` | NetworkPolicy | `<namespace>/<name>-netpol.yaml` |

Every resource accepts `namespace`, `labels`, `annotations` and `spec`. Precedence is generator defaults < `spec` < flat keys; a flat key that overrides a `spec` value logs `Flat key '<key>' overrides spec passthrough '<field>' for resource '<name>'`.

Flat keys are the snake_case spelling of the `spec` fields; the camelCase spelling is accepted too. Values nested inside them use the API's camelCase field names.

| Kind | Flat keys |
|---|---|
| Network | `peerings`, `provider_id` |
| NetworkInterface | `network_ref`, `ip_families`, `ips`, `prefixes`, `virtual_ip`, `provider_id`, `attributes` |
| VirtualIP | `type`, `ip_family` |
| LoadBalancer | `type`, `ip_families`, `network_ref`, `ips`, `network_interface_selector`, `ports` |
| NATGateway | `type`, `ip_family`, `network_ref`, `ports_per_network_interface` |
| NetworkPolicy | `network_ref`, `network_interface_selector`, `ingress`, `egress`, `policy_types` |
| Volume | `volume_class_ref`, `volume_pool_ref`, `volume_pool_selector`, `resources`, `data_source`, `encryption`, `unclaimable`, `tolerations` |
| Machine | `machine_class_ref`, `machine_pool_ref`, `machine_pool_selector`, `power`, `network_interfaces`, `volumes`, `ignition_ref`, `efi_vars`, `tolerations` |

Shorthands (a dict passes through unchanged, for example `networkRef: {name: x, namespace: y}`; other keys of peerings, ports and Machine attachments stay verbatim):

| Input | Result |
|---|---|
| `*_ref: <name>` (network, class, pool) | `{name: <name>}` |
| `ips: [10.0.0.10]`, `prefixes: [10.0.0.0/24]` | `[{value: ...}]` |
| `ignition_ref: <name>` | `ignitionRef: {name: <name>}`; a dict keeps `key` |
| peering `networkRef: <name>` | `networkRef: {name: <name>}` |
| `encryption: <secret>` | `encryption: {secretRef: {name: <secret>}}` |
| `data_source: {osImage: <image>}` | `dataSource: {osImage: {image: <image>}}` |
| `data_source: {volumeSnapshotRef: <name>}` | `dataSource: {volumeSnapshotRef: {name: <name>}}` |
| Machine `network_interfaces[].networkInterfaceRef`, `volumes[].volumeRef: <name>` | `{name: <name>}` |
| Machine `power: true/false` (YAML 1.1 `On`/`Off`) | `power: On`/`Off` |

Defaults and derived values:

| Field | Value | Why |
|---|---|---|
| VirtualIP, NATGateway `type` | `Public` | Required and the only supported type ([VirtualIP](https://github.com/ironcore-dev/ironcore/blob/v0.8.0/internal/apis/networking/validation/virtualip.go), [NATGateway](https://github.com/ironcore-dev/ironcore/blob/v0.8.0/internal/apis/networking/validation/natgateway.go) validation). |
| NetworkInterface, LoadBalancer `ipFamilies` | one family per entry of `ips`: the family of a `value`, else the prefix template's `ipFamily`; the compile fails if neither is set | The API server derives it the same way ([defaulting](https://github.com/ironcore-dev/ironcore/blob/v0.8.0/internal/apis/networking/v1alpha1/defaults.go)), but the OpenAPI schema marks it required, so the gate's schema check needs it in the output. |

Required inputs without a default: LoadBalancer `type` (`Public` exposes the selected interfaces to the internet, so choose `Public` or `Internal`), VirtualIP and NATGateway `ip_family`, LoadBalancer `ip_families` when it has no `ips`, and NetworkInterface `ips` (an ephemeral IP needs a parent Prefix only the operator knows). Without them the schema check fails. A VirtualIP is bound to an interface through the NetworkInterface's `virtual_ip: {virtualIPRef: <name>}`; `targetRef` needs the interface UID, which is unknown at compile time. NetworkPolicy `policyTypes`, NATGateway `portsPerNetworkInterface`, Machine `power` and volume `device` are left to the API server, which derives `policyTypes` from `ingress`/`egress`, defaults the others and assigns `od*` device names. A default-deny policy without rules needs `policy_types` set explicitly.

### Example

```yaml
parameters:
  generators:
    ironcore:
      namespace: production
      networks:
        main-net: {}
      network_interfaces:
        web-01:
          network_ref: main-net
          ips:
            - 10.0.1.10
            - "2001:db8::10"
          labels:
            role: web
      volumes:
        web-01-root:
          volume_class_ref: fast
          resources:
            storage: 20Gi
          data_source:
            osImage: registry.example.com/os-images/ubuntu:24.04
      machines:
        web-01:
          machine_class_ref: x1-medium
          network_interfaces:
            - name: primary
              networkInterfaceRef: web-01
          volumes:
            - name: root
              volumeRef: web-01-root
          ignition_ref:
            name: web-01-ignition
            key: ignition.json
      load_balancers:
        web:
          type: Public
          ip_families:
            - IPv4
          network_ref: main-net
          network_interface_selector:
            matchLabels:
              role: web
          ports:
            - port: 443
              protocol: TCP
      nat_gateways:
        egress:
          ip_family: IPv4
          network_ref: main-net
      network_policies:
        web-ingress:
          network_ref: main-net
          network_interface_selector:
            matchLabels:
              role: web
          ingress:
            - ports:
                - port: 443
                  protocol: TCP
```

## Schemas

IronCore serves these kinds through an aggregated API server, not CRDs. The schemas under `schemas/` come from the generated OpenAPI v3 documents in `gen/v3/` at IronCore v0.8.0 (Apache-2.0); see `schemas/sources.yaml`.
