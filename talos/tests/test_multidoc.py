"""Unit tests of the talos component images (docs/specs/talos.md); command in the spec's implementation inventory."""

import copy

from ..multidoc import IMAGES, split


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
    c = config(apiServer={"image": "registry.k8s.io/kube-apiserver:v1.36.4@sha256:aa"}, proxy={"image": "mirror/kube-proxy:v1.37.1"})
    try:
        split("cp-1", c)
    except ValueError as e:
        for fragment in ("cp-1", "apiServer v1.36.4", "proxy v1.37.1"):
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
