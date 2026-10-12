# kmcp Generator

Published on [kadet-hub](https://kadet-hub.org/generators/kmcp/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kmcp/) page.

Kapitan kadet generator for [kmcp](https://github.com/kagent-dev/kmcp) `MCPServer` resources (`kagent.dev/v1alpha1`). Built for kmcp 0.4.0. Each entry under `mcpservers` becomes one MCPServer; the kmcp controller turns it into a Deployment, Service and ConfigMap that run the MCP server, for stdio servers behind the agentgateway transport adapter.

Secrets and ConfigMaps referenced by `secret_refs` and `configmap_refs` belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kmcp@sha256:<digest>
        output_path: lib/kmcp
    compile:
      - output_path: manifests/kmcp/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/kmcp
```

### Inventory Contract

Servers are read from `parameters.generators.kmcp.mcpservers.<name>` and written to `<namespace>/<name>-mcpserver`. The namespace resolves from the server's `namespace`, then `parameters.generators.kmcp.namespace`, then `parameters.namespace`, then `default`.

| Key | Default | Result |
|---|---|---|
| `namespace`, `labels`, `annotations` | | `metadata`; the labels `name`, `app.kubernetes.io/managed-by: kmcp` and `app.kubernetes.io/component: mcp-server` are always added |
| `transport_type` | `stdio` | `spec.transportType`, `stdio` or `http`; other values raise an error |
| `stdio_transport` | `{}` | `spec.stdioTransport` (stdio only) |
| `http_transport.target_port` | `deployment.port` | `spec.httpTransport.targetPort` (http only) |
| `http_transport.target_path` (alias `path`) | | `spec.httpTransport.path` |
| `deployment.port` | `3000` | `spec.deployment.port` |
| `deployment.image`, `image_pull_policy`, `cmd`, `args`, `env`, `volume_mounts`, `volumes` | | the camelCase `spec.deployment` field, verbatim |
| `deployment.secret_refs`, `configmap_refs` | | `secretRefs`, `configMapRefs`; a list of names becomes `[{name: ...}]` |
| `deployment.init_container` (`image`, `image_pull_policy`) | | `spec.deployment.initContainer`, the transport adapter image for stdio |
| `deployment.service_account` (`annotations`, `labels`) | | `spec.deployment.serviceAccount` |
| `spec` | | raw `MCPServer` spec, for fields without a flat key (`replicas`, `resources`, `sidecars`, `serviceAccountName`, `timeout`, `httpTransport.tls`, ...) |

Precedence is generator defaults, then `spec`, then flat keys; a flat key that overrides a `spec` value logs a warning.

Defaults the generator adds, because the controller rejects the resource without them: `transportType` falls back to `stdio`, since the CRD has no default and the controller fails with "unsupported transport type" ([translator](https://github.com/kagent-dev/kmcp/blob/v0.4.0/pkg/controller/transportadapter/transportadapter_translator.go#L584-L603)); `httpTransport.targetPort` falls back to the deployment port, since the controller fails with "HTTP transport requires a target port", and for `http` the Service forwards to that port on the server container ([translator](https://github.com/kagent-dev/kmcp/blob/v0.4.0/pkg/controller/transportadapter/transportadapter_translator.go#L495-L520)). `deployment.port` is always emitted with its CRD default `3000` so the derived target port matches it. With `cmd: npx` or `cmd: uvx` and no `image`, the controller picks a Node or uv image itself ([translator](https://github.com/kagent-dev/kmcp/blob/v0.4.0/pkg/controller/transportadapter/transportadapter_translator.go#L101-L112)).

### Example

```yaml
parameters:
  namespace: mcp
  generators:
    kmcp:
      mcpservers:
        everything:
          deployment:
            cmd: npx
            args: ["-y", "@modelcontextprotocol/server-everything"]
        search:
          transport_type: http
          deployment:
            image: registry.example.com/mcp/search:1.2.0
            port: 8080
            secret_refs: [search-api-credentials]
            configmap_refs: [search-config]
          http_transport:
            target_path: /mcp
          spec:
            deployment:
              replicas: 2
```

`search` gets `httpTransport: {targetPort: 8080, path: /mcp}` without repeating the port.

## Output Files

| Output key | Kind |
|---|---|
| `<namespace>/<name>-mcpserver` | `kagent.dev/v1alpha1` MCPServer |

The compiled output is validated against the upstream CRD schema in `schemas/kagent.dev/`.
