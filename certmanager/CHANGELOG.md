# Changelog

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators. Existing inventories compile unchanged; the version restarts at 1.0.0.

New defaults and shorthands, each documented in the README with its upstream source:

- Certificates get `privateKey.rotationPolicy: Always` unless `spec` sets it. This changes the output of existing inventories by that one field.
- Issuers and ClusterIssuers accept `letsencrypt: production|staging`, `email` and `http01_ingress_class`, which expand to `spec.acme`; an issuer needs `spec` or `letsencrypt`.
- Precedence: generator defaults, then `spec` (`certificate` for `ca_issuers`), then shorthands. A shorthand wins over the same field in `spec` and logs a warning.
- ACME issuers without `privateKeySecretRef` get `<name>-account-key`.
- `ca_issuers.<name>` renders the SelfSigned ClusterIssuer, the ECDSA P-256 root Certificate in `cert-manager` and the CA ClusterIssuer; a clash with another entry's output key fails the compile.

Ships the upstream CRD schemas of cert-manager 1.21.2 and trust-manager 0.25.0 under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
