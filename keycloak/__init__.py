"""Keycloak generator for Kapitan.

Generates Keycloak Operator resources for identity and access management:
- Keycloak: Deploy Keycloak server instances
- KeycloakRealmImport: Import realm configurations with clients, users, roles
- KeycloakOIDCClient, KeycloakSAMLClient: operator-managed clients (v2alpha1)

Schema reference: k8s.keycloak.org/v2beta1 (clients v2alpha1)
See: https://www.keycloak.org/guides#operator

BACKEND COMPATIBILITY
─────────────────────
The generator must work with ALL valid Kapitan inventory backends:
  - reclass / reclass-rs  → plain Python dicts
  - omegaconf             → OmegaConf DictConfig / ListConfig

RULES for inventory access:
  1. Always use `.get("key", default)` — never direct attribute access.
  2. Always call `_convert_to_dict()` on nested values before passing
     them to resource classes or mutating them.
"""

__version__ = "1.0.2"

import logging
import re
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


inv = inventory()
logger = logging.getLogger(__name__)


# ─── Helpers ───────────────────────────────────────────────────────────────


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj / OmegaConf objects to plain Python dicts."""
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        from omegaconf import OmegaConf

        return _convert_to_dict(OmegaConf.to_container(obj, resolve=True))
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "root"):
        return _convert_to_dict(obj.root)
    if isinstance(obj, dict):
        return {k: _convert_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_to_dict(item) for item in obj]
    return obj


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge any user-supplied ``spec`` dict into *spec_target*."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when flat keys will override passthrough values from ``spec``."""
    spec = _convert_to_dict(config.get("spec")) or {}
    if not spec:
        return
    flat = _convert_to_dict(config)
    for flat_key, crd_key in mapping.items():
        flat_value, spec_value = flat, spec
        for part in flat_key.split("."):
            flat_value = flat_value.get(part) if isinstance(flat_value, dict) else None
        for part in crd_key.split("."):
            spec_value = spec_value.get(part) if isinstance(spec_value, dict) else None
        if flat_value is not None and spec_value is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set ``target[target_key]`` from ``config[source_key]`` when it is not None."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _convert_to_dict(value)


class KeycloakBase(k8s.Base):
    """Base class for Keycloak resources with common patterns."""

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", self.kwargs.get("default_namespace", "default"))

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Add common metadata fields from config."""
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))

    def _set_refs(
        self, target: BaseObj, config: dict, source_key: str, *, target_key: str
    ) -> None:
        """Set LocalObjectReference list field with auto-wrapping.

        Supports both string list (auto-wrapped) and pre-wrapped format.
        """
        refs = config.get(source_key)
        if refs:
            refs = _convert_to_dict(refs)
            if isinstance(refs, list) and refs and isinstance(refs[0], str):
                target[target_key] = [{"name": ref} for ref in refs]
            else:
                target[target_key] = refs


class Keycloak(KeycloakBase):
    """Keycloak instance resource.

    Deploys a Keycloak server with configurable database, hostname, HTTP settings,
    ingress, resources, and features.

    Required kwargs:
        name: Resource name.
        config: Keycloak configuration dictionary.

    Smart defaults:
        - namespace: Inherits from parameters.namespace

    Example minimal config:
        {
            'hostname': {
                'hostname': 'keycloak.example.com'
            }
        }
    """

    _FLAT_KEY_MAP = {
        "instances": "instances",
        "image": "image",
        "image_pull_secrets": "imagePullSecrets",
        "additional_options": "additionalOptions",
        "proxy": "proxy",
        "unsupported": "unsupported",
    }

    # Section -> {snake_case inventory key: CRD field}
    _SECTION_KEY_MAP = {
        "db": {
            "vendor": "vendor",
            "host": "host",
            "port": "port",
            "database": "database",
            "schema": "schema",
            "url": "url",
            "pool_initial_size": "poolInitialSize",
            "pool_max_size": "poolMaxSize",
            "pool_min_size": "poolMinSize",
            "username_secret": "usernameSecret",
            "password_secret": "passwordSecret",
        },
        "hostname": {
            "hostname": "hostname",
            "admin": "admin",
            "admin_url": "adminUrl",
            "strict": "strict",
            "strict_backchannel": "strictBackchannel",
            "backchannel_dynamic": "backchannelDynamic",
        },
        "http": {
            "http_enabled": "httpEnabled",
            "http_port": "httpPort",
            "https_port": "httpsPort",
            "tls_secret": "tlsSecret",
        },
        "ingress": {
            "enabled": "enabled",
            "class_name": "className",
            "annotations": "annotations",
        },
        "features": {"enabled": "enabled", "disabled": "disabled"},
        "transaction": {"xa_enabled": "xaEnabled"},
        "cache": {"config_map_file": "configMapFile"},
        "resources": {"requests": "requests", "limits": "limits"},
        "scheduling": {
            "affinity": "affinity",
            "tolerations": "tolerations",
            "priority_class_name": "priorityClassName",
        },
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "k8s.keycloak.org/v2beta1"
        self.kwargs.kind = "Keycloak"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)

        spec = self.root.spec

        # 1. Passthrough
        _merge_spec_passthrough(spec, config)

        # 2. Collision warnings
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # 3. Explicit abstractions — flat keys take precedence over passthrough
        _set_field(spec, config, "instances", target_key="instances")

        # Image configuration
        _set_field(spec, config, "image", target_key="image")
        _set_field(spec, config, "image_pull_secrets", target_key="imagePullSecrets")

        # Additional server options, proxy and unsupported pod template
        _set_field(spec, config, "additional_options", target_key="additionalOptions")
        _set_field(spec, config, "proxy", target_key="proxy")
        _set_field(spec, config, "unsupported", target_key="unsupported")

        # Sections: snake_case keys map to CRD fields, other keys pass through
        for section, key_map in self._SECTION_KEY_MAP.items():
            section_config = _convert_to_dict(config.get(section))
            if section == "db" and section_config and section_config.get("credentials_secret"):
                # Shorthand for one Secret with the keys of kubernetes.io/basic-auth
                section_config = dict(section_config)
                secret = section_config.pop("credentials_secret")
                section_config.setdefault("username_secret", {"name": secret, "key": "username"})
                section_config.setdefault("password_secret", {"name": secret, "key": "password"})
            if section_config:
                self._build_section(section, section_config, key_map)

    def _build_section(self, section: str, section_config: dict, key_map: dict) -> None:
        """Merge unmodelled section keys verbatim, then set modelled keys."""
        target = self.root.spec[section]
        for key, value in section_config.items():
            if key not in key_map:
                target[key] = value
        for key, crd_key in key_map.items():
            value = section_config.get(key)
            if value is None:
                continue
            if crd_key in target:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    f"{section}.{key}",
                    f"{section}.{crd_key}",
                    self.kwargs.name,
                )
            target[crd_key] = value


def _warn_plaintext_credentials(name: str, realm: dict) -> None:
    """Warn when a realm import carries credentials in plain manifests.

    Realm JSON is emitted verbatim into compiled output; user credentials
    and client secrets belong in kapitan secret refs or external secret
    management, not in the inventory.
    """
    for user in realm.get("users") or []:
        if isinstance(user, dict) and user.get("credentials"):
            logger.warning(
                "keycloak realm import '%s': user '%s' carries plaintext "
                "credentials in the compiled manifest",
                name,
                user.get("username", "<unknown>"),
            )
    for client in realm.get("clients") or []:
        if isinstance(client, dict) and client.get("secret"):
            logger.warning(
                "keycloak realm import '%s': client '%s' carries a plaintext "
                "secret in the compiled manifest",
                name,
                client.get("clientId", "<unknown>"),
            )


# Realm content maps: snake_case entry key -> representation field.
_CLIENT_KEY_MAP = {
    "admin_url": "adminUrl",
    "base_url": "baseUrl",
    "bearer_only": "bearerOnly",
    "client_authenticator_type": "clientAuthenticatorType",
    "consent_required": "consentRequired",
    "default_client_scopes": "defaultClientScopes",
    "direct_access_grants_enabled": "directAccessGrantsEnabled",
    "frontchannel_logout": "frontchannelLogout",
    "full_scope_allowed": "fullScopeAllowed",
    "implicit_flow_enabled": "implicitFlowEnabled",
    "optional_client_scopes": "optionalClientScopes",
    "protocol_mappers": "protocolMappers",
    "public_client": "publicClient",
    "redirect_uris": "redirectUris",
    "root_url": "rootUrl",
    "service_accounts_enabled": "serviceAccountsEnabled",
    "standard_flow_enabled": "standardFlowEnabled",
    "web_origins": "webOrigins",
}
_CLIENT_SCOPE_KEY_MAP = {"protocol_mappers": "protocolMappers"}
_GROUP_KEY_MAP = {
    "client_roles": "clientRoles",
    "realm_roles": "realmRoles",
    "sub_groups": "subGroups",
}
_IDENTITY_PROVIDER_KEY_MAP = {
    "display_name": "displayName",
    "first_broker_login_flow_alias": "firstBrokerLoginFlowAlias",
    "hide_on_login": "hideOnLogin",
    "link_only": "linkOnly",
    "post_broker_login_flow_alias": "postBrokerLoginFlowAlias",
    "provider_id": "providerId",
    "store_token": "storeToken",
    "trust_email": "trustEmail",
}


def _realm_entry(
    id_key: str, ident: str, config: Any, key_map: dict, label: str
) -> dict:
    """Build one representation entry: identifier from the map key, unmodelled
    keys verbatim, then flat keys mapped (a flat key wins and warns)."""
    config = _convert_to_dict(config) or {}
    entry = {id_key: ident}
    entry.update((k, v) for k, v in config.items() if k not in key_map)
    entry[id_key] = ident
    for key, crd_key in key_map.items():
        if config.get(key) is None:
            continue
        if crd_key in entry:
            logger.warning(
                "Flat key '%s' overrides '%s' for %s '%s'", key, crd_key, label, ident
            )
        entry[crd_key] = config[key]
    return entry


def _group_entry(name: str, config: Any, label: str) -> dict:
    entry = _realm_entry("name", name, config, _GROUP_KEY_MAP, label)
    if isinstance(entry.get("subGroups"), dict):
        entry["subGroups"] = [
            _group_entry(sub, sub_config, label)
            for sub, sub_config in sorted(entry["subGroups"].items())
        ]
    return entry


def _merge_named(items: list, entries: list, id_key: str, label: str) -> list:
    """Return *items* with *entries* merged in by identifier; entries win per field."""
    merged = list(items)
    index = {
        item.get(id_key): i for i, item in enumerate(merged) if isinstance(item, dict)
    }
    for entry in entries:
        i = index.get(entry[id_key])
        if i is None:
            merged.append(entry)
            continue
        overridden = sorted(k for k in entry if k != id_key and k in merged[i])
        if overridden:
            logger.warning(
                "%s '%s' overrides realm fields %s", label, entry[id_key], overridden
            )
        merged[i] = {**merged[i], **entry}
    return merged


class KeycloakRealmImport(KeycloakBase):
    """KeycloakRealmImport resource for importing realm configurations.

    Imports realm configurations including clients, users, roles, groups,
    identity providers, and authentication flows into a Keycloak instance.

    Required kwargs:
        name: Resource name.
        config: KeycloakRealmImport configuration dictionary.

    Smart defaults:
        - namespace: Inherits from parameters.namespace
        - realm.realm: the resource name
        - keycloakCRName: the only Keycloak instance in the same namespace

    Example minimal config:
        {
            'keycloak_cr_name': 'my-keycloak',
            'realm': {
                'realm': 'my-realm',
                'enabled': True
            }
        }
    """

    _FLAT_KEY_MAP = {
        "keycloak_cr_name": "keycloakCRName",
        "realm": "realm",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "k8s.keycloak.org/v2beta1"
        self.kwargs.kind = "KeycloakRealmImport"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)

        spec = self.root.spec

        # 1. Passthrough
        _merge_spec_passthrough(spec, config)

        # 2. Collision warnings
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # 3. Explicit abstractions — flat keys take precedence over passthrough
        keycloak_cr_name = config.get("keycloak_cr_name")
        if keycloak_cr_name:
            spec.keycloakCRName = keycloak_cr_name

        if config.get("realm"):
            realm = _convert_to_dict(config["realm"])
            _warn_plaintext_credentials(self.kwargs.name, realm)
            spec.realm = realm

        # 4. Realm content maps, merged into the realm representation
        self._build_realm_content(spec, config)

        # 5. Generator defaults, applied only when neither spec nor flat keys set them.
        # The operator names the import Secret after realm.realm and looks up
        # keycloakCRName in the import's namespace.
        realm = dict(_convert_to_dict(spec.realm)) if "realm" in spec else {}
        if not realm.get("realm"):
            spec.realm = {"realm": self.kwargs.name, **realm}
        default_cr = self.kwargs.get("default_keycloak_cr_name")
        if default_cr and not spec.get("keycloakCRName"):
            spec.keycloakCRName = default_cr

    def _build_realm_content(self, spec: Any, config: dict) -> None:
        """Render the keyed realm content maps into ``spec.realm`` lists."""
        content = {
            key: _convert_to_dict(config.get(key)) or {}
            for key in (
                "clients",
                "client_scopes",
                "roles",
                "groups",
                "identity_providers",
            )
        }
        if not any(content.values()):
            return
        name = self.kwargs.name
        label = f"keycloak realm import '{name}':"
        # Shallow copies: entries keep their own values, new keys go to plain dicts.
        realm = dict(_convert_to_dict(spec.realm)) if "realm" in spec else {}
        placeholders = (
            dict(_convert_to_dict(spec.placeholders)) if "placeholders" in spec else {}
        )
        generated: dict[str, dict] = {}

        def placeholder(prefix: str, ident: str, ref: Any) -> str:
            key = f"{prefix}_{re.sub(r'[^A-Za-z0-9]', '_', ident).upper()}"
            value = {"secret": _convert_to_dict(ref)}
            if generated.get(key, value) != value:
                raise ValueError(
                    f"{label} placeholder {key} maps to two Secret references"
                )
            if key not in generated and placeholders.get(key, value) != value:
                logger.warning(
                    "%s secret ref overrides spec.placeholders.%s", label, key
                )
            generated[key] = placeholders[key] = value
            return "${" + key + "}"

        def merge(field: str, entries: list, id_key: str, kind: str) -> None:
            if entries:
                realm[field] = _merge_named(
                    realm.get(field) or [], entries, id_key, f"{label} {kind}"
                )

        clients = []
        for client_id, client_config in sorted(content["clients"].items()):
            client_config = dict(client_config or {})
            secret_ref = client_config.pop("secret_ref", None)
            entry = _realm_entry(
                "clientId", client_id, client_config, _CLIENT_KEY_MAP, f"{label} client"
            )
            _warn_plaintext_credentials(name, {"clients": [entry]})
            if secret_ref:
                if "secret" in entry:
                    logger.warning(
                        "Flat key 'secret_ref' overrides 'secret' for %s client '%s'",
                        label,
                        client_id,
                    )
                entry["secret"] = placeholder("CLIENT_SECRET", client_id, secret_ref)
            clients.append(entry)
        merge("clients", clients, "clientId", "client")

        merge(
            "clientScopes",
            [
                _realm_entry(
                    "name", n, c, _CLIENT_SCOPE_KEY_MAP, f"{label} client scope"
                )
                for n, c in sorted(content["client_scopes"].items())
            ],
            "name",
            "client scope",
        )

        roles = content["roles"]
        realm_roles = [
            _realm_entry("name", n, c, {}, f"{label} realm role")
            for n, c in sorted((roles.get("realm") or {}).items())
        ]
        client_roles = {
            client_id: [
                _realm_entry("name", n, c, {}, f"{label} client role")
                for n, c in sorted((role_map or {}).items())
            ]
            for client_id, role_map in sorted((roles.get("client") or {}).items())
        }
        if realm_roles or client_roles:
            role_field = dict(realm.get("roles") or {})
            if realm_roles:
                role_field["realm"] = _merge_named(
                    role_field.get("realm") or [],
                    realm_roles,
                    "name",
                    f"{label} realm role",
                )
            if client_roles:
                by_client = dict(role_field.get("client") or {})
                for client_id, entries in client_roles.items():
                    by_client[client_id] = _merge_named(
                        by_client.get(client_id) or [],
                        entries,
                        "name",
                        f"{label} client '{client_id}' role",
                    )
                role_field["client"] = by_client
            realm["roles"] = role_field

        merge(
            "groups",
            [
                _group_entry(n, c, f"{label} group")
                for n, c in sorted(content["groups"].items())
            ],
            "name",
            "group",
        )

        providers = []
        for alias, provider_config in sorted(content["identity_providers"].items()):
            provider_config = dict(provider_config or {})
            secret_ref = provider_config.pop("client_secret_ref", None)
            entry = _realm_entry(
                "alias",
                alias,
                provider_config,
                _IDENTITY_PROVIDER_KEY_MAP,
                f"{label} identity provider",
            )
            if secret_ref:
                provider = dict(entry.get("config") or {})
                if "clientSecret" in provider:
                    logger.warning(
                        "Flat key 'client_secret_ref' overrides 'config.clientSecret' "
                        "for %s identity provider '%s'",
                        label,
                        alias,
                    )
                provider["clientSecret"] = placeholder(
                    "IDP_CLIENT_SECRET", alias, secret_ref
                )
                entry["config"] = provider
            providers.append(entry)
        merge("identityProviders", providers, "alias", "identity provider")

        spec.realm = realm
        if generated:
            spec.placeholders = placeholders


class KeycloakClient(KeycloakBase):
    """KeycloakOIDCClient or KeycloakSAMLClient (upstream alpha, k8s.keycloak.org/v2alpha1).

    metadata.name becomes the clientId. Smart defaults:
        - keycloakCRName: the only Keycloak instance in the same namespace
    """

    _FLAT_KEY_MAP = {
        "keycloak_cr_name": "keycloakCRName",
        "realm": "realm",
        "client": "client",
    }

    def new(self) -> None:
        self.need("name")
        self.need("kind")
        self.kwargs.apiVersion = "k8s.keycloak.org/v2alpha1"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        self._add_common_metadata(config)
        spec = self.root.spec
        _merge_spec_passthrough(spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)
        for key, crd_key in self._FLAT_KEY_MAP.items():
            _set_field(spec, config, key, target_key=crd_key)
        default_cr = self.kwargs.get("default_keycloak_cr_name")
        if default_cr and not spec.get("keycloakCRName"):
            spec.keycloakCRName = default_cr


def main(input_params: dict) -> BaseObj:
    """Main entry point for the Keycloak generator.

    Reads from inventory parameters:
        - generators.keycloak.instances: Dict of Keycloak instance configurations
        - generators.keycloak.realm_imports: Dict of KeycloakRealmImport configurations
        - generators.keycloak.oidc_clients / saml_clients: Dict of client configurations

    Returns:
        BaseObj with generated resources in obj.root
    """
    obj = BaseObj()

    # Get keycloak generator config
    keycloak_config = inv.parameters.get("generators", {}).get("keycloak", {}) or {}
    keycloak_config = _convert_to_dict(keycloak_config)
    default_namespace = keycloak_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )

    # Generate Keycloak instances
    instances_by_namespace: dict[str, list[str]] = {}
    for name, config in keycloak_config.get("instances", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        instances_by_namespace.setdefault(namespace, []).append(name)
        obj.root[f"{namespace}/{name}-keycloak"] = Keycloak(
            name=name, config=config, default_namespace=default_namespace
        )

    # Generate KeycloakRealmImports; keycloakCRName defaults to the only
    # instance in the import's namespace
    for name, config in keycloak_config.get("realm_imports", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        candidates = instances_by_namespace.get(namespace, [])
        obj.root[f"{namespace}/{name}-keycloakrealmimport"] = KeycloakRealmImport(
            name=name,
            config=config,
            default_namespace=default_namespace,
            default_keycloak_cr_name=candidates[0] if len(candidates) == 1 else None,
        )

    # Generate KeycloakOIDCClients and KeycloakSAMLClients, same default
    for key, kind in (("oidc_clients", "KeycloakOIDCClient"), ("saml_clients", "KeycloakSAMLClient")):
        for name, config in keycloak_config.get(key, {}).items():
            config = _convert_to_dict(config) or {}
            namespace = config.get("namespace", default_namespace)
            candidates = instances_by_namespace.get(namespace, [])
            obj.root[f"{namespace}/{name}-{kind.lower()}"] = KeycloakClient(
                name=name,
                kind=kind,
                config=config,
                default_namespace=default_namespace,
                default_keycloak_cr_name=candidates[0] if len(candidates) == 1 else None,
            )

    return obj


__all__ = [
    "Keycloak",
    "KeycloakClient",
    "KeycloakRealmImport",
    "main",
    "k8s",
    "inv",
    "_convert_to_dict",
    "_merge_spec_passthrough",
    "_warn_collisions",
]
