# Changelog

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Keycloak Operator 26.8.0. Ships the Apache-2.0 CRD schemas of this release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Emits `k8s.keycloak.org/v2beta1` instead of `v2alpha1`. At 26.8.0 `v2beta1` is the storage version and `v2alpha1` is deprecated; both have the same schema, so only `apiVersion` changes.
- Breaking: a Keycloak without `instances` no longer emits `instances: 1`. The operator default is also 1, and the emitted value overrode `kubectl scale` and HPAs on every apply. To keep the old output, set `instances: 1` on the entry.
- Breaking: `cache.config_file` and realm import `resource_type` are removed. They rendered `configFile` and `resourceType`, which the CRD does not define; `resource_type` is now ignored and `cache.config_file` passes through like any unmodelled section key, so QA-7 rejects it. Use `cache.config_map_file`.
- New: `oidc_clients` and `saml_clients` render KeycloakOIDCClient and KeycloakSAMLClient (`k8s.keycloak.org/v2alpha1`, upstream alpha). The generator adds nothing to `client`.
- New defaults and shorthand, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands.
  - A realm import without `realm.realm` takes the entry key as realm name.
  - A realm import or client without `keycloak_cr_name` references the only Keycloak instance in its namespace.
  - `db.credentials_secret: <name>` sets `usernameSecret` and `passwordSecret` to the keys `username` and `password` of that Secret.
- A section key that overrides `spec` now logs "Flat key '<section>.<key>' overrides spec passthrough '<section>.<field>' for resource '<name>'", the wording of the other kadet-hub generators.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
