# Cilium Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/cilium/) page.

Kapitan kadet generator for [Cilium](https://cilium.io/) policy and load balancer resources. Built for Cilium 1.20.4.

- **CiliumNetworkPolicy** (`cilium.io/v2`): namespaced L3-L7 policy
- **CiliumClusterwideNetworkPolicy** (`cilium.io/v2`): cluster-scoped L3-L7 policy, also for nodes (host policies)
- **CiliumLoadBalancerIPPool** (`cilium.io/v2`): IP pool for LB-IPAM
- **CiliumL2AnnouncementPolicy** (`cilium.io/v2alpha1`): which nodes answer ARP/NDP for which Service IPs

Each kind is emitted in its storage version at Cilium 1.20.4. CiliumLoadBalancerIPPool `v2alpha1` is still served but deprecated; CiliumL2AnnouncementPolicy exists only as `v2alpha1`. The Cilium install belongs in the `helm` input with the upstream `cilium` chart.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/cilium@sha256:<digest>
        output_path: lib/cilium
    compile:
      - output_path: manifests/cilium/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/cilium
```

### Inventory Contract

All keys live under `parameters.generators.cilium`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `network_policies.<name>` | CiliumNetworkPolicy | `<namespace>/<name>-cnp` |
| `clusterwide_policies.<name>` | CiliumClusterwideNetworkPolicy | `<name>-ccnp` |
| `lb_ip_pools.<name>` | CiliumLoadBalancerIPPool | `<name>-lbippool` |
| `l2_announcement_policies.<name>` | CiliumL2AnnouncementPolicy | `<name>-l2ap` |

Every resource accepts `labels`, `annotations` and `spec`, and gets the label `name: <name>`; CiliumNetworkPolicy also accepts `namespace`. Precedence is generator defaults < `spec` < flat keys and shorthands: a flat key that overrides the same field in `spec` wins and logs a warning.

| Kind | Flat key | Renders to |
|---|---|---|
| both policies | `endpoint_selector` | `spec.endpointSelector` |
| CiliumClusterwideNetworkPolicy | `node_selector` | `spec.nodeSelector` |
| both policies | `ingress`, `egress` | `spec.ingress`, `spec.egress`, rules verbatim apart from `ports` |
| both policies | `description` | `spec.description` |
| both policies | `enable_default_deny` | `spec.enableDefaultDeny` |
| both policies | `allow_dns` | an extra `spec.egress` rule, see below |
| CiliumLoadBalancerIPPool | `blocks`, alias `cidrs` | `spec.blocks` |
| CiliumLoadBalancerIPPool | `disabled` | `spec.disabled` |
| CiliumL2AnnouncementPolicy | `node_selector`, `service_selector` | `spec.nodeSelector`, `spec.serviceSelector` |
| CiliumL2AnnouncementPolicy | `interfaces` | `spec.interfaces` |
| CiliumL2AnnouncementPolicy | `external_ips`, `load_balancer_ips` | `spec.externalIPs`, `spec.loadBalancerIPs` |

Selectors accept `match_labels` and `match_expressions` as well as the camelCase keys. A CiliumNetworkPolicy needs `endpoint_selector` (or `spec.endpointSelector`), a CiliumClusterwideNetworkPolicy `endpoint_selector` or `node_selector`; the compile fails otherwise. `endpoint_selector: {}` selects every endpoint. `node_selector` on a CiliumNetworkPolicy is dropped with a warning. Other fields, such as `ingressDeny`, `egressDeny` or the pool's `serviceSelector`, go into `spec`.

### Shorthands and defaults

| Input | Result |
|---|---|
| rule `ports: [8080, 53/UDP, http]` in `ingress`, `egress`, `ingressDeny` or `egressDeny` (also in `spec`) | one more `toPorts` entry: `{ports: [{port: "8080"}, {port: "53", protocol: UDP}, {port: http}]}` |
| `allow_dns: true` | egress rule to kube-dns on port 53 with the L7 DNS rule `matchPattern: "*"` |
| `allow_dns: [<pattern>, ...]` | the same rule, allowing only lookups that match the patterns |
| pool block `"192.0.2.0/28"` | `{cidr: 192.0.2.0/28}` |
| pool block `"198.51.100.10-198.51.100.20"` | `{start: 198.51.100.10, stop: 198.51.100.20}` |
| L2 policy without `external_ips`, `load_balancer_ips` or the same fields in `spec` | `loadBalancerIPs: true` |

The CRD types `port` as a string, so an unquoted `port: 53` in a hand-written `toPorts` fails validation; the shorthand converts numbers. A missing protocol is not emitted, Cilium reads it as `ANY` ([PortProtocol](https://github.com/cilium/cilium/blob/v1.20.4/pkg/k8s/apis/cilium.io/client/crds/v2/ciliumnetworkpolicies.yaml)).

`toFQDNs` rules only learn IPs from DNS answers that pass Cilium's DNS proxy, which needs an L7 DNS rule on the DNS traffic ([DNS based](https://docs.cilium.io/en/v1.20/security/policy/layer3/#dns-based)). `allow_dns` renders the rule from the upstream [FQDN example](https://github.com/cilium/cilium/blob/v1.20.4/examples/policies/l3/fqdn/fqdn.yaml): `toEndpoints` with `k8s:io.kubernetes.pod.namespace: kube-system` and `k8s:k8s-app: kube-dns`. It is opt-in because it adds allowed egress, and the DNS rule may already live in another policy for the same endpoints. Clusters whose DNS pods carry other labels write the rule in `egress` instead. Like every egress rule it turns on default deny for egress unless `enable_default_deny.egress` is `false`.

Both L2 announcement flags default to `false` upstream, so a policy without either announces nothing ([IP types](https://docs.cilium.io/en/v1.20/network/l2-announcements/#ip-types)). The generator sets `loadBalancerIPs: true`, the IPs that LB-IPAM assigns; `externalIPs` also needs the `externalIPs.enable` Helm value and stays off unless set. Pool block notation follows [LB-IPAM](https://docs.cilium.io/en/v1.20/network/lb-ipam/).

`enable_default_deny` is not defaulted; Cilium enables default deny for each direction that has rules.

### Example

```yaml
parameters:
  generators:
    cilium:
      namespace: shop
      network_policies:
        web:
          endpoint_selector:
            match_labels:
              app: web
          ingress:
            - fromEndpoints:
                - matchLabels:
                    k8s:io.kubernetes.pod.namespace: ingress-nginx
                    app.kubernetes.io/name: ingress-nginx
              ports: [8080]
          egress:
            - toEndpoints:
                - matchLabels:
                    app: api
              ports: [3000/TCP]
          allow_dns: true
        payments-egress:
          namespace: payments
          endpoint_selector:
            match_labels:
              app: payments
          egress:
            - toFQDNs:
                - matchName: api.payments.example.com
              ports: [443/TCP]
          allow_dns: [api.payments.example.com]
      clusterwide_policies:
        node-health-check:
          node_selector:
            match_labels:
              kubernetes.io/os: linux
          ingress:
            - fromEntities: [health]
      lb_ip_pools:
        public-pool:
          blocks:
            - 192.0.2.0/28
            - 198.51.100.10-198.51.100.20
      l2_announcement_policies:
        workers:
          node_selector:
            match_expressions:
              - key: node-role.kubernetes.io/control-plane
                operator: DoesNotExist
          interfaces: ["^eth[0-9]+"]
```

This renders `shop/web-cnp`, `payments/payments-egress-cnp`, `node-health-check-ccnp`, `public-pool-lbippool` and `workers-l2ap`. Both namespaced policies get the kube-dns egress rule; `payments-egress` allows only lookups of `api.payments.example.com`, and `workers` announces LoadBalancer IPs from every worker node.

## Schemas

`schemas/cilium.io/` holds the closed JSON Schemas of the four kinds from the Cilium 1.20.4 CRDs (Apache-2.0). The policy schemas restrict `spec.log.value` with the pattern `^\PC*$`, which Python's `re` cannot compile; validate output that sets `log` with a validator that supports Unicode property classes.
