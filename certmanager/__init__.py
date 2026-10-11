from __future__ import annotations

import logging
from typing import Any


"""cert-manager resource generators for Kapitan.

This module provides classes and functions for generating cert-manager resources
using Kapitan's kadet input type. Supports Issuer, ClusterIssuer, Certificate,
and trust-manager Bundle resources.
"""

__version__ = "1.0.0"

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
    """Recursively convert BaseObj / OmegaConf objects to plain Python dicts.

    Kapitan inventory values arrive as OmegaConf DictConfig objects.
    This function converts them so they can be serialised
    to YAML without surprises.
    """
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


def _require_spec(config_spec: dict, kind: str, name: str) -> Any:
    """Return the converted spec, failing loudly when it is missing.

    All cert-manager/trust-manager resources require spec; emitting
    spec: null would only fail later at apply time.
    """
    spec = config_spec.get("spec")
    if not spec:
        raise ValueError(f"certmanager {kind} '{name}': 'spec' is required")
    return _convert_to_dict(spec)


# https://letsencrypt.org/docs/acme-protocol-updates/
LETSENCRYPT_SERVERS = {
    "production": "https://acme-v02.api.letsencrypt.org/directory",
    "staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
}


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge *override* onto *base*; override wins, lists are replaced."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _issuer_spec(config_spec: Any, kind: str, name: str) -> dict:
    """Issuer/ClusterIssuer spec: ``spec``, ACME shorthands on top.

    An ACME issuer without privateKeySecretRef gets its own account key
    Secret ``<name>-account-key``.
    """
    acme = {}
    letsencrypt = config_spec.get("letsencrypt")
    if letsencrypt is not None:
        if letsencrypt not in LETSENCRYPT_SERVERS:
            raise ValueError(
                f"certmanager {kind} '{name}': letsencrypt must be "
                f"production or staging, not '{letsencrypt}'"
            )
        acme["server"] = LETSENCRYPT_SERVERS[letsencrypt]
    if config_spec.get("email") is not None:
        acme["email"] = config_spec.get("email")
    ingress_class = config_spec.get("http01_ingress_class")
    if ingress_class is not None:
        acme["solvers"] = [{"http01": {"ingress": {"ingressClassName": ingress_class}}}]
    user_spec = _convert_to_dict(config_spec.get("spec")) or {}
    user_acme = user_spec.get("acme")
    if isinstance(user_acme, dict):
        flat_keys = {"server": "letsencrypt", "email": "email", "solvers": "http01_ingress_class"}
        for field, flat_key in flat_keys.items():
            if field in acme and user_acme.get(field) is not None:
                logger.warning(
                    "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                    flat_key,
                    f"acme.{field}",
                    name,
                )
    spec = _merge(user_spec, {"acme": acme} if acme else {})
    if not spec:
        raise ValueError(
            f"certmanager {kind} '{name}': 'spec' or 'letsencrypt' is required"
        )
    if isinstance(spec.get("acme"), dict) and not spec["acme"].get("privateKeySecretRef"):
        spec["acme"]["privateKeySecretRef"] = {"name": f"{name}-account-key"}
    return spec


class CertManagerIssuer(k8s.Base):
    """cert-manager Issuer resource.

    Generates a namespaced Issuer for cert-manager certificate issuance.

    Required kwargs:
        config_spec: Issuer configuration dictionary containing spec and optional namespace.
        name: Resource name.
    """

    def new(self) -> None:
        self.need("config_spec")
        self.kwargs.apiVersion = "cert-manager.io/v1"
        self.kwargs.kind = "Issuer"
        super().new()

    def body(self) -> None:
        config_spec = self.kwargs.config_spec
        self.add_namespace(
            config_spec.get("namespace", inv.parameters.get("namespace", "default"))
        )
        super().body()
        self.root.spec = _issuer_spec(config_spec, self.kwargs.kind, self.kwargs.name)


class CertManagerClusterIssuer(k8s.Base):
    """cert-manager ClusterIssuer resource.

    Generates a cluster-scoped ClusterIssuer for cert-manager certificate issuance.

    Required kwargs:
        config_spec: ClusterIssuer configuration dictionary containing spec.
        name: Resource name.
    """

    def new(self) -> None:
        self.need("config_spec")
        self.kwargs.apiVersion = "cert-manager.io/v1"
        self.kwargs.kind = "ClusterIssuer"
        super().new()

    def body(self) -> None:
        super().body()
        config_spec = self.kwargs.config_spec
        self.root.spec = _issuer_spec(config_spec, self.kwargs.kind, self.kwargs.name)


class CertManagerCertificate(k8s.Base):
    """cert-manager Certificate resource.

    Generates a Certificate resource that requests certificates from an Issuer.

    Required kwargs:
        config_spec: Certificate configuration dictionary containing spec and optional namespace.
        name: Resource name.
    """

    def new(self) -> None:
        self.need("config_spec")
        self.kwargs.apiVersion = "cert-manager.io/v1"
        self.kwargs.kind = "Certificate"
        super().new()

    def body(self) -> None:
        config_spec = self.kwargs.config_spec
        self.add_namespace(
            config_spec.get("namespace", inv.parameters.get("namespace", "default"))
        )
        super().body()
        # Vendor recommendation; the controller default since 1.18 is feature-gated.
        self.root.spec = _merge(
            {"privateKey": {"rotationPolicy": "Always"}},
            _require_spec(config_spec, self.kwargs.kind, self.kwargs.name),
        )


class CertManagerBundle(k8s.Base):
    """trust-manager Bundle resource.

    Generates a Bundle resource for trust-manager CA distribution.

    Required kwargs:
        config_spec: Bundle configuration dictionary containing spec and optional namespace.
        name: Resource name.
    """

    def new(self) -> None:
        self.kwargs.apiVersion = "trust.cert-manager.io/v1alpha1"
        self.kwargs.kind = "Bundle"
        super().new()
        self.need("config_spec")

    def body(self) -> None:
        super().body()
        config_spec = self.kwargs.config_spec
        # trust-manager Bundle is cluster-scoped upstream; the target
        # namespace for synced bundles lives in spec.target, not metadata.
        self.root.spec = _require_spec(config_spec, self.kwargs.kind, self.kwargs.name)


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for the cert-manager generator.

    Generates cert-manager resources from inventory parameters.

    Expected inventory structure:
        parameters:
          namespace: default-namespace
          generators:
            certmanager:
              namespace: optional-generator-namespace  # overrides parameters.namespace
              certs:
                my-cert:
                  namespace: optional-namespace
                  spec:
                    secretName: my-cert-tls
                    issuerRef:
                      name: my-issuer
                      kind: ClusterIssuer
                    dnsNames:
                      - example.com
              issuers:
                my-issuer:
                  namespace: cert-manager
                  spec:
                    acme:
                      server: https://acme-v02.api.letsencrypt.org/directory
                      email: admin@example.com
                      privateKeySecretRef:
                        name: letsencrypt-account-key
                      solvers:
                        - http01:
                            ingress:
                              class: nginx
              clusterissuers:
                my-cluster-issuer:
                  spec:
                    ca:
                      secretName: ca-key-pair
              bundles:
                my-bundle:
                  spec:
                    sources:
                      - useDefaultCAs: true
                    target:
                      configMap:
                        key: ca-bundle.crt

    Args:
        input_params: Input parameters from Kapitan compile configuration.

    Returns:
        BaseObj containing all generated cert-manager resources.
    """
    obj = BaseObj()

    cert_manager_config = inv.parameters.get("generators", {}).get("certmanager", {})
    if not cert_manager_config:
        return obj

    namespace = cert_manager_config.get(
        "namespace", inv.parameters.get("namespace", "default")
    )

    # Generate Certificates
    for cert_name, cert_spec in (cert_manager_config.get("certs") or {}).items():
        if cert_spec.get("type", "certmanager") == "certmanager":
            name = cert_spec.get("name", cert_name)
            ns = cert_spec.get("namespace", namespace)
            cert = CertManagerCertificate(
                name=name, config_spec={**cert_spec, "namespace": ns}
            )
            obj.root[f"{ns}/{name}-cert"] = cert

    # Generate Issuers
    for issuer_name, issuer_spec in (cert_manager_config.get("issuers") or {}).items():
        if issuer_spec.get("type", "certmanager") == "certmanager":
            name = issuer_spec.get("name", issuer_name)
            ns = issuer_spec.get("namespace", namespace)
            issuer = CertManagerIssuer(
                name=name, config_spec={**issuer_spec, "namespace": ns}
            )
            obj.root[f"{ns}/{name}-issuer"] = issuer

    # Generate ClusterIssuers
    for issuer_name, issuer_spec in (
        cert_manager_config.get("clusterissuers") or {}
    ).items():
        if issuer_spec.get("type", "certmanager") == "certmanager":
            name = issuer_spec.get("name", issuer_name)
            issuer = CertManagerClusterIssuer(name=name, config_spec=issuer_spec)
            # ClusterIssuer is cluster-scoped: omit namespace from output key
            obj.root[f"{name}-cissuer"] = issuer

    # Generate Bundles
    for bundle_name, bundle_spec in (cert_manager_config.get("bundles") or {}).items():
        if bundle_spec.get("type", "certmanager") == "certmanager":
            name = bundle_spec.get("name", bundle_name)
            bundle = CertManagerBundle(name=name, config_spec=bundle_spec)
            obj.root[f"{name}-bundle"] = bundle

    # Generate CA ClusterIssuers, bootstrapped like
    # https://cert-manager.io/docs/configuration/selfsigned/#bootstrapping-ca-issuers
    for ca_name, ca_spec in (cert_manager_config.get("ca_issuers") or {}).items():
        ca_spec = ca_spec or {}
        if ca_spec.get("type", "certmanager") == "certmanager":
            name = ca_spec.get("name", ca_name)
            # A ClusterIssuer reads its Secret from the cluster resource namespace.
            ns = ca_spec.get("namespace", "cert-manager")
            selfsigned = f"{name}-selfsigned"
            certificate = _merge(
                {
                    "isCA": True,
                    "commonName": name,
                    "secretName": name,
                    "privateKey": {"algorithm": "ECDSA", "size": 256},
                    "issuerRef": {
                        "name": selfsigned,
                        "kind": "ClusterIssuer",
                        "group": "cert-manager.io",
                    },
                },
                _convert_to_dict(ca_spec.get("certificate")) or {},
            )
            if ca_spec.get("common_name") is not None:
                if (_convert_to_dict(ca_spec.get("certificate")) or {}).get("commonName") is not None:
                    logger.warning(
                        "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                        "common_name",
                        "certificate.commonName",
                        name,
                    )
                certificate["commonName"] = ca_spec.get("common_name")
            resources = {
                f"{selfsigned}-cissuer": CertManagerClusterIssuer(
                    name=selfsigned, config_spec={"spec": {"selfSigned": {}}}
                ),
                f"{ns}/{name}-cert": CertManagerCertificate(
                    name=name, config_spec={"namespace": ns, "spec": certificate}
                ),
                f"{name}-cissuer": CertManagerClusterIssuer(
                    name=name,
                    config_spec={"spec": {"ca": {"secretName": certificate["secretName"]}}},
                ),
            }
            for key, resource in resources.items():
                if key in obj.root:
                    raise ValueError(
                        f"certmanager ca_issuers '{name}': '{key}' is already rendered"
                    )
                obj.root[key] = resource

    return obj


__all__ = [
    "CertManagerBundle",
    "CertManagerCertificate",
    "CertManagerClusterIssuer",
    "CertManagerIssuer",
    "inv",
    "k8s",
    "main",
]
