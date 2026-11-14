"""Unit tests of the argocd installation (docs/specs/argocd.md); command in the spec's implementation inventory."""

import contextlib
import copy
import json
from pathlib import Path

from box import Box
from yaml import safe_load, safe_load_all

from .. import install, inv, main

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "install-cmp.yaml"
CLUSTER_SCOPED = {"ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition"}
# The images of Argo CD 3.6.1's install.yaml with the digests their registries serve for these tags.
PINNED = {
    "quay.io/argoproj/argocd:v3.6.1": "sha256:296e3d74f449b2ce45265613fcb68c18ed7366488360c8ea32f5f2a93d2e5c54",
    "ghcr.io/dexidp/dex:v2.46.0": "sha256:933fcd3f523338c847b88ef84a7145fb2fcb7b9917f08418612afeaaa2001777",
    "public.ecr.aws/docker/library/redis:8.10.1-alpine": "sha256:ef216d85ec44f4fdf7c0e6df2d1757a4734ed32fbb278cabd3181b5a27353b79",
}
KAPITAN = "docker.io/kapicorp/kapitan:0.36.3@sha256:04b9ca04f5041851631fb1041fbafe37b1ca6c3ad99a81d6ccd40f5ebd20f857"


def render(**argocd):
    inv["parameters"] = Box(generators={"argocd": argocd})
    return {key: obj.root.to_dict() if hasattr(obj, "root") else obj for key, obj in main({}).root.items()}


def upstream():
    """install.yaml as vendored, with the CRDs from schemas/, keyed as the generator writes them."""
    docs = [d for d in safe_load_all((ROOT / "manifests" / "install.yaml").read_text()) if d]
    for path in sorted((ROOT / "schemas" / "argoproj.io" / "crds").iterdir()):
        docs.append(json.loads(path.read_text()) if path.suffix == ".json" else safe_load(path.read_text()))
    return {f"install/{d['metadata']['name']}-{d['kind'].lower()}": d for d in docs}


def pods(doc):
    pod = (doc.get("spec") or {}).get("template", {}).get("spec", {})
    return pod.get("initContainers", []) + pod.get("containers", [])


def undo(doc, namespace):
    """The upstream document a rendered one came from: ACD-2's three changes reverted."""
    doc = copy.deepcopy(doc)
    if doc["kind"] not in CLUSTER_SCOPED:
        assert doc["metadata"].pop("namespace") == namespace, doc["metadata"]
    for subject in doc.get("subjects", []) if doc["kind"] == "ClusterRoleBinding" else []:
        assert subject["namespace"] == namespace, subject
        subject["namespace"] = "argocd"
    for container in pods(doc):
        image, _, digest = container["image"].partition("@")
        assert PINNED[image] == digest, container["image"]
        container["image"] = image
    return doc


@contextlib.contextmanager
def documents(change):
    """install._documents with change applied to its result."""
    real = install._documents

    def changed():
        docs = real()
        change(docs)
        return docs

    install._documents = changed
    try:
        yield
    finally:
        install._documents = real


def fails(message, **argocd):
    try:
        render(**argocd)
    except ValueError as e:
        assert message in str(e), str(e)
    else:
        raise AssertionError(f"compiled: {argocd}")


def repo_server_pod(docs):
    deployment = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "argocd-repo-server")
    return deployment["spec"]["template"]["spec"]


def test_no_install_renders_as_before():
    app = {"project": "p", "destination": "web", "source": {"repoURL": "https://git.example.com/a.git"}}
    assert set(render(applications={"web": app})) == {"argocd/web-application"}
    assert set(render(applications={"web": app}, install=None)) == {"argocd/web-application"}


def test_install_is_upstream():
    out = render(install={})
    expected = upstream()
    assert len(expected) == 60
    assert set(out) == set(expected)
    for key, doc in out.items():
        assert undo(doc, "argocd") == expected[key], key
    images = {c["image"] for doc in out.values() for c in pods(doc)}
    assert images == {f"{image}@{digest}" for image, digest in PINNED.items()}


def test_install_namespace():
    out, expected = render(namespace="cd", install={}), upstream()
    for key, doc in out.items():
        assert undo(doc, "cd") == expected[key], key
    binding = out["install/argocd-server-clusterrolebinding"]
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": "argocd-server", "namespace": "cd"}]
    assert out["install/argocd-server-rolebinding"]["subjects"] == [{"kind": "ServiceAccount", "name": "argocd-server"}]


def test_unknown_kind_fails():
    job = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "migrate"}}
    with documents(lambda docs: docs.append(job)):
        fails("Job migrate of the Argo CD manifest", install={})


def test_image_without_pin_fails():
    def retag(docs):
        server = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "argocd-server")
        server["spec"]["template"]["spec"]["containers"][0]["image"] = "quay.io/argoproj/argocd:v3.5.7"

    with documents(retag):
        fails("image quay.io/argoproj/argocd:v3.5.7 of Deployment argocd-server has no digest", install={})


def test_edited_manifest_fails():
    pin, install.INSTALL_SHA256 = install.INSTALL_SHA256, "0" * 64
    try:
        fails("manifests/install.yaml has SHA-256 " + pin, install={})
    finally:
        install.INSTALL_SHA256 = pin


def test_version_mismatch_fails():
    pin, install.INSTALL_VERSION = install.INSTALL_VERSION, "3.5.7"
    try:
        fails("the CRDs in schemas/ are Argo CD 3.6.1, manifests/install.yaml is 3.5.7", install={})
    finally:
        install.INSTALL_VERSION = pin


def test_cmp_golden():
    plain, out = render(install={}), render(install={"cmp": {}})
    golden = {f"install/{d['metadata']['name']}-{d['kind'].lower()}": d for d in safe_load_all(GOLDEN.read_text())}
    assert set(golden) == {"install/argocd-repo-server-deployment", "install/kapitan-plugin-configmap"}
    assert set(out) == set(plain) | set(golden)
    for key, doc in out.items():
        assert doc == (golden[key] if key in golden else plain[key]), key
    sidecar = out["install/argocd-repo-server-deployment"]["spec"]["template"]["spec"]["containers"][-1]
    assert sidecar["image"] == KAPITAN
    assert "resources" not in sidecar


def test_cmp_image_by_digest():
    image = "registry.example.com/kapitan@sha256:" + "a" * 64
    out = render(install={"cmp": {"image": image}})
    assert out["install/argocd-repo-server-deployment"]["spec"]["template"]["spec"]["containers"][-1]["image"] == image


def test_cmp_image_without_digest_fails():
    for image in ("docker.io/kapicorp/kapitan:0.36.3", "docker.io/kapicorp/kapitan@sha256:abc", "@sha256:" + "a" * 64, ""):
        fails("install.cmp.image must be pinned by digest", install={"cmp": {"image": image}})


def test_cmp_resources():
    resources = {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}}
    out = render(install={"cmp": {"resources": resources}})
    assert out["install/argocd-repo-server-deployment"]["spec"]["template"]["spec"]["containers"][-1]["resources"] == resources


def test_cmp_needs_pod_without_token():
    def token_on(docs):
        repo_server_pod(docs)["automountServiceAccountToken"] = True

    def token_unset(docs):
        del repo_server_pod(docs)["automountServiceAccountToken"]

    for change in (token_on, token_unset):
        with documents(change):
            fails("install.cmp needs the argocd-repo-server pod without a service account token", install={"cmp": {}})
            render(install={})


def test_unknown_keys_fail():
    fails("unknown keys under install: version", install={"cmp": {}, "version": "3.6.1"})
    fails("unknown keys under install.cmp: imgae", install={"cmp": {"imgae": KAPITAN}})
    fails("install must be a mapping", install=True)
    fails("install.cmp must be a mapping", install={"cmp": True})
