# Multus Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/multus/) page.

Kapitan kadet generator for [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni) NetworkAttachmentDefinitions (`k8s.cni.cncf.io/v1`). Built for Multus CNI 4.3.1.

Each entry under `networks` renders one NetworkAttachmentDefinition. The CNI configuration is written as YAML in the inventory and serialised to the JSON string that `spec.config` expects, with sorted keys so the output is stable.

Only NetworkAttachmentDefinitions are rendered. The Multus install (DaemonSet, RBAC, CRD) belongs in the `helm` or `kubernetes` generator, and the `k8s.v1.cni.cncf.io/networks` annotation that attaches a pod to a network belongs on the workload.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/multus@sha256:<digest>
        output_path: lib/multus
    compile:
      - output_path: manifests/multus/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/multus
```

### Inventory Contract

All keys live under `parameters.generators.multus`.

| Key | Description |
|---|---|
| `namespace` | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `networks.<name>` | One NetworkAttachmentDefinition named `<name>`, output key `<namespace>/<name>-net-attach-def`. |

Every entry under `networks` accepts:

| Key | Result |
|---|---|
| `namespace` | `metadata.namespace` and the output directory. |
| `cni_config` | CNI config or config list (`plugins`) as a dict, serialised to JSON into `spec.config`. `name` is set to the entry name when absent. |
| `config_json` | Raw JSON string written to `spec.config` verbatim. Wins over `cni_config`. |
| `resource_name` | Annotation `k8s.v1.cni.cncf.io/resourceName`. |
| `labels`, `annotations` | Metadata. Every resource also gets the label `name: <name>`. |
| `spec` | Passed through to the resource `spec`. |

Precedence is generator defaults < `spec` < flat keys: `cni_config` or `config_json` wins over `spec.config` and logs a warning, and `resource_name` wins over the same key in `annotations`.

An entry without `cni_config`, `config_json` or `spec.config` renders an empty `spec`. Multus then loads the CNI config file from its config directory whose `name` matches the NetworkAttachmentDefinition ([GetCNIConfig](https://github.com/k8snetworkplumbingwg/network-attachment-definition-client/blob/v1.7.6/pkg/utils/cniconfig.go#L36-L56), the NAD client version Multus 4.3.1 builds with).

### Defaults and Shorthands

| Input | Result | Source |
|---|---|---|
| `cni_config` without `name` | `name: <entry name>` | Multus injects the same name at runtime ([GetCNIConfigFromSpec](https://github.com/k8snetworkplumbingwg/network-attachment-definition-client/blob/v1.7.6/pkg/utils/cniconfig.go#L108-L128)); the rendered config is complete without it. |
| `resource_name: <resource>` | `metadata.annotations["k8s.v1.cni.cncf.io/resourceName"]` | Multus matches this annotation against the device plugin or DRA resource name and passes the allocated device ID to the CNI plugin ([how-to-use](https://github.com/k8snetworkplumbingwg/multus-cni/blob/v4.3.1/docs/how-to-use.md#create-network-attachment-definition-with-resource-name), [k8sclient.go](https://github.com/k8snetworkplumbingwg/multus-cni/blob/v4.3.1/pkg/k8sclient/k8sclient.go#L309-L350)). The value must equal the resource name exactly. |

`cniVersion` has no default: which versions a config may declare depends on the CNI plugin binaries installed on the nodes. Set it in `cni_config`, as the upstream examples do.

### Example

```yaml
parameters:
  generators:
    multus:
      namespace: networks
      networks:
        storage-net:
          cni_config:
            cniVersion: 1.0.0
            type: macvlan
            master: eth1
            mode: bridge
            ipam:
              type: host-local
              subnet: 192.168.100.0/24
              rangeStart: 192.168.100.10
              rangeEnd: 192.168.100.200
        sriov-net:
          resource_name: intel.com/sriov_vf
          cni_config:
            cniVersion: 1.0.0
            plugins:
              - type: sriov
                vlan: 100
                ipam:
                  type: host-local
                  subnet: 192.168.200.0/24
              - type: tuning
                sysctl:
                  net.ipv6.conf.IFNAME.accept_ra: "0"
        legacy-net:
          namespace: kube-system
          config_json: '{"cniVersion":"0.3.1","type":"macvlan","master":"eth0","ipam":{"type":"dhcp"}}'
```

This renders `networks/storage-net-net-attach-def`, `networks/sriov-net-net-attach-def` (with the `resourceName` annotation and a two-plugin config list named `sriov-net`) and `kube-system/legacy-net-net-attach-def`.
