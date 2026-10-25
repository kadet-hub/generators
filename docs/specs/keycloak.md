# keycloak generator

Status: Draft
Code: `keycloak/`, `conftest.py`
Verified against: main @ 0011e4c

## Problem and decision

The keycloak generator had no spec. Its behaviour is described in
`keycloak/README.md` and the CHANGELOG. This spec starts with the resource
names, which a recipe in kadet-hub/recipes could not set. Other behaviour
moves in here when a change touches it.

Every entry renders one resource named after its key. kadet-hub/recipes
lets a recipe write only keys below its own name (RCP-18 there), so its
`keycloak` recipe could only render a Keycloak named `keycloak*`. The
kadet-hub/examples recipe it replaces names the Keycloak `sso`. The
Keycloak Operator names the StatefulSet `sso`, the Services `sso-service`
and `sso-discovery` and the Secret `sso-initial-admin` after it, and
clients in the cluster reach Keycloak as `sso-service`. A target that
moves to the recipe keeps these names only if the Keycloak keeps its name.

## Resource names

- KC-1: An entry of `instances`, `realm_imports`, `oidc_clients` or
  `saml_clients` with `name` MUST render its resource with that name and
  write it to `<namespace>/<name>-<kind>`. An entry without `name` MUST
  keep the name of its key.

  The defaults that come from the resource's name follow `name`: the
  `realm.realm` of a realm import, and the `keycloakCRName` of a realm
  import or client, which names the only Keycloak of its namespace by that
  Keycloak's name. The operator takes the name of a KeycloakOIDCClient or
  KeycloakSAMLClient as the client's `clientId`.

  - Test: `keycloak/tests/test_names.py::test_name_names_the_resource`,
    `::test_key_names_the_resource_without_name`; fixture target `complete`
  - Since: #113

- KC-2: Two entries of one section that render the same name in the same
  namespace MUST fail the compile, naming both keys.

  Before, the later one would have replaced the earlier output file.

  - Test: `keycloak/tests/test_names.py::test_same_name_fails`
  - Since: #113

DEC-1: The name is a key of the entry, as for every entry of the
cloudnative-pg generator (CNPG-1) and the custom resource sections of the
rabbitmq generator (RMQ-1). Letting kadet-hub/recipes accept the examples
recipe's names was rejected for the reason DEC-1 of the cloudnative-pg
spec gives.

The unit tests need a target before the package loads, which `conftest.py`
at the repository root registers (rabbitmq spec, DEC-1).

## Implementation inventory

| Item | Value |
|---|---|
| Resource names | `keycloak/__init__.py` (`main`) |
| Unit tests | `keycloak/tests/test_names.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider keycloak/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `keycloak/tests/fixtures`, targets `minimal` and `complete` |
