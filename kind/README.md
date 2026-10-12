# kind Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kind/) page.

Kapitan kadet generator for [kind](https://kind.sigs.k8s.io/) cluster configuration files (`kind.x-k8s.io/v1alpha4` `Cluster`). Each entry under `clusters` renders one file for `kind create cluster --config`.

Built for kind v0.33.0.

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kind@sha256:<digest>
        output_path: lib/kind
    compile:
      - output_path: kind/
        input_type: kadet
        output_type: yaml
        input_paths:
          - lib/kind
  generators:
    kind:
      clusters:
        dev:
          kubernetes_version: "1.37"
          networking:
            disable_default_cni: true
            pod_subnet: 192.168.0.0/16
          nodes:
            - role: control-plane
              extra_port_mappings:
                - container_port: 30080
                  host_port: 8080
                  listen_address: 127.0.0.1
            - role: worker
              labels:
                tier: frontend
            - role: worker
              labels:
                tier: backend
```

```bash
kind create cluster --config compiled/<target>/kind/dev.yaml
```

## Inputs

All keys live under `parameters.generators.kind.clusters.<name>`. Keys are snake_case and render the kind camelCase field of the same name; values pass through unchanged. The camelCase spelling of a modelled key raises an error naming the replacement; any other unknown key is dropped with a warning.

| Level | Keys |
|---|---|
| cluster | `kubernetes_version`, `feature_gates`, `runtime_config`, `networking`, `nodes`, `containerd_config_patches`, `containerd_config_patches_json6902`, `spec` |
| `networking` | `ip_family`, `api_server_address`, `api_server_port`, `pod_subnet`, `service_subnet`, `disable_default_cni`, `kube_proxy_mode` |
| `nodes[]` | `role`, `image`, `kubernetes_version`, `labels`, `extra_mounts`, `extra_port_mappings`, `kubeadm_config_patches`, `kubeadm_config_patches_json6902` |
| `extra_mounts[]` | `host_path`, `container_path`, `read_only`, `selinux_relabel`, `propagation` |
| `extra_port_mappings[]` | `container_port`, `host_port`, `listen_address`, `protocol` |

`ip_family`, `kube_proxy_mode`, `role`, `propagation` and `protocol` are checked against the values kind accepts. `containerd_config_patches_json6902` is a list of strings, as in kind.

`kubernetes_version` (`"1.37"`, `"1.37.0"` or `"v1.37.0"`; quote it) sets `image` to the digest-pinned `kindest/node` image that the [kind v0.33.0 release notes](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0) list for that version: 1.37.0, 1.36.4, 1.35.8 or 1.34.11. kind requires the `@sha256` digest to get an image built for the release. Set on the cluster, it applies to every node without its own `image` or `kubernetes_version`; with no `nodes`, it writes out kind's default single control-plane node. A node with both `image` and `kubernetes_version` is an error. Without `kubernetes_version` and `image`, kind uses its own default image.

`spec` holds kind fields in their upstream camelCase spelling, for fields without a flat key such as cluster-level `kubeadmConfigPatches` or `networking.dnsSearch`. It is written first and passes through unchecked; flat keys are applied on top, and a flat key that overrides a `spec` value logs a warning. `kubernetes_version` does not touch nodes given in `spec`.

The generator sets no defaults of its own. `api_server_address` stays kind's `127.0.0.1` unless set; kind's documentation strongly discourages exposing the API server on other addresses.

`extra_mounts` write `hostPath` entries, so the manifest declares the `host-path` output capability.

## Output

| Input | Output file |
|---|---|
| `clusters.<name>` | `<name>.yaml`, with `name: <name>` |

The output is not schema-checked: kind publishes no JSON Schema for its config, so the generator ships none. kind itself decodes the file strictly and rejects unknown fields when the cluster is created.
