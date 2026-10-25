# Keycloak Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/keycloak/) page.

Built for Keycloak Operator 26.8.1. Keycloak and KeycloakRealmImport are emitted as `k8s.keycloak.org/v2beta1`, their storage version; `v2alpha1` of these kinds is still served but deprecated. KeycloakOIDCClient and KeycloakSAMLClient exist only as `v2alpha1` (served, storage, not deprecated) and are an upstream alpha (preview) API. The bundled JSON Schemas are Apache-2.0, derived from the [upstream CRDs](https://github.com/keycloak/keycloak-k8s-resources/tree/26.8.1/kubernetes).

Kapitan kadet generator for the Keycloak Operator:

- **Keycloak**: a Keycloak server with database, hostname, TLS, ingress, cache, features and scheduling
- **KeycloakRealmImport**: a realm created on import, with clients, client scopes, roles, groups and identity providers declared as maps that merge across classes
- **KeycloakOIDCClient**, **KeycloakSAMLClient** (upstream alpha): clients the operator creates, updates and deletes through the Admin API v2

The database, the TLS Secret and the database credentials Secret belong in other generators or operators (for example CloudNativePG and cert-manager).

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/keycloak@sha256:<digest>
        output_path: lib/keycloak
    compile:
      - output_path: manifests/keycloak/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/keycloak
```

## Inventory contract

All keys live under `parameters.generators.keycloak`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `instances.<name>` | Keycloak | `<namespace>/<name>-keycloak` |
| `realm_imports.<name>` | KeycloakRealmImport | `<namespace>/<name>-keycloakrealmimport` |
| `oidc_clients.<name>` | KeycloakOIDCClient | `<namespace>/<name>-keycloakoidcclient` |
| `saml_clients.<name>` | KeycloakSAMLClient | `<namespace>/<name>-keycloaksamlclient` |

Every entry accepts `namespace`, `labels`, `annotations`, `spec` and `name`, which names the resource and its output key in place of the entry key. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides a `spec` value logs a warning.

### Keycloak

| Key | CRD field |
|---|---|
| `instances` | `instances` |
| `image`, `image_pull_secrets` | `image`, `imagePullSecrets` |
| `additional_options` | `additionalOptions` |
| `proxy`, `unsupported` | `proxy`, `unsupported`, verbatim |
| `db` | `db`: `vendor`, `host`, `port`, `database`, `schema`, `url`, `pool_initial_size`, `pool_min_size`, `pool_max_size`, `username_secret`, `password_secret`, `credentials_secret` |
| `hostname` | `hostname`: `hostname`, `admin`, `admin_url`, `strict`, `strict_backchannel`, `backchannel_dynamic` |
| `http` | `http`: `http_enabled`, `http_port`, `https_port`, `tls_secret` |
| `ingress` | `ingress`: `enabled`, `class_name`, `annotations` |
| `features` | `features`: `enabled`, `disabled` |
| `transaction` | `transaction`: `xa_enabled` |
| `cache` | `cache`: `config_map_file` |
| `resources` | `resources`: `requests`, `limits` |
| `scheduling` | `scheduling`: `affinity`, `tolerations`, `priority_class_name` |

Section keys are the snake_case spelling of the CRD field. Other keys inside a section, for example `scheduling.topologySpreadConstraints` or `http.serviceName`, pass through verbatim. Fields without a flat key, such as `startOptimized`, `bootstrapAdmin`, `truststores` or `networkPolicy`, go into `spec`.

### KeycloakRealmImport

| Key | CRD field |
|---|---|
| `keycloak_cr_name` | `keycloakCRName` |
| `realm` | `realm`, a full [RealmRepresentation](https://www.keycloak.org/docs-api/latest/rest-api/index.html#RealmRepresentation) |
| `clients.<clientId>`, `client_scopes.<name>`, `roles.realm.<name>`, `roles.client.<clientId>.<name>`, `groups.<name>`, `identity_providers.<alias>` | `realm.clients`, `realm.clientScopes`, `realm.roles`, `realm.groups`, `realm.identityProviders` |

The maps are keyed by the entry's identifier and merge across Kapitan classes, so a class can add one client without repeating the others. Lists are sorted by identifier. An entry whose identifier already exists in `realm` merges into it and the map wins with a warning. Entry keys in snake_case map to camelCase:

| Map | Flat keys |
|---|---|
| `clients` | `admin_url`, `base_url`, `bearer_only`, `client_authenticator_type`, `consent_required`, `default_client_scopes`, `direct_access_grants_enabled`, `frontchannel_logout`, `full_scope_allowed`, `implicit_flow_enabled`, `optional_client_scopes`, `protocol_mappers`, `public_client`, `redirect_uris`, `root_url`, `service_accounts_enabled`, `standard_flow_enabled`, `web_origins` |
| `client_scopes` | `protocol_mappers` |
| `groups` | `realm_roles`, `client_roles`, `sub_groups` (a map of nested groups) |
| `identity_providers` | `display_name`, `first_broker_login_flow_alias`, `hide_on_login`, `link_only`, `post_broker_login_flow_alias`, `provider_id`, `store_token`, `trust_email` |

`secret_ref` on a client and `client_secret_ref` on an identity provider take a Secret key reference. They render `secret: ${CLIENT_SECRET_<clientId>}` or `config.clientSecret: ${IDP_CLIENT_SECRET_<alias>}` and add the matching [`spec.placeholders`](https://github.com/keycloak/keycloak/blob/26.8.1/docs/guides/operator/realm-import.adoc) entry, so the secret reaches neither the inventory nor the compiled manifest. Names are upper-cased with other characters as `_`; two refs that resolve to the same name with different Secrets fail the compile. Users are not modelled; user credentials or client secrets written into `realm` log a warning.

The operator only creates realms that do not exist yet; it never updates or deletes them.

### KeycloakOIDCClient and KeycloakSAMLClient

| Key | CRD field |
|---|---|
| `keycloak_cr_name` | `keycloakCRName` |
| `realm` | `realm`, the realm the client lives in |
| `client` | `client`, verbatim: the Admin API v2 client representation, for example `loginFlows`, `redirectUris`, `webOrigins` and `auth` (OIDC) or `nameIdFormat`, `signDocuments`, `signAssertions` (SAML) |

The entry key becomes `metadata.name`, which the operator uses as `clientId`. `clientId`, `realm` and `keycloakCRName` [cannot change after creation](https://github.com/keycloak/keycloak/blob/26.8.1/docs/guides/operator/managing-clients.adoc). `client` replaces `spec.client` as a whole, it is not merged.

The generator adds nothing to `client`: no secret, no `loginFlows`, no redirect URIs or web origins, so public clients, wildcard redirects and direct access grants exist only when the inventory writes them. A confidential client references its secret with `client.auth.secretRef`; that Secret needs the label `operator.keycloak.org/kind: KeycloakOIDCClient` and comes from elsewhere.

The guide's prerequisites are not defaulted either: the referenced Keycloak needs `features.enabled: [client-admin-api:v2]`, and the operator reads admin client credentials from the Secret `<keycloak_cr_name>-admin` (keys `client-id`, `client-secret`), which has to be created during admin bootstrap. Anyone who can write these CRs can do what those admin credentials allow.

### Defaults and shorthands

| Input | Result | Source |
|---|---|---|
| `db.credentials_secret: <name>` | `usernameSecret: {name: <name>, key: username}`, `passwordSecret: {name: <name>, key: password}` | the keys of a [`kubernetes.io/basic-auth`](https://kubernetes.io/docs/concepts/configuration/secret/#basic-authentication-secret) Secret, as in the operator's [basic deployment](https://github.com/keycloak/keycloak/blob/26.8.1/docs/guides/operator/basic-deployment.adoc); `username_secret` and `password_secret` win |
| realm import without `realm.realm` | `realm.realm: <entry key>` | the operator [names the import Secret after it](https://github.com/keycloak/keycloak/blob/26.8.1/operator/src/main/java/org/keycloak/operator/controllers/KeycloakRealmImportSecretDependentResource.java) |
| realm import or client without `keycloak_cr_name` | `keycloakCRName` of the only Keycloak in `instances` with the same namespace | required by all three CRDs; the operator [looks it up in the resource's namespace](https://github.com/keycloak/keycloak/blob/26.8.1/operator/src/main/java/org/keycloak/operator/controllers/KeycloakRealmImportController.java) |

With zero or several instances in the namespace, `keycloak_cr_name` stays unset and the resource fails QA-7 at compile time until the inventory names one. A client's `realm` has no default: QA-7 fails without it.

The operator's basic deployment guide lists a database, a hostname and a TLS certificate as prerequisites. The generator defaults none of them, sets no admin password, and never turns off `hostname.strict` or turns on `http.http_enabled`: each of these weakens or bypasses authentication, so the inventory has to opt in. The CRD marks none of them required, so QA-7 does not catch a missing one. `proxy.headers` is not defaulted either; the guide warns that forwarded headers can be spoofed unless network policies restrict the HTTP port. The operator creates the initial admin in the Secret `<name>-initial-admin` with a generated password.

`instances` is emitted only when set. The [operator default](https://github.com/keycloak/keycloak/blob/26.8.1/operator/src/main/java/org/keycloak/operator/crds/v2beta1/deployment/KeycloakSpec.java) is 1, and leaving it out lets `kubectl scale` or an HPA own the replica count.

## Example

```yaml
parameters:
  namespace: identity
  generators:
    keycloak:
      instances:
        sso:
          instances: 3
          db:
            vendor: postgres
            host: keycloak-db-rw
            database: app
            credentials_secret: keycloak-db-app
          hostname:
            hostname: sso.example.com
          http:
            tls_secret: sso-tls
          ingress:
            class_name: nginx
            annotations:
              nginx.ingress.kubernetes.io/backend-protocol: HTTPS
              nginx.ingress.kubernetes.io/ssl-passthrough: "true"
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              memory: 2Gi
      realm_imports:
        apps:
          realm:
            enabled: true
            sslRequired: external
            bruteForceProtected: true
          clients:
            portal:
              public_client: true
              redirect_uris:
                - https://portal.example.com/*
              web_origins:
                - https://portal.example.com
              attributes:
                pkce.code.challenge.method: S256
            orders-api:
              standard_flow_enabled: false
              service_accounts_enabled: true
              secret_ref:
                name: orders-api-oidc
                key: client-secret
          roles:
            realm:
              admin:
                description: Administrator role
          groups:
            platform:
              realm_roles:
                - admin
```

This renders `identity/sso-keycloak` and `identity/apps-keycloakrealmimport`; the import gets `realm: apps` and `keycloakCRName: sso` from the defaults above.

`tests/fixtures/inventory/targets/complete.yml` covers every section, two instances in one namespace with an explicit `keycloak_cr_name`, Secret refs, OIDC and SAML clients and flat keys overriding `spec`.
