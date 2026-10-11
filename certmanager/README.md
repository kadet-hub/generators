# cert-manager Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/certmanager/) page.

Kapitan kadet generator for [cert-manager](https://cert-manager.io/) and [trust-manager](https://cert-manager.io/docs/trust/trust-manager/) resources. Built for cert-manager 1.21.2 (`cert-manager.io/v1`) and trust-manager 0.25.0 (`trust.cert-manager.io/v1alpha1`):

- **Certificate**: requests a certificate from an Issuer or ClusterIssuer and stores it in a Secret
- **Issuer**: namespaced certificate authority (ACME, CA, self-signed, Vault, ...)
- **ClusterIssuer**: cluster-scoped certificate authority
- **Bundle**: trust-manager CA bundle synced into ConfigMaps or Secrets across namespaces

Short entries expand to the settings cert-manager and Let's Encrypt recommend: Certificates rotate their private key, Let's Encrypt issuers get the right directory URL, their own account key and an HTTP01 solver bound to one ingress class, and one `ca_issuers` entry bootstraps a private CA. The CA key Secrets and solver credentials belong in the `kubernetes` or `external-secrets` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/certmanager@sha256:<digest>
        output_path: lib/certmanager
    compile:
      - output_path: manifests/cert-manager/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/certmanager
```

### Inventory Contract

All keys live under `parameters.generators.certmanager`. Without that block the generator renders nothing.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace for Certificates and Issuers. Falls back to `parameters.namespace`, then `default`. |
| `certs.<name>` | Certificate | `<namespace>/<name>-cert` |
| `issuers.<name>` | Issuer | `<namespace>/<name>-issuer` |
| `clusterissuers.<name>` | ClusterIssuer | `<name>-cissuer` |
| `bundles.<name>` | Bundle | `<name>-bundle` |
| `ca_issuers.<name>` | ClusterIssuer, Certificate, ClusterIssuer | `<name>-selfsigned-cissuer`, `<namespace>/<name>-cert`, `<name>-cissuer` |

Every entry accepts these keys:

| Key | Description |
|---|---|
| `spec` | The resource `spec`, passed through. Required for Certificates and Bundles; Issuers and ClusterIssuers need `spec` or `letsencrypt`. |
| `name` | Overrides the map key in `metadata.name` and in the output key. |
| `namespace` | Certificate, Issuer and `ca_issuers` only. ClusterIssuer and Bundle are cluster-scoped; a Bundle selects its target namespaces in `spec.target.namespaceSelector`. |
| `type` | Entries without `type` or with `type: certmanager` render; any other value skips the entry, for resources managed elsewhere. |

### Defaults and shorthands

Precedence is generator defaults, then `spec` (`certificate` for `ca_issuers`), then shorthands: a shorthand wins over the same field in `spec` and logs a warning, and both win over the defaults; maps merge, lists and values replace.

| Applies to | Input | Output | Source |
|---|---|---|---|
| Certificate | always | `privateKey.rotationPolicy: Always` | [Rotation of the private key](https://cert-manager.io/docs/usage/certificate/#rotation-private-key): recommended on every Certificate. The controller default since 1.18 sits behind a feature gate ([1.18 release notes](https://cert-manager.io/docs/releases/release-notes/release-notes-1.18/#the-default-value-of-certificatespecprivatekeyrotationpolicy-is-now-always)), so the generator sets it explicitly. |
| Issuer, ClusterIssuer | `letsencrypt: production` or `staging` | `acme.server`: `https://acme-v02.api.letsencrypt.org/directory` or `https://acme-staging-v02.api.letsencrypt.org/directory` | [Let's Encrypt ACME endpoints](https://letsencrypt.org/docs/acme-protocol-updates/), [staging environment](https://letsencrypt.org/docs/staging-environment/) |
| Issuer, ClusterIssuer | `email: <address>` | `acme.email` | [ACME issuer](https://cert-manager.io/docs/configuration/acme/#creating-a-basic-acme-issuer) |
| Issuer, ClusterIssuer | `http01_ingress_class: <class>` | `acme.solvers: [{http01: {ingress: {ingressClassName: <class>}}}]` | [HTTP01 `ingressClassName`](https://cert-manager.io/docs/configuration/acme/http01/#ingressclassname): the recommended field; without a class every ingress controller serves the challenge. |
| Issuer, ClusterIssuer with `acme` | no `privateKeySecretRef` | `acme.privateKeySecretRef.name: <name>-account-key` | Any name works ([ACME issuer](https://cert-manager.io/docs/configuration/acme/#creating-a-basic-acme-issuer)); one Secret per issuer keeps staging and production apart, since Let's Encrypt accounts are scoped per environment ([staging environment](https://letsencrypt.org/docs/staging-environment/)). |

A `ca_issuers.<name>` entry renders the [SelfSigned bootstrap of a CA issuer](https://cert-manager.io/docs/configuration/selfsigned/#bootstrapping-ca-issuers):

- ClusterIssuer `<name>-selfsigned` with `selfSigned: {}`.
- Certificate `<name>` with `isCA: true`, `commonName` from `common_name` (default `<name>`), `secretName: <name>`, an ECDSA P-256 key and `issuerRef` to `<name>-selfsigned`. `certificate` overrides fields of this spec, for example `duration`, `subject` or `privateKey.size`.
- ClusterIssuer `<name>` with `ca.secretName` set to the Certificate's `secretName`. Certificates reference this one.

The Certificate goes to `namespace`, default `cert-manager`: a ClusterIssuer reads its Secret from the controller's [cluster resource namespace](https://cert-manager.io/docs/configuration/ca/#deployment), so set `namespace` only when `--cluster-resource-namespace` differs. The root renews on cert-manager's schedule with a new key; distribute trust from a copy of the root in a separate ConfigMap, as trust-manager [recommends](https://cert-manager.io/docs/trust/trust-manager/#cert-manager-integration-intentionally-copying-ca-certificates), not from the CA Secret.

Controller defaults are not emitted: `duration` 90 days, renewal at two thirds of the lifetime, `revisionHistoryLimit: 1`, the default key usages and an RSA 2048 key for leaf certificates ([Certificate resource](https://cert-manager.io/docs/usage/certificate/#reissuance-triggered-by-expiry-renewal)).

The compile fails with `ValueError: certmanager ...` when an entry lacks `spec` (or `letsencrypt` for issuers), `letsencrypt` is neither `production` nor `staging`, or a `ca_issuers` resource has the same output key as another entry.

### Example

```yaml
parameters:
  namespace: apps
  generators:
    certmanager:
      ca_issuers:
        internal-ca:
          common_name: Internal Root CA
      clusterissuers:
        letsencrypt-staging:
          letsencrypt: staging
          email: platform-team@example.com
          http01_ingress_class: nginx
        letsencrypt-prod:
          letsencrypt: production
          email: platform-team@example.com
          http01_ingress_class: nginx
      certs:
        api-tls:
          spec:
            secretName: api-tls
            issuerRef:
              name: letsencrypt-prod
              kind: ClusterIssuer
            dnsNames:
              - api.example.com
        orders-db-tls:
          spec:
            secretName: orders-db-tls
            issuerRef:
              name: internal-ca
              kind: ClusterIssuer
            dnsNames:
              - orders-db.apps.svc
      bundles:
        internal-ca-bundle:
          spec:
            sources:
              - useDefaultCAs: true
              - configMap:
                  name: internal-ca-root
                  key: ca.crt
            target:
              configMap:
                key: ca-bundle.crt
              namespaceSelector:
                matchLabels:
                  trust-internal-ca: "true"
```

This renders `internal-ca-selfsigned-cissuer`, `cert-manager/internal-ca-cert`, `internal-ca-cissuer`, `letsencrypt-staging-cissuer`, `letsencrypt-prod-cissuer`, `apps/api-tls-cert`, `apps/orders-db-tls-cert` and `internal-ca-bundle-bundle`. The `internal-ca-root` ConfigMap holds the copied root.
