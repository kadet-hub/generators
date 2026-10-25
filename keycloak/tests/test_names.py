"""Unit tests of the keycloak generator (docs/specs/keycloak.md); command in the spec's implementation inventory."""

from box import Box

from .. import inv, main


def render(**sections):
    inv["parameters"] = Box(namespace="identity", generators={"keycloak": sections})
    return {key: obj.root.to_dict() for key, obj in main({}).root.items()}


def test_name_names_the_resource():
    out = render(
        instances={"keycloak": {"name": "sso"}},
        realm_imports={"keycloak-apps": {"name": "apps"}},
        oidc_clients={"keycloak-portal": {"name": "portal", "realm": "apps"}},
    )
    assert set(out) == {
        "identity/sso-keycloak",
        "identity/apps-keycloakrealmimport",
        "identity/portal-keycloakoidcclient",
    }
    assert out["identity/sso-keycloak"]["metadata"]["name"] == "sso"
    assert out["identity/sso-keycloak"]["metadata"]["labels"] == {"name": "sso"}
    assert "name" not in out["identity/sso-keycloak"]["spec"]
    assert out["identity/apps-keycloakrealmimport"]["spec"] == {"realm": {"realm": "apps"}, "keycloakCRName": "sso"}
    assert out["identity/portal-keycloakoidcclient"]["metadata"]["name"] == "portal"
    assert out["identity/portal-keycloakoidcclient"]["spec"]["keycloakCRName"] == "sso"


def test_key_names_the_resource_without_name():
    out = render(instances={"sso": {}}, realm_imports={"apps": {}})
    assert set(out) == {"identity/sso-keycloak", "identity/apps-keycloakrealmimport"}
    assert out["identity/apps-keycloakrealmimport"]["spec"] == {"realm": {"realm": "apps"}, "keycloakCRName": "sso"}


def test_same_name_fails():
    try:
        render(instances={"keycloak": {"name": "sso"}, "sso": {}})
    except ValueError as e:
        assert str(e) == "keycloak: instances 'keycloak' and 'sso' both render 'sso' in namespace 'identity'"
    else:
        raise AssertionError("two entries rendering one name compiled")
