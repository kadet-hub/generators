"""Unit tests of the talos generator (docs/specs/talos.md); command in the spec's implementation inventory."""

import copy

import yaml

from .. import main
from ..multidoc import IMAGES, append_documents, split


def config(machine_type="controlplane", **cluster):
    return {"machine": {"type": machine_type}, "cluster": {"clusterName": "c", **cluster}}


def images(docs):
    """{kind or v1alpha1 path: image} of the rendered component images."""
    legacy, *rest = docs
    out = {d["kind"]: d["image"] for d in rest if "image" in d and d["kind"].startswith("Kube")}
    for path in (("machine", "kubelet"), ("cluster", "apiServer"), ("cluster", "proxy")):
        block = legacy.get(path[0], {}).get(path[1]) or {}
        if "image" in block:
            out[".".join(path)] = block["image"]
    return out


def test_component_tags_must_agree():
    cases = (
        (config(apiServer={"image": "registry.k8s.io/kube-apiserver:v1.36.4@sha256:aa"}, proxy={"image": "mirror/kube-proxy:v1.37.1"}), ("apiServer v1.36.4", "proxy v1.37.1")),
        # no tag gives no version to derive the other images from
        (config(apiServer={"image": "registry.k8s.io/kube-apiserver@sha256:aa"}), ("apiServer (no tag)",)),
    )
    for c, fragments in cases:
        try:
            split("cp-1", c)
        except ValueError as e:
            for fragment in ("cp-1", *fragments):
                assert fragment in str(e), str(e)
        else:
            raise AssertionError("no ValueError")


def test_missing_images_take_the_tag():
    c = config(apiServer={"image": "mirror.example.org/kube-apiserver:v1.36.4@sha256:aa"}, proxy={"disabled": True})
    got = images(split("cp-1", c))
    assert got == {
        "KubeletConfig": "ghcr.io/siderolabs/kubelet:v1.36.4",
        "KubeAPIServerConfig": "mirror.example.org/kube-apiserver:v1.36.4@sha256:aa",
        "KubeControllerManagerConfig": "registry.k8s.io/kube-controller-manager:v1.36.4",
        "KubeSchedulerConfig": "registry.k8s.io/kube-scheduler:v1.36.4",
        "KubeProxyConfig": "registry.k8s.io/kube-proxy:v1.36.4",
    }, got
    # an apiServer block that stays in v1alpha1 gets the image there
    c = config(apiServer={"extraVolumes": [{"hostPath": "/x", "mountPath": "/x"}]}, scheduler={"image": "registry.k8s.io/kube-scheduler:v1.36.4"})
    got = images(split("cp-1", c))
    assert got["cluster.apiServer"] == "registry.k8s.io/kube-apiserver:v1.36.4", got
    # workers keep only kubelet; the other kinds are control plane documents
    got = images(split("wk-1", config("worker", proxy={"image": "registry.k8s.io/kube-proxy:v1.36.4"})))
    assert got == {"KubeletConfig": "ghcr.io/siderolabs/kubelet:v1.36.4"}, got


def test_no_images_unchanged():
    c = config(proxy={"disabled": True})
    before = copy.deepcopy(c)
    docs = split("cp-1", c)
    assert images(docs) == {"KubeProxyConfig": IMAGES["proxy"]}
    assert "kubelet" not in docs[0]["machine"] and before["cluster"]["proxy"] == {"disabled": True}


TRIM = {"apiVersion": "v1alpha1", "kind": "FilesystemTrimConfig", "interval": "168h0m0s"}
ISOLATION = {"apiVersion": "v1alpha1", "kind": "SecurityProfileConfig", "workloadIsolation": True}
VOLUME = {"apiVersion": "v1alpha1", "kind": "UserVolumeConfig", "name": "local-path-provisioner", "volumeType": "directory"}


def render(monkeypatch, **talos):
    """main() output for parameters.generators.talos = *talos*."""
    class Inventory:
        parameters = {"generators": {"talos": talos}}

    monkeypatch.setattr(f"{main.__module__}.inv", Inventory)
    return main().root


def error(*args):
    """The ValueError message of append_documents(*args)."""
    try:
        append_documents(*args)
    except ValueError as e:
        return str(e)
    raise AssertionError("no ValueError")


def test_documents_appended(monkeypatch):
    roots = {"apiVersion": "v1alpha1", "kind": "TrustedRootsConfig", "name": "corp", "certificates": "?{gpg:talos/corp-ca}"}
    out = render(monkeypatch, base={"documents": [TRIM, ISOLATION]}, nodes={
        "cp-1": {"type": "controlplane", "cluster": {"clusterName": "c"}},
        "wk-1": {"documents": [VOLUME, roots], "userdataSecret": {"name": "wk-1", "namespace": "vms"}},
        "wk-2": {"documents": []},
    })
    kinds = {TRIM["kind"], ISOLATION["kind"], VOLUME["kind"], roots["kind"]}
    for node, documents in (("cp-1", [TRIM, ISOLATION]), ("wk-1", [VOLUME, roots]), ("wk-2", [])):
        docs = out[node]
        assert "documents" not in docs[0], node
        generated = docs[1:len(docs) - len(documents)]
        assert generated and not [d for d in generated if d["kind"] in kinds], node
        # the node's list replaces the base list; the Kapitan ref stays as written
        assert docs[len(docs) - len(documents):] == documents, (node, docs)
    userdata = list(yaml.safe_load_all(out["vms/wk-1-secret"]["stringData"]["userdata"]))
    assert userdata[-2:] == [VOLUME, roots]


def test_documents_need_apiversion_and_kind():
    for doc, missing in (({"kind": "FilesystemTrimConfig"}, "apiVersion"), ({"apiVersion": "v1alpha1", "kind": ""}, "kind"), ("FilesystemTrimConfig", "apiVersion and kind")):
        e = error("wk-1", split("wk-1", config("worker")), [TRIM, doc])
        assert all(f in e for f in ("wk-1", "documents[1]", missing)), e
    e = error("wk-1", split("wk-1", config("worker")), TRIM)
    assert "wk-1: documents must be a list" in e, e


def test_documents_must_not_repeat_generated():
    c = config(proxy={"disabled": True})
    c["machine"]["network"] = {"hostname": "cp-1", "interfaces": [{"interface": "eth0", "addresses": ["192.0.2.11/24"]}]}
    hostname = {"apiVersion": "v1alpha1", "kind": "HostnameConfig", "hostname": "other"}
    eth0 = {"apiVersion": "v1alpha1", "kind": "LinkConfig", "name": "eth0"}
    for doc, fragment in ((hostname, "HostnameConfig"), (eth0, "LinkConfig eth0")):
        e = error("cp-1", split("cp-1", copy.deepcopy(c)), [VOLUME, doc])
        assert all(f in e for f in ("cp-1", "documents[1]", fragment)), e
    eth1 = {**eth0, "name": "eth1"}
    assert append_documents("cp-1", split("cp-1", copy.deepcopy(c)), [eth1])[-1] == eth1
    # the worker filter drops the generated KubeProxyConfig, so a raw one repeats nothing
    proxy = {"apiVersion": "v1alpha1", "kind": "KubeProxyConfig", "enabled": False}
    assert append_documents("wk-1", split("wk-1", config("worker", proxy={"disabled": True})), [proxy])[-1] == proxy
