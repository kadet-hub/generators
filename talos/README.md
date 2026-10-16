# Talos Generator

Published on [kadet-hub](https://kadet-hub.org/generators/talos/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/talos/) page.

Kapitan kadet generator for [Talos](https://www.talos.dev/) machine configurations. One inventory block describes a cluster: a shared `base` plus one entry per node. Each node yields a multi-document machine config for `talosctl apply-config`; optional outputs are a Kubernetes Secret per node carrying that config as KubeVirt cloud-init userdata, config patches and a `talosconfig`.

Built for Talos 1.14.3. Talos 1.14 deprecates most `v1alpha1` `machine` and `cluster` fields in favour of multi-document kinds ([v1alpha1 types](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/v1alpha1/v1alpha1_types.go)). The inventory keeps the `v1alpha1` shape; the generator writes each node as the `v1alpha1` document reduced to its current fields (`machine.type`, `token`, `ca`, `acceptedCAs`, `certSANs`, `features`, `logging`, `seccompProfiles`, `cluster.token`, `etcd`, `externalCloudProvider`, `adminKubeconfig`) followed by the documents that replace the rest, the way `talosctl gen config` 1.14.3 does.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/talos@sha256:<digest>
        output_path: lib/talos
    compile:
      - output_path: talos/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/talos
```

### Inventory Contract

All keys live under `parameters.generators.talos`.

| Key | Output key | Content |
|---|---|---|
| `base` | | Config deep-merged under every node. |
| `nodes.<name>` | `<name>` | Talos machine config: the `v1alpha1` document plus multi-document kinds. |
| `nodes.<name>.userdataSecret` (`name`, `namespace`) | `<namespace>/<name>-secret` | `v1` Secret, `stringData.userdata` holds the node's machine config. |
| `patches.<name>` | `<name>` | Config patch, passed through with the dict forms below normalized. |
| `secrets` | `secrets` | Passed through, for a `talosctl gen secrets` bundle. |
| `talosconfig` | `talosconfig` | Passed through. |

A node accepts `type` (`controlplane`, `worker` or `init`, default `worker`), `debug`, `machine`, `cluster` and the shorthands below. The legacy `parameters.talos_nodes` location still works with a deprecation warning; a node of the same name under `generators.talos.nodes` wins. An extra output whose key equals a node name replaces that node and logs a warning.

Precedence: generator defaults < `base` < the node's `machine`/`cluster` < shorthands. `base` and the node merge recursively; lists replace. A shorthand that overrides a nested value logs `Flat key 'hostname' overrides spec passthrough 'machine.network.hostname' for resource '<node>'`.

| Shorthand | Result |
|---|---|
| `hostname: <h>` | `machine.network.hostname: <h>` |
| `ip: <cidr>` or a list | `addresses` of the only `machine.network.interfaces` entry; with zero or several interfaces the compile fails. |
| `interfaces: {eth0: {...}}` | `interfaces: [{interface: eth0, ...}]` |
| `extraKernelArgs: {console: ttyS0, quiet: true}` | `extraKernelArgs: [console=ttyS0, quiet]` |

The dict form keyed by the item's natural key works for `interfaces` (`interface`), interface and VLAN `routes` (`network`), `vlans` (`vlanId`), `machine.files` (`path`), `extraHostEntries` (`ip`), kubelet `extraMounts` (`destination`), install `extensions` (`image`), `seccompProfiles` (`name`), `cluster.inlineManifests` (`name`) and apiServer `admissionControl` (`name`). In the dict form, `base` and node entries merge per key.

### Translation to Talos 1.14 documents

| Inventory key | Document |
|---|---|
| `machine.network.hostname`, `features.stableHostname` | `HostnameConfig` |
| `machine.network.nameservers`, `searchDomains`, `disableSearchDomain`, `features.hostDNS` | `ResolverConfig` |
| `machine.network.extraHostEntries` | `StaticHostConfig` per entry |
| `machine.network.kubespan` | `KubeSpanConfig` |
| `machine.network.interfaces` | `LinkConfig`, `BondConfig`, `BridgeConfig`, `VLANConfig` (`<link>.<vlanId>`), `WireguardConfig`, `DummyLinkConfig`, `DHCPv4Config`/`DHCPv6Config`, `Layer2VIPConfig`/`HCloudVIPConfig` |
| `machine.install` | `UnattendedInstallConfig` |
| `machine.kubelet` | `KubeletConfig`, `KubeCredentialProviderConfig`; `nodeIP`, `registerWithFQDN`, `skipNodeRegistration` go to `KubeNodeConfig` |
| `machine.nodeLabels`, `nodeAnnotations`, `nodeTaints`, `cluster.allowSchedulingOnControlPlanes` | `KubeNodeConfig` |
| `machine.pods` | `KubeStaticPodConfig` named `<namespace>-<name>` |
| `machine.files` at `/etc/cri/conf.d/<name>.part` (`op: create`) | `CRICustomizationConfig` `<name>`; Talos merges all CRI customizations in lexicographic order of their name ([container.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/container/container.go)) |
| `machine.env`, `time`, `sysctls`, `sysfs`, `udev`, `kernel.modules`, `baseRuntimeSpecOverrides` | `EnvironmentConfig`, `TimeSyncConfig`, `SysctlConfig`, `SysfsConfig`, `UdevRulesConfig`, `KernelModuleConfig`, `CRIBaseRuntimeSpecConfig` |
| `machine.registries` | `RegistryMirrorConfig`, `RegistryTLSConfig`, `RegistryAuthConfig` per host |
| `machine.systemDiskEncryption.state`/`ephemeral` | `VolumeConfig` `STATE`/`EPHEMERAL` |
| `features.kubernetesTalosAPIAccess`, `kubePrism`, `imageCache` | `KubeTalosAPIAccessConfig`, `KubePrismConfig`, `ImageCacheConfig` (when enabled) |
| `cluster.id` + `secret`, `discovery` | `DiscoveryIdentityConfig`, `DiscoveryServiceConfig` |
| `cluster.clusterName`, `controlPlane.endpoint` | `KubeClusterConfig` |
| `cluster.network` | `KubeNetworkConfig`; CNI `flannel` (the default) `KubeFlannelCNIConfig`, `custom` URLs `KubeExternalManifestConfig`, `none` nothing |
| `cluster.ca`, `acceptedCAs`, `aggregatorCA`, `serviceAccount` | `KubeAPIServerCAConfig`, `KubeAggregatorCAConfig`, `KubeServiceAccountConfig` |
| `cluster.secretboxEncryptionSecret`, `aescbcEncryptionSecret` | `KubeEtcdEncryptionConfig` with the provider list Talos rendered for them (`key2`, `key1`, `identity`) |
| `cluster.apiServer`, `controlPlane.localAPIServerPort` | `KubeAPIServerConfig`, `KubeAuthenticationConfig`, `KubeAuthorizerConfig`, `KubeAdmissionControlConfig`, `KubeAuditPolicyConfig` |
| `cluster.controllerManager`, `scheduler`, `proxy`, `coreDNS`, `machine.controlPlane.*.disabled` | `KubeControllerManagerConfig`, `KubeSchedulerConfig`, `KubeProxyConfig`, `KubeCoreDNSConfig` |
| `cluster.extraManifests` (+ `extraManifestHeaders`), `inlineManifests` | `KubeExternalManifestConfig`, `KubeInlineManifestConfig` |

Worker configs leave out the kinds Talos only allows on control planes (API server, controller manager, scheduler, proxy, CoreDNS, flannel, etcd encryption, service account, aggregator CA, Talos API access) and the manifest kinds. They never carry the CA private keys: `machine.ca.key`, `cluster.ca.key` and `cluster.aggregatorCA.key` are dropped, the cluster CA certificate becomes an accepted CA, and `cluster.etcd` is dropped.

Some legacy blocks have no multi-document equivalent. They stay in the `v1alpha1` document, which Talos 1.14 still accepts, and the compile logs `node '<node>': <key> has no Talos v1.14 multi-document equivalent; kept in the deprecated v1alpha1 form`:

- `machine.install` with `extraKernelArgs`, `extensions`, `legacyBIOSSupport`, `grubUseUKICmdline` or `diskSelector.name` (Talos points to Image Factory for kernel arguments and extensions);
- `machine.network.interfaces` when one uses `deviceSelector`, bond `deviceSelectors`, `primary` or `adActorSystem`, or an Equinix Metal VIP, or when every interface is `ignore`;
- `machine.kubelet` with `extraMounts` or `disableManifestsDirectory: false`;
- `machine.files` outside `/etc/cri/conf.d/*.part`, and `machine.disks`;
- `machine.time` when `servers` mixes NTP servers and PTP devices (`/dev/...`), since `TimeSyncConfig` takes either `ntp` or `ptp`;
- `cluster.discovery` with the Kubernetes registry enabled (`DiscoveryServiceConfig` has no Kubernetes registry and conflicts with any `.cluster.discovery` block);
- `cluster.apiServer`, `controllerManager` or `scheduler` with `extraVolumes`, and `apiServer.extraArgs` with `anonymous-auth`, `oidc-*`, `authentication-config`, `authorization-mode`, `authorization-config` or `authorization-webhook-*`, which `KubeAPIServerConfig` denies ([apiserver.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/k8s/apiserver.go)).

Keys whose meaning changes with the translation:

- Certificates and keys under `cluster.ca`, `acceptedCAs`, `aggregatorCA`, `serviceAccount` and registry `tls` are base64-encoded PEM in `v1alpha1` and plain PEM in the documents. The generator decodes plain values; it cannot decode a Kapitan ref, so a ref for one of these keys must hold the PEM text. `machine.ca` and `cluster.etcd.ca` stay base64.
- `machine.time.servers` become `TimeSyncConfig` `ntp.servers`, or `ptp.devices` when every entry is a PTP device (`/dev/...`); Talos 1.14.3 rejects PTP devices in `ntp.servers` ([time_sync.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/network/time_sync.go)).
- `machine.install.disk` becomes the CEL selector `disk.dev_path == "<disk>"`, or `"<disk>" in disk.symlinks` for a `/dev/disk/...` path; `diskSelector` becomes the expression Talos built from it ([DiskMatchExpression](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/v1alpha1/v1alpha1_provider.go)).
- `machine.network.interfaces`: once a link document exists, Talos stops running DHCP on the other physical links ([RunDefaultDHCPOperators](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/container/container.go)). An interface with `ignore: true` therefore emits nothing. A route to `0.0.0.0/0` or `::/0` becomes a route without destination, which `LinkConfig` treats as the default route.
- `cluster.extraManifests` and custom CNI URLs (both with `extraManifestHeaders`) are named after the URL with every character outside `[a-z0-9.]` replaced by `-`; the legacy path used the URL itself, which the document rejects.
- `persist` is ignored; Talos 1.14 no longer supports it.
- `patches` pass through as written. For Talos 1.14 write them as multi-document kinds, as in the example below.

Defaults the generator adds, each matching what the legacy path did implicitly or what the document requires:

- `UnattendedInstallConfig.installer.image` is the installer `talosctl gen config` 1.14.3 writes, `factory.talos.dev/metal-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.3` ([images.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/images/images.go)); without an image Talos only installs from Image Factory boot assets and does not reboot after the install ([unattended_install.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/runtime/unattended_install.go)). Set `install.image` for other platforms, for example `nocloud-installer` on KubeVirt.
- `provisioning.wipe: false` unless `install.wipe` is set: the document defaults to `true`, the legacy section to `false`.
- `install.disk: /dev/sda` when neither `disk` nor `diskSelector` is set, with a deprecation warning; the document requires a selector. Set it explicitly.
- Images for `KubeletConfig`, `KubeAPIServerConfig`, `KubeControllerManagerConfig`, `KubeSchedulerConfig` and `KubeProxyConfig` when the inventory sets none: Kubernetes 1.37.1, the default of Talos 1.14.3 ([constants.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/constants/constants.go)). The documents require an image.
- `KubeNetworkConfig` falls back to `cluster.local`, `10.244.0.0/16` and `10.96.0.0/12`, and `KubeFlannelCNIConfig` to `backendType: vxlan` and `backendPort: 4789`, as the legacy path did ([v1alpha1_cniconfig.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/v1alpha1/v1alpha1_cniconfig.go)); without the port flannel would use 8472.
- With `KubeAPIServerConfig`, the `Node` (first) and `RBAC` (second) authorizers are added when `authorizationConfig` lacks them, as the legacy path did ([control_plane.go](https://github.com/siderolabs/talos/blob/v1.14.3/internal/app/machined/pkg/controllers/k8s/control_plane.go)); the document path adds none. `KubeAuthenticationConfig` is Talos' default, the one `talosctl gen config` writes: anonymous access only to `/livez`, `/readyz` and `/healthz` ([authentication.go](https://github.com/siderolabs/talos/blob/v1.14.3/pkg/machinery/config/types/k8s/authentication.go)). The document path renders kube-apiserver with `--authentication-config` instead of `--anonymous-auth=false` and enables startup probes, which call those paths unauthenticated.
- `KubeNodeConfig` on a control plane gets the `node-role.kubernetes.io/control-plane` label and, unless `allowSchedulingOnControlPlanes` is set, its `NoSchedule` taint, which the legacy path added implicitly.
- `debug: false`.

### Example

```yaml
parameters:
  generators:
    talos:
      base:
        machine:
          token: ?{gpg:talos/prod/machine-token}
          ca:
            crt: ?{gpg:talos/prod/machine-ca-crt}
            key: ?{gpg:talos/prod/machine-ca-key}
          features:
            kubePrism:
              enabled: true
              port: 7445
          network:
            nameservers:
              - 10.0.0.2
            interfaces:
              eth0:
                dhcp: false
                routes:
                  0.0.0.0/0:
                    gateway: 10.0.0.1
        cluster:
          id: ?{gpg:talos/prod/cluster-id}
          secret: ?{gpg:talos/prod/cluster-secret}
          clusterName: prod
          controlPlane:
            endpoint: https://k8s.example.com:6443
          token: ?{gpg:talos/prod/cluster-token}
          secretboxEncryptionSecret: ?{gpg:talos/prod/secretbox}
          ca:
            crt: ?{gpg:talos/prod/cluster-ca-crt-pem}
            key: ?{gpg:talos/prod/cluster-ca-key-pem}
          serviceAccount:
            key: ?{gpg:talos/prod/service-account-key-pem}
          network:
            cni:
              name: none
          proxy:
            disabled: true
          discovery:
            enabled: true
            registries:
              service: {}
      nodes:
        cp-1:
          type: controlplane
          hostname: cp-1
          ip: 10.0.0.11/24
          machine:
            install:
              diskSelector:
                type: ssd
            network:
              interfaces:
                eth0:
                  vip:
                    ip: 10.0.0.10
        worker-1:
          type: worker
          hostname: worker-1
          ip: 10.0.0.21/24
          machine:
            install:
              disk: /dev/sda
        worker-2:
          type: worker
          hostname: worker-2
          ip: 10.0.0.22/24
          userdataSecret:
            name: worker-2-userdata
            namespace: talos-vms
          machine:
            install:
              disk: /dev/vda
              image: factory.talos.dev/nocloud-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.3
      patches:
        patch-time:
          apiVersion: v1alpha1
          kind: TimeSyncConfig
          ntp:
            servers:
              - time.example.com
```

Tokens, CA material and the `secrets` bundle belong in Kapitan refs as above, never in plain inventory; the generator sets none of them. Kapitan writes the refs unrevealed unless you compile with `--reveal`.

## Output

```
compiled/<target>/talos/
├── cp-1.yaml
├── worker-1.yaml
├── worker-2.yaml
├── talos-vms/
│   └── worker-2-userdata-secret.yaml
└── patch-time.yaml
```

Each node file is a multi-document YAML stream: the `v1alpha1` document first, then the kinds in a fixed order. Apply it with `talosctl apply-config --nodes 10.0.0.11 --file compiled/<target>/talos/cp-1.yaml`. Reference the Secret from the VirtualMachine's `cloudInitNoCloud.secretRef`.

## Schemas

The kadet-hub gate validates every Talos multi-document kind against the schema of Talos 1.14.3 and the userdata Secret against Kubernetes 1.37.1 (QA-7). The Talos schemas under `schemas/core/*_v1alpha1.json` are split per kind from the upstream `config.schema.json`; they are MPL-2.0 (see `schemas/core/NOTICE`), the generator code is Apache-2.0. The `v1alpha1` base document has no `apiVersion`/`kind` and is not schema-checked.
