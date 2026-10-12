# K3d Generator

Published on [kadet-hub](https://kadet-hub.org/generators/k3d/): pin a released version by digest from its catalog page.

Kapitan kadet generator for [k3d](https://k3d.io/) cluster config files. Every entry under `clusters` becomes one `k3d.io/v1alpha5` `Simple` config that `k3d cluster create --config` reads. Built for k3d 5.9.0.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/k3d@sha256:<digest>
        output_path: lib/k3d
    compile:
      - output_path: k3d/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/k3d
```

```bash
k3d cluster create --config compiled/<target>/k3d/<cluster>.yml
```

### Inventory Contract

All keys live under `parameters.generators.k3d.clusters.<cluster>`. The cluster key becomes `metadata.name` and the output file `<cluster>.yml`. The keys are the k3d v1alpha5 config fields and pass through unchanged, apart from the forms below:

| Key | Accepted input | Output |
|---|---|---|
| `servers`, `agents`, `image`, `network`, `subnet`, `token` | value | same field |
| `kubeAPI` | `host`, `hostIP`, `hostPort` | values rendered as strings, so `hostPort: 6443` is valid |
| `ports`, `volumes`, `env` | plain value, `{port\|volume\|envVar: ..., nodeFilters}` or `{value: ..., nodeFilters}` | `{port\|volume\|envVar: "<string>", nodeFilters}` |
| `files` | `source`, `destination`, `description`, `nodeFilters` | same |
| `registries` | `create` (`name`, `host`, `hostPort`, `image`, `proxy`, `volumes`, `enforcePortMatch`), `use`, `config` | same |
| `hostAliases` | `ip`, `hostnames` | same |
| `options` | `k3d`, `k3s` (`extraArgs`, `nodeLabels`), `kubeconfig`, `runtime` | same |

There is no `spec` passthrough and the generator sets no defaults: an empty cluster entry gives a config with only `apiVersion`, `kind` and `metadata`, and k3d applies its own defaults. One of them is `kubeAPI.hostIP: 0.0.0.0`, so the API listens on all host interfaces unless you set `hostIP: 127.0.0.1`; the same holds for `registries.create.host`.

Keys outside the v1alpha5 config are dropped from the output with a warning that names them. The generator does not validate at compile time; the shipped schema below is what the gate checks the output against.

Node filters: `loadbalancer`, `server:*`, `server:0`, `agent:*`, `agent:1`, `all`. A port without node filter goes to the load balancer when the cluster has more than one node.

`token` is the cluster join secret; set it from a Kapitan ref (`?{...}`), not as plain text.

### Example

```yaml
parameters:
  generators:
    k3d:
      clusters:
        dev:
          servers: 1
          agents: 2
          image: rancher/k3s:v1.32.5-k3s1
          kubeAPI:
            hostIP: 127.0.0.1
            hostPort: 6443
          ports:
            - port: "8080:80"
              nodeFilters: ["loadbalancer"]
          registries:
            create:
              name: registry.localhost
              host: 127.0.0.1
              hostPort: "5000"
              proxy:
                remoteURL: https://registry-1.docker.io
            config: |
              mirrors:
                "docker.io":
                  endpoint:
                    - "http://registry.localhost:5000"
          options:
            k3s:
              extraArgs:
                - arg: --disable=traefik
                  nodeFilters: ["server:*"]
```

The registry is created under the given name and is reachable from the nodes as `registry.localhost:5000`; with `proxy.remoteURL` it acts as a pull-through cache for Docker Hub.

## Output

| File | Content |
|---|---|
| `<cluster>.yml` | `k3d.io/v1alpha5` `Simple`, one per cluster |

## Schemas

`schemas/k3d.io/simple_v1alpha5.json` is the SimpleConfig schema k3d publishes at [v5.9.0](https://github.com/k3d-io/k3d/blob/v5.9.0/pkg/config/v1alpha5/schema.json) (MIT, see `schemas/k3d.io/LICENSE`), closed so that unknown fields fail. All output is checked against it. The k3s manifests or registry config embedded as strings in `files[].source` and `registries.config` are not schema-checked.
