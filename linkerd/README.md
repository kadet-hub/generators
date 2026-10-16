# Linkerd Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/linkerd/) page.

Kapitan kadet generator for [Linkerd](https://linkerd.io/) policy resources. Built for Linkerd `edge-26.10.1`. Its CRDs are unchanged from `edge-26.6.3`, the edge release of Linkerd 2.20.

- **Server** (`policy.linkerd.io/v1beta3`): a port on a set of pods that policy applies to
- **ServerAuthorization** (`policy.linkerd.io/v1beta1`): clients allowed to reach a Server
- **AuthorizationPolicy** (`policy.linkerd.io/v1alpha1`): authentications required for a Server, HTTPRoute or namespace
- **MeshTLSAuthentication** (`policy.linkerd.io/v1alpha1`): a set of mesh identities
- **NetworkAuthentication** (`policy.linkerd.io/v1alpha1`): a set of client networks
- **HTTPRoute** (`policy.linkerd.io/v1beta3`): HTTP route attached to a Server
- **ServiceProfile** (`linkerd.io/v1alpha2`): per-route metrics, retries and timeouts of a Service

The Linkerd install belongs in the `helm` input with the upstream `linkerd-crds` and `linkerd-control-plane` charts. Gateway API routes (`gateway.networking.k8s.io`) are not rendered.

Server and HTTPRoute are emitted as `v1beta3`, the storage versions; Linkerd marks `v1beta1` deprecated ([CRD](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/charts/linkerd-crds/templates/policy/server.yaml#L73-L77)). The Linkerd docs describe AuthorizationPolicy as the replacement for ServerAuthorization.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/linkerd@sha256:<digest>
        output_path: lib/linkerd
    compile:
      - output_path: manifests/linkerd/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/linkerd
```

### Inventory Contract

All keys live under `parameters.generators.linkerd`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `servers.<name>` | Server | `<namespace>/<name>-server` |
| `server_authorizations.<name>` | ServerAuthorization | `<namespace>/<name>-serverauth` |
| `authorization_policies.<name>` | AuthorizationPolicy | `<namespace>/<name>-authpolicy` |
| `meshtls_authentications.<name>` | MeshTLSAuthentication | `<namespace>/<name>-meshtlsauth` |
| `network_authentications.<name>` | NetworkAuthentication | `<namespace>/<name>-networkauth` |
| `http_routes.<name>` | HTTPRoute | `<namespace>/<name>-httproute` |
| `service_profiles.<name>` | ServiceProfile | `<namespace>/<name>-serviceprofile` |

Every resource accepts `namespace`, `labels`, `annotations` and `spec`, and gets the label `name: <name>`; a Server also gets `server: <name>`. Precedence is generator defaults < `spec` < flat keys and shorthands: a flat key that overrides the same field in `spec` wins and logs a warning.

| Kind | Flat key | Renders to |
|---|---|---|
| Server | `selector_labels` | `spec.podSelector.matchLabels` |
| Server | `port` | `spec.port`, a number or a container port name |
| ServerAuthorization | `selector_labels` | `spec.server.selector.matchLabels` |
| ServerAuthorization | `client` | `spec.client` |
| AuthorizationPolicy | `target_ref` | `spec.targetRef`; a string names a Server |
| AuthorizationPolicy | `required_authentication_refs` | `spec.requiredAuthenticationRefs`; a string names an entry of `meshtls_authentications` or `network_authentications` |
| MeshTLSAuthentication | `identities` | `spec.identities` |
| MeshTLSAuthentication | `identity_refs` | `spec.identityRefs`; a string names a ServiceAccount |
| NetworkAuthentication | `networks` | `spec.networks`; a string is a CIDR |

HTTPRoute and ServiceProfile take `spec` verbatim. A ServiceProfile name must be the fully qualified name of its Service, such as `api.api-namespace.svc.cluster.local`.

A Server needs `selector_labels` or `spec.podSelector`; the compile fails otherwise, because an empty selector matches every pod in the namespace.

### Shorthands and defaults

| Input | Result |
|---|---|
| `target_ref: <name>` | `{group: policy.linkerd.io, kind: Server, name: <name>}` |
| `required_authentication_refs: [<name>]` | `{group: policy.linkerd.io, kind: MeshTLSAuthentication or NetworkAuthentication, name: <name>}`, plus `namespace` when the entry is in another namespace than the policy |
| `identity_refs: [<name>]` | `{kind: ServiceAccount, name: <name>}`, a ServiceAccount in the namespace of the MeshTLSAuthentication |
| `networks: [<cidr>]` | `{cidr: <cidr>}` |
| a `targetRef` or `requiredAuthenticationRefs` entry of kind `Server`, `MeshTLSAuthentication` or `NetworkAuthentication` without `group` | `group: policy.linkerd.io` |

Dicts pass through, for example `target_ref: {group: policy.linkerd.io, kind: HTTPRoute, name: x}`, `target_ref: {kind: Namespace, name: <namespace>}` or a `{kind: ServiceAccount, name: x}` authentication. A string in `required_authentication_refs` that matches no entry, or entries in both sections, fails the compile with `ValueError`.

The group default exists because Linkerd reads a missing `group` as the core API group ([`targets_kind`](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/policy-controller/k8s/api/src/policy.rs#L31-L48)). A `targetRef` of `{kind: Server, name: x}` then names no supported kind ([accepted kinds](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/policy-controller/k8s/index/src/inbound/authorization_policy.rs#L64-L108)), and the policy admission webhook rejects the AuthorizationPolicy ([admission](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/policy-controller/runtime/src/admission.rs#L248-L308)). The three kinds exist only in `policy.linkerd.io`; `HTTPRoute` also exists in `gateway.networking.k8s.io` and gets no group. The ServiceAccount reference resolves to the namespace of the MeshTLSAuthentication when `namespace` is unset ([identityRefs](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/policy-controller/k8s/index/src/inbound/meshtls_authentication.rs#L29)). The expanded forms are those of the [authorization policy reference](https://linkerd.io/2.20/reference/authorization-policy/).

Values the CRD or the controller already default are not emitted: Server `proxyProtocol` (`unknown`) and `accessPolicy` (`deny`), and the HTTPRoute `parentRefs` group, which the CRD defaults to `policy.linkerd.io` ([CRD](https://github.com/linkerd/linkerd2/blob/edge-26.10.1/charts/linkerd-crds/templates/policy/httproute.yaml#L2675)).

### Example

```yaml
parameters:
  generators:
    linkerd:
      namespace: booksapp
      servers:
        authors:
          selector_labels:
            app: authors
          port: service
      meshtls_authentications:
        webapp:
          identity_refs: [webapp]
      network_authentications:
        cluster-network:
          networks: [10.0.0.0/8]
      authorization_policies:
        authors-webapp:
          target_ref: authors
          required_authentication_refs: [webapp]
        authors-probes:
          target_ref: authors
          required_authentication_refs: [cluster-network]
      http_routes:
        authors-get:
          spec:
            parentRefs:
              - name: authors
                kind: Server
                group: policy.linkerd.io
            rules:
              - matches:
                  - path:
                      type: PathPrefix
                      value: /authors
                    method: GET
```

This renders `booksapp/authors-server`, `booksapp/webapp-meshtlsauth`, `booksapp/cluster-network-networkauth`, `booksapp/authors-webapp-authpolicy`, `booksapp/authors-probes-authpolicy` and `booksapp/authors-get-httproute`. Both AuthorizationPolicies target the Server with `group: policy.linkerd.io`, and `authors-webapp` requires the MeshTLSAuthentication `webapp`, which authenticates the `webapp` ServiceAccount.
