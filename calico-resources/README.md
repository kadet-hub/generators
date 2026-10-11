# Calico Resources Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/calico-resources/) page.

Kapitan kadet generator for the Calico day-2 resources in `projectcalico.org/v3`. Built for Calico 3.33.0.

- **NetworkPolicy**: namespaced policy for workload endpoints
- **GlobalNetworkPolicy**: cluster-wide policy, also for host endpoints
- **NetworkSet**, **GlobalNetworkSet**: labelled lists of CIDRs that policy selectors can match
- **IPPool**: an additional IP pool
- **BGPPeer**, **BGPConfiguration**: BGP peerings and the cluster or per-node BGP settings

At Calico 3.33.0 all seven kinds are served and stored as `v3` by the native CRDs in `v3_projectcalico_org.yaml`; none is deprecated. Clusters that still use the `crd.projectcalico.org/v1` CRDs accept the same documents through the Calico API server (`api_server` in the `calico` generator). The Calico install itself, including the default IP pool, belongs in the `calico` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/calico-resources@sha256:<digest>
        output_path: lib/calico-resources
    compile:
      - output_path: manifests/calico-resources/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/calico-resources
```

### Inventory Contract

All keys live under `parameters.generators.calico_resources`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `network_policies.<name>` | NetworkPolicy | `<namespace>/<name>-np` |
| `global_network_policies.<name>` | GlobalNetworkPolicy | `<name>-gnp` |
| `network_sets.<name>` | NetworkSet | `<namespace>/<name>-netset` |
| `global_network_sets.<name>` | GlobalNetworkSet | `<name>-gnetset` |
| `ip_pools.<name>` | IPPool | `<name>-ippool` |
| `bgp_peers.<name>` | BGPPeer | `<name>-bgppeer` |
| `bgp_configurations.<name>` | BGPConfiguration | `<name>-bgpconfig` |

Every resource accepts `labels`, `annotations` and `spec`, and gets the label `name: <name>`; NetworkPolicy and NetworkSet also accept `namespace`. Network sets are matched by their `labels`. Precedence is generator defaults < `spec` < flat keys and shorthands: a flat key that overrides the same field in `spec` wins and logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields; values pass through unchanged apart from the shorthands below:

| Kind | Flat keys |
|---|---|
| NetworkPolicy | `selector`, `service_account_selector`, `order`, `tier`, `types`, `ingress`, `egress`, `performance_hints` |
| GlobalNetworkPolicy | the NetworkPolicy keys and `namespace_selector`, `apply_on_forward`, `pre_dnat`, `do_not_track` |
| NetworkSet, GlobalNetworkSet | `nets` |
| IPPool | `cidr`, `block_size`, `ipip_mode`, `vxlan_mode`, `nat_outgoing`, `node_selector`, `namespace_selector`, `allowed_uses`, `assignment_mode`, `disabled`, `disable_bgp_export` |
| BGPPeer | `peer_ip`, `as_number`, `node`, `node_selector`, `peer_selector`, `local_as_number`, `password`, `source_address`, `next_hop_mode`, `keepalive_time`, `max_restart_time`, `reachable_by`, `ttl_security`, `filters` |
| BGPConfiguration | `as_number`, `node_to_node_mesh_enabled`, `listen_port`, `log_severity_screen`, `service_cluster_ips`, `service_external_ips`, `service_load_balancer_ips`, `communities`, `prefix_advertisements`, `bind_mode` |

Rules in `ingress` and `egress` are written in CRD casing. Other fields go into `spec`.

### Shorthands

| Input | Result |
|---|---|
| any selector field as a map, `{app: web, tier: api}` (spec level and in a rule's `source` or `destination`) | `app == 'web' && tier == 'api'`, keys sorted |
| rule `ports: [8080, "8443:8445", http]` | `protocol: TCP` and `destination.ports: [8080, "8443:8445", http]` |
| rule `ports: [53/UDP, 53/TCP]` | two rules, one per protocol, otherwise identical |

Selector strings pass through unchanged, so expressions such as `has(k)`, `in {...}` or `all()` stay available ([selectors](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#selectors)). Calico requires `protocol` on any rule that matches ports (Rule.protocol in the CRD); `ports` uses the rule's `protocol` and otherwise TCP. Calico rules carry one protocol each, so mixed protocols become one rule per protocol, the same split the upstream [default deny example](https://docs.tigera.io/calico/3.33/network-policy/get-started/kubernetes-default-deny) uses for DNS. Numeric strings become integers, ranges and named ports stay strings ([ports](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#ports)).

An empty selector map and an empty `ports` list fail the compile. Calico treats an empty match field as unset ([empty match fields](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#empty-match-fields)), so a rule with `selector: {}` or `ports: []` would match every peer or port. Write `all()` to select everything on purpose.

### Defaults

The generator adds no rule, policy or networking setting on its own:

- No allow policy is rendered unless written. `types` and `tier` are left to Calico's admission policies, which set `types` from the rules present and `tier` to `default`.
- IPPool `ipipMode` and `vxlanMode` default to `Never` and `natOutgoing` to `false` upstream. An extra pool without `nat_outgoing: true` therefore does not masquerade, unlike the operator's default pool. Encapsulation and NAT change how traffic leaves the node and are rendered only when set; `blockSize` and `allowedUses` are left to admission.
- BGP settings are rendered only when set. A `BGPConfiguration` named `default` applies to the whole cluster, `node.<node name>` to one node ([BGPConfiguration](https://docs.tigera.io/calico/3.33/reference/resources/bgpconfig)); `node_to_node_mesh_enabled: false` removes the full mesh and needs BGPPeers to keep routes.

### Example

```yaml
parameters:
  generators:
    calico_resources:
      namespace: shop
      network_policies:
        api:
          selector:
            app: api
          ingress:
            - action: Allow
              source:
                selector:
                  app: web
              ports: [3000]
          egress:
            - action: Allow
              destination:
                selector: role == 'partner'
              ports: [443]
      global_network_policies:
        deny-app-policy:
          namespace_selector: kubernetes.io/metadata.name not in {"calico-system", "kube-public", "kube-system", "tigera-operator"}
          types: [Ingress, Egress]
          egress:
            - action: Allow
              destination:
                selector:
                  k8s-app: kube-dns
              ports: [53/UDP, 53/TCP]
      network_sets:
        partner-api:
          labels:
            role: partner
          nets:
            - 198.51.100.0/24
      bgp_peers:
        rack1-tor:
          peer_ip: 192.0.2.1
          as_number: 64513
          node_selector:
            rack: rack1
```

This renders `shop/api-np`, `deny-app-policy-gnp`, `shop/partner-api-netset` and `rack1-tor-bgppeer`. `deny-app-policy` is the upstream global default deny for application namespaces with DNS to kube-dns allowed; `api` then allows its own traffic, including egress to the partner network set.

## Schemas

`schemas/projectcalico.org/` holds the closed JSON Schemas of the seven kinds from the Calico 3.33.0 `v3_projectcalico_org.yaml` CRDs (Apache-2.0). The CRDs' CEL rules, for example that an IPPool CIDR is strictly masked or that `node` and `nodeSelector` exclude each other, are checked by the API server, not by QA-7.
