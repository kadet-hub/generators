# Tetragon Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/tetragon/) page.

Kapitan kadet generator for [Tetragon](https://tetragon.io/) policies (`cilium.io/v1alpha1`). Built for Tetragon 1.7.1.

- **TracingPolicy**: cluster-wide policy, applies to every process on the selected nodes
- **TracingPolicyNamespaced**: policy that applies only to the pods of its namespace

Only these custom resources are rendered. The Tetragon install (DaemonSet, operator, RBAC) comes from the [Tetragon Helm chart](https://github.com/cilium/tetragon/tree/v1.7.1/install/kubernetes/tetragon) through the `helm` input. PodInfo is written by the Tetragon operator. The requirements are in [docs/specs/tetragon.md](../docs/specs/tetragon.md).

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/tetragon@sha256:<digest>
        output_path: lib/tetragon
    compile:
      - output_path: manifests/tetragon/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/tetragon
```

### Inventory Contract

All keys live under `parameters.generators.tetragon`.

| Key | Kind | Output key |
|---|---|---|
| `tracing_policies.<key>` | TracingPolicy | `<name>-tracingpolicy` |
| `tracing_policies_namespaced.<key>` | TracingPolicyNamespaced | `<namespace>/<name>-tracingpolicynamespaced` |

The resource is named after `name` on the entry, else after its key. Two entries of one section that render the same name (in the same namespace) fail the compile.

Namespace of a TracingPolicyNamespaced: `namespace` on the entry, then `generators.tetragon.namespace`, then `parameters.namespace`, then `default`.

Every entry accepts `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. The flat keys below set the top-level `spec` field of the same name in camelCase. A flat key wins over the same field in `spec` and logs a warning.

`kprobes`, `tracepoints`, `uprobes`, `usdts`, `lsmhooks`, `fentries`, `enforcers`, `lists`, `options`, `loader`, `pod_selector` (→ `podSelector`), `container_selector` (→ `containerSelector`), `host_selector` (→ `hostSelector`), `selectors_macros` (→ `selectorsMacros`)

Values are written as in the [Tetragon policy reference](https://tetragon.io/docs/concepts/tracing-policy/), in CRD camelCase (`matchArgs`, `matchActions`), so upstream examples can be copied. The compiled output is validated against the 1.7.1 CRD schemas.

The `Override` action needs kernel support: on `kprobes` a kernel with `CONFIG_BPF_KPROBE_OVERRIDE`, on `lsmhooks` the `bpf` LSM. `Sigkill` works without either.

### Example

```yaml
parameters:
  generators:
    tetragon:
      tracing_policies:
        write-etc:
          kprobes:
            - call: security_file_permission
              syscall: false
              args:
                - index: 0
                  type: file
                - index: 1
                  type: int
              selectors:
                - matchArgs:
                    - index: 0
                      operator: Prefix
                      values: ["/etc/"]
                    - index: 1
                      operator: Equal
                      values: ["2"]
      tracing_policies_namespaced:
        exec-shell:
          namespace: apps
          pod_selector:
            matchLabels:
              app: web
          tracepoints:
            - subsystem: raw_syscalls
              event: sys_enter
              args:
                - index: 4
                  type: syscall64
              selectors:
                - matchArgs:
                    - index: 4
                      operator: Equal
                      values: ["59"]
```

This renders `write-etc-tracingpolicy`, which reports writes below `/etc` on every node, and `apps/exec-shell-tracingpolicynamespaced`, which reports `execve` (syscall 59 on x86-64) in the `web` pods of `apps`.
