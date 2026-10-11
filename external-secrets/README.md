# External Secrets Generator

Kapitan kadet generator for [External Secrets Operator](https://external-secrets.io/) resources (`external-secrets.io/v1`):

- **SecretStore**: namespaced provider configuration
- **ClusterSecretStore**: cluster-scoped provider configuration
- **ExternalSecret**: syncs provider values into a Kubernetes Secret
- **ClusterExternalSecret**: one ExternalSecret spec fanned out across namespaces

Only ESO custom resources are rendered. ServiceAccounts, Roles and RoleBindings (for example the reader ServiceAccount a SecretStore authenticates with) belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/external-secrets@sha256:<digest>
        output_path: lib/external-secrets
    compile:
      - output_path: manifests/external-secrets/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/external-secrets
```

### Inventory Contract

All keys live under `parameters.generators.external_secrets`.

| Key | Scope | Description |
|---|---|---|
| `namespace` | generator | Default namespace for namespaced kinds. Falls back to `parameters.namespace`, then `default`. |
| `deny_cluster_scoped` | generator | `true` fails the compile on any ClusterSecretStore, ClusterExternalSecret, or `secretStoreRef` of kind ClusterSecretStore. |
| `namespace_key_prefix` | generator | Every `data[].remoteRef.key` and `dataFrom[].extract.key` of an ExternalSecret must start with `<prefix>/<namespace>/` and must not contain a `..` segment. `dataFrom[].find` and ClusterExternalSecret fail the compile because their keys cannot be checked per namespace. |
| `secretstores.<name>` | resource | SecretStore. `spec` is required and passed through. |
| `clustersecretstores.<name>` | resource | ClusterSecretStore. `spec` is required and passed through. |
| `externalsecrets.<name>` | resource | ExternalSecret. `spec` is passed through; shorthands below. |
| `clusterexternalsecrets.<name>` | resource | ClusterExternalSecret. Shorthands apply to `spec.externalSecretSpec`. |

Every resource entry accepts `name` (overrides the map key), `labels`, `annotations`, and, for namespaced kinds, `namespace`.

ExternalSecret and ClusterExternalSecret shorthands:

| Key | Result |
|---|---|
| `store: <name>` | `secretStoreRef: {kind: SecretStore, name: <name>}` |
| `cluster_store: <name>` | `secretStoreRef: {kind: ClusterSecretStore, name: <name>}` |
| `refresh_interval: <duration>` | `refreshInterval: <duration>` |
| `allow_default_refresh: true` | Allows omitting a refresh interval; ESO's default applies. |

A refresh interval is required: set `refresh_interval`, `refreshInterval` in `spec`, or `allow_default_refresh: true` on the entry. `store` and `cluster_store` are mutually exclusive. Shorthands override the same field in `spec` and log a warning.

Provider blocks (`vault`, `conjur`, or any other ESO provider) pass through as dicts. OpenBao uses the `vault` provider.

### Example

```yaml
parameters:
  generators:
    external_secrets:
      deny_cluster_scoped: true
      namespace_key_prefix: platform/dev
      secretstores:
        vault-backend:
          namespace: thanos
          spec:
            provider:
              vault:
                server: https://vault.example.internal
                path: secret
                version: v2
                caProvider:
                  type: ConfigMap
                  name: platform-ca
                  key: ca-bundle.crt
                auth:
                  jwt:
                    path: jwt
                    role: thanos
                    kubernetesServiceAccountToken:
                      serviceAccountRef:
                        name: external-secrets-reader
                        audiences: [vault]
        conjur-backend:
          namespace: loki
          spec:
            provider:
              conjur:
                url: https://conjur.example.internal
                auth:
                  jwt:
                    account: platform
                    serviceID: k8s-cluster-a
                    serviceAccountRef:
                      name: external-secrets-reader
      externalsecrets:
        thanos-objstore-config:
          namespace: thanos
          store: vault-backend
          refresh_interval: 1h
          spec:
            target:
              creationPolicy: Owner
              template:
                data:
                  objstore.yml: |
                    type: S3
                    config:
                      access_key: "{{ .access_key }}"
                      secret_key: "{{ .secret_key }}"
            data:
              - secretKey: access_key
                remoteRef:
                  key: platform/dev/thanos/s3
                  property: access_key
              - secretKey: secret_key
                remoteRef:
                  key: platform/dev/thanos/s3
                  property: secret_key
```

Output files:

| Kind | Output key |
|---|---|
| SecretStore | `<namespace>/<name>-ss` |
| ClusterSecretStore | `<name>-css` |
| ExternalSecret | `<namespace>/<name>-es` |
| ClusterExternalSecret | `<name>-ces` |

Validation failures raise `ValueError: external-secrets <Kind> '<name>': <reason>` and stop the compile.
