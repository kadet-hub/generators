"""Unit tests of the certmanager generator (docs/specs/certmanager.md); command in the spec's implementation inventory."""

from box import Box

from .. import inv, main

META = {"labels": {"team": "platform"}, "annotations": {"argocd.argoproj.io/sync-wave": "-1"}}


def render(**sections):
    inv["parameters"] = Box(namespace="apps", generators={"certmanager": sections})
    return {key: obj.root.to_dict() for key, obj in main({}).root.items()}


def test_entry_metadata():
    spec = {"ca": {"secretName": "ca"}}
    out = render(
        certs={"web": {**META, "spec": {"secretName": "web-tls"}}},
        issuers={"ca": {**META, "spec": spec}},
        clusterissuers={"cluster-ca": {**META, "spec": spec}},
        bundles={"trust": {**META, "spec": {"sources": [{"useDefaultCAs": True}]}}},
    )
    assert set(out) == {"apps/web-cert", "apps/ca-issuer", "cluster-ca-cissuer", "trust-bundle"}
    for key, resource in out.items():
        name = resource["metadata"]["name"]
        assert resource["metadata"]["labels"] == {"name": name, "team": "platform"}, key
        assert resource["metadata"]["annotations"] == META["annotations"], key


def test_ca_issuer_metadata():
    out = render(ca_issuers={"root": META})
    assert set(out) == {"root-selfsigned-cissuer", "cert-manager/root-cert", "root-cissuer"}
    for key, resource in out.items():
        assert resource["metadata"]["labels"]["team"] == "platform", key
        assert resource["metadata"]["annotations"] == META["annotations"], key


def test_no_metadata_keys():
    out = render(certs={"web": {"spec": {"secretName": "web-tls"}}})
    assert out["apps/web-cert"]["metadata"] == {"name": "web", "namespace": "apps", "labels": {"name": "web"}}
