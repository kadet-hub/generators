# Changelog

## 1.0.2

Built for Linkerd `edge-26.10.1`. The `linkerd-crds` chart is unchanged since `edge-26.6.3`, so the shipped schemas and the rendered output stay the same.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Linkerd 2.20 (`edge-26.6.3`). Ships the CRD schemas of that release under `schemas/`, taken from the `linkerd-crds` chart instead of the CRDs catalog; the kadet-hub gate validates the compiled output against them (QA-7).
- New flat keys and shorthands, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
  - AuthorizationPolicy `target_ref: <server>` and `required_authentication_refs: [<name>]`, which resolves names against the generator's own `meshtls_authentications` and `network_authentications`.
  - MeshTLSAuthentication `identities` and `identity_refs: [<service account>]`.
  - NetworkAuthentication `networks: [<cidr>]`.
- AuthorizationPolicy refs of kind `Server`, `MeshTLSAuthentication` or `NetworkAuthentication` without `group` get `group: policy.linkerd.io`, also in `spec`. Before, Linkerd read them as core group refs and rejected the policy.
- Server and HTTPRoute are emitted as `policy.linkerd.io/v1beta3`, the storage versions; Server `v1beta1` is deprecated upstream and HTTPRoute `v1beta3` only adds `timeouts`. The inventory keys and shorthands are unchanged.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
