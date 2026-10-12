# Calico Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/calico/) page.

Kapitan kadet generator for the [Tigera operator](https://github.com/tigera/operator) resources that install and configure Calico. Built for Calico 3.33.0 (Tigera operator 1.44.0).

- **Installation** (`operator.tigera.io/v1`): Calico networking, CNI, IP pools and control plane settings
- **APIServer** (`operator.tigera.io/v1`): the Calico API server
- **ImageSet** (`operator.tigera.io/v1`): Calico images pinned by digest
- **Goldmane** (`operator.tigera.io/v1`): the flow aggregator
- **Whisker** (`operator.tigera.io/v1`): the flow log UI, which reads from Goldmane
- **NetworkPolicy**, **GlobalNetworkPolicy** (`projectcalico.org/v3`): policy for workload and host endpoints
- **NetworkSet**, **GlobalNetworkSet** (`projectcalico.org/v3`): labelled lists of CIDRs that policy selectors can match
- **IPPool** (`projectcalico.org/v3`): an additional IP pool
- **BGPPeer**, **BGPConfiguration** (`projectcalico.org/v3`): BGP peerings and the cluster or per-node BGP settings

The five operator kinds are cluster-scoped and exist only as `v1`, the served storage version at operator 1.44.0. The operator itself and its CRDs come from the upstream `tigera-operator.yaml` manifest or the `tigera-operator` Helm chart. At Calico 3.33.0 the seven `projectcalico.org` kinds are served and stored as `v3` by the native CRDs in `v3_projectcalico_org.yaml`; none is deprecated. Clusters that still use the `crd.projectcalico.org/v1` CRDs accept the same documents through the Calico API server (`api_server`).

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/calico@sha256:<digest>
        output_path: lib/calico
    compile:
      - output_path: manifests/calico/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/calico
```

### Inventory Contract

All keys live under `parameters.generators.calico`.

| Key | Kind | Output key |
|---|---|---|
| `installation` | Installation, always rendered | `<name>-installation` |
| `api_server` | APIServer, rendered when the key is present (`api_server: {}` is enough) | `<name>-apiserver` |
| `imageset` | ImageSet, rendered when the key is present | `<name>-imageset` |
| `goldmane` | Goldmane, rendered when the key is present (`goldmane: {}` is enough) | `<name>-goldmane` |
| `whisker` | Whisker, rendered when the key is present (`whisker: {}` is enough) | `<name>-whisker` |
| `namespace` | | Default namespace of NetworkPolicy and NetworkSet. Falls back to `parameters.namespace`, then `default`. |
| `network_policies.<name>` | NetworkPolicy | `<namespace>/<name>-np` |
| `global_network_policies.<name>` | GlobalNetworkPolicy | `<name>-gnp` |
| `network_sets.<name>` | NetworkSet | `<namespace>/<name>-netset` |
| `global_network_sets.<name>` | GlobalNetworkSet | `<name>-gnetset` |
| `ip_pools.<name>` | IPPool | `<name>-ippool` |
| `bgp_peers.<name>` | BGPPeer | `<name>-bgppeer` |
| `bgp_configurations.<name>` | BGPConfiguration | `<name>-bgpconfig` |

The Installation is rendered in every target, also in one that only sets policies; compile policies for an application in the target that holds the cluster's Installation, or set the same `installation` there.

Every operator resource accepts `name`, `labels`, `annotations` and `spec`, and gets the label `name: <name>`. `name` defaults to `default`. The CRDs only accept `default`, `tigera-secure` or `overlay` for an Installation `default` or `tigera-secure` for an APIServer and `default` for Goldmane and Whisker. An ImageSet must be named `calico-<release>`, for this release `calico-v3.33.0` (`enterprise-<release>` for the enterprise variants); the operator ignores names without that prefix and refuses to install while a `calico-*` ImageSet with the wrong release exists ([imageset.go](https://github.com/tigera/operator/blob/v1.44.0/pkg/controller/utils/imageset/imageset.go)). An ImageSet without `name` is rendered as `default` and logs a warning.

Precedence is generator defaults < `spec` < flat keys: a flat key that overrides the same field in `spec` wins and logs a warning. The override is per top-level field, so a flat `cni` or `calico_network` replaces the whole `spec.cni` or `spec.calicoNetwork`.

| Kind | Flat key | Renders to |
|---|---|---|
| Installation | `variant` | `spec.variant` (`Calico`, `CalicoEnterprise`, `TigeraSecureEnterprise`) |
| Installation | `kubernetes_provider` | `spec.kubernetesProvider` |
| Installation | `registry`, `image_path`, `image_prefix` | `spec.registry`, `spec.imagePath`, `spec.imagePrefix` |
| Installation | `image_pull_secrets` | `spec.imagePullSecrets`; a string becomes `{name: <string>}` |
| Installation | `cni` | `spec.cni` from `type`, `ipam`, `bin_dir`, `conf_dir` |
| Installation | `calico_network` | `spec.calicoNetwork` from `bgp`, `mtu`, `linux_dataplane`, `ip_pools`, `host_ports`, `node_address_autodetection_v4`, `node_address_autodetection_v6`, `container_ip_forwarding`, `multi_interface_mode`, `windows_dataplane` |
| Installation | `calico_network.ip_pools[]` | `cidr`, `encapsulation`, `nat_outgoing`, `node_selector`, `block_size`, `disable_bgp_export` |
| Installation | `control_plane_replicas`, `fips_mode`, `non_privileged`, `flex_volume_path`, `kubelet_volume_plugin_path`, `service_cidrs`, `control_plane_tolerations`, `control_plane_node_selector` | the camelCase field (`serviceCIDRs` for `service_cidrs`) |
| Installation | `calico_node_daemon_set`, `calico_kube_controllers_deployment`, `typha_deployment`, `certificate_management`, `node_update_strategy`, `node_metrics_port`, `logging`, `proxy`, `azure` | the camelCase field, value verbatim |
| ImageSet | `images` | `spec.images` |
| Goldmane | `metrics_port`, `goldmane_deployment` | `spec.metricsPort`, `spec.goldmaneDeployment` |
| Whisker | `notifications`, `whisker_deployment` | `spec.notifications`, `spec.whiskerDeployment` |

Enum values are checked against the CRD and fail the compile with the allowed values. Keys in `cni`, `calico_network` and `ip_pools` entries that are not listed pass through verbatim, so write them in CRD casing (for example `specVersion`, `installMode`, `assignmentMode`, `linuxPodInterfaceType`); the listed keys win over them.

### projectcalico.org resources

Every `projectcalico.org` resource accepts `labels`, `annotations` and `spec`, and gets the label `name: <name>`; NetworkPolicy and NetworkSet also accept `namespace`. Network sets are matched by their `labels`. Precedence is generator defaults < `spec` < flat keys and shorthands: a flat key that overrides the same field in `spec` wins and logs a warning.

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

#### Shorthands

| Input | Result |
|---|---|
| any selector field as a map, `{app: web, tier: api}` (spec level and in a rule's `source` or `destination`) | `app == 'web' && tier == 'api'`, keys sorted |
| rule `ports: [8080, "8443:8445", http]` | `protocol: TCP` and `destination.ports: [8080, "8443:8445", http]` |
| rule `ports: [53/UDP, 53/TCP]` | two rules, one per protocol, otherwise identical |

Selector strings pass through unchanged, so expressions such as `has(k)`, `in {...}` or `all()` stay available ([selectors](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#selectors)). Calico requires `protocol` on any rule that matches ports (Rule.protocol in the CRD); `ports` uses the rule's `protocol` and otherwise TCP. Calico rules carry one protocol each, so mixed protocols become one rule per protocol, the same split the upstream [default deny example](https://docs.tigera.io/calico/3.33/network-policy/get-started/kubernetes-default-deny) uses for DNS. Numeric strings become integers, ranges and named ports stay strings ([ports](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#ports)).

An empty selector map and an empty `ports` list fail the compile. Calico treats an empty match field as unset ([empty match fields](https://docs.tigera.io/calico/3.33/reference/resources/networkpolicy#empty-match-fields)), so a rule with `selector: {}` or `ports: []` would match every peer or port. Write `all()` to select everything on purpose.

#### Defaults

For these kinds the generator adds no rule, policy or networking setting on its own:

- No allow policy is rendered unless written. `types` and `tier` are left to Calico's admission policies, which set `types` from the rules present and `tier` to `default`.
- IPPool `ipipMode` and `vxlanMode` default to `Never` and `natOutgoing` to `false` upstream. An extra pool without `nat_outgoing: true` therefore does not masquerade, unlike the operator's default pool. Encapsulation and NAT change how traffic leaves the node and are rendered only when set; `blockSize` and `allowedUses` are left to admission.
- BGP settings are rendered only when set. A `BGPConfiguration` named `default` applies to the whole cluster, `node.<node name>` to one node ([BGPConfiguration](https://docs.tigera.io/calico/3.33/reference/resources/bgpconfig)); `node_to_node_mesh_enabled: false` removes the full mesh and needs BGPPeers to keep routes.

### Operator defaults

Once `cni` is set the CRD requires `cni.type`. Without one the generator takes `spec.cni.type`, or else sets the operator's own default for the provider: `AzureVNET` for `AKS`, `AmazonVPC` for `EKS`, `GKE` for `GKE`, `Calico` otherwise ([fillDefaults](https://github.com/tigera/operator/blob/v1.44.0/pkg/controller/installation/core_controller.go)). The operator additionally picks `AmazonVPC` when an `aws-node` DaemonSet exists; that cannot be seen at compile time, so set `type` on such clusters.

Nothing else is defaulted. `variant` is left to the operator, which fills in the variant it runs as. BGP, encapsulation, NAT and the IP pools themselves change the cluster network and are rendered only when set; the operator defaults an IP pool to IPIP encapsulation, `natOutgoing: Enabled`, `nodeSelector: all()` and block size 26 ([Installation API](https://docs.tigera.io/calico/3.33/reference/installation/api)).

Goldmane and Whisker are opt-in, although the upstream `custom-resources.yaml` creates both: Goldmane aggregates the flow logs of every node and Whisker serves them in a UI. The operator marks Whisker degraded while no Goldmane exists ([whisker controller](https://github.com/tigera/operator/blob/v1.44.0/pkg/controller/whisker/controller.go)), so `whisker` without `goldmane` logs a warning. Whisker's `notifications` defaults to `Disabled` here because the upstream default `Enabled` makes the UI fetch banner text from an external API ([Whisker CRD](https://github.com/tigera/operator/blob/v1.44.0/pkg/imports/crds/operator/operator.tigera.io_whiskers.yaml)); `notifications` or `spec.notifications` set to `Enabled` turns it on.

An ImageSet must list a digest for every image the operator deploys for the configured Installation; image names are the `calico/` names of the release, such as `calico/calico`, `calico/node` and `calico/third-party-cni-plugins` ([ImageSet](https://docs.tigera.io/calico/3.33/operations/image-options/imageset)).

### Example

```yaml
parameters:
  generators:
    calico:
      installation:
        calico_network:
          bgp: Enabled
          node_address_autodetection_v4:
            kubernetes: NodeInternalIP
          ip_pools:
            - name: default-ipv4-ippool
              cidr: 10.244.0.0/16
              encapsulation: IPIPCrossSubnet
              nat_outgoing: Enabled
        control_plane_replicas: 2
        spec:
          nodeMetricsPort: 9091
      api_server: {}
      imageset:
        name: calico-v3.33.0
        images:
          - image: calico/calico
            digest: sha256:4ebc20730127bc9e8bf1db5f5a2d8b58cf37fe0e891b3c7b5471992221d213e5
          - image: calico/node
            digest: sha256:565d8db3200e443955557f8f28ff44ab8a4a456754bc74a19c4f2f3444af9b1c
          - image: calico/third-party-cni-plugins
            digest: sha256:0f32f48279484c0d6f0e0d0e767b2d0e1a6c6ca34cb3421a61b989d992f3df41
```

This renders `default-installation`, `default-apiserver` and `calico-v3.33.0-imageset`.

Policies, network sets and BGP:

```yaml
parameters:
  generators:
    calico:
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

This renders `shop/api-np`, `deny-app-policy-gnp`, `shop/partner-api-netset` and `rack1-tor-bgppeer`. `deny-app-policy` is the upstream global default deny for application namespaces with DNS to kube-dns allowed; `api` then allows its own traffic, including egress to the partner network set. `default-installation` is rendered as well.

## Schemas

`schemas/operator.tigera.io/` holds the closed JSON Schemas of the five kinds from the Tigera operator 1.44.0 CRDs (Apache-2.0). `schemas/projectcalico.org/` holds the closed JSON Schemas of the seven kinds from the Calico 3.33.0 `v3_projectcalico_org.yaml` CRDs (Apache-2.0). The CRDs' CEL rules, for example that an IPPool CIDR is strictly masked or that `node` and `nodeSelector` exclude each other, are checked by the API server, not by QA-7.
