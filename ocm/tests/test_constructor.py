"""Unit tests of ocm (docs/specs/ocm.md); command in the spec's implementation inventory."""

import json
import os
import tempfile

import jsonschema
import yaml

from constructor import OcmError, build, parse_ref

HERE = os.path.dirname(__file__)
DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata: {name: web}
spec:
  template:
    spec:
      initContainers: [{name: init, image: "busybox:1.37"}]
      containers:
        - {name: web, image: "ghcr.io/org/web:1.0@sha256:aaa"}
        - {name: sidecar, image: "ghcr.io/org/web:1.0@sha256:aaa"}
---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata: {name: r}
spec:
  groups: [{name: g, rules: [{alert: a, expr: "x", labels: {op: =}}]}]
"""
CR = """\
apiVersion: example.org/v1
kind: Agent
metadata: {name: a}
spec: {deep: {image: "quay.io/org/agent:v2"}}
"""


def base(**extra):
    return {"name": "example.org/acme/app", "version": "${VERSION}", "provider": {"name": "acme"}, **extra}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def compiled(d):
    """A compile root below d with two manifests and a file the scans skip."""
    root = os.path.join(d, "target")
    write(os.path.join(root, "k8s", "web", "deployment.yml"), DEPLOYMENT)
    write(os.path.join(root, "k8s", "agent.yaml"), CR)
    write(os.path.join(root, "k8s", "notes.txt"), "image: not-read:1\n")
    return root


def raises(fn, *fragments):
    try:
        fn()
    except OcmError as e:
        for fragment in fragments:
            assert fragment in str(e), (fragment, str(e))
        return
    raise AssertionError(f"no OcmError, expected {fragments}")


def run(root, components, **params):
    out = build({"components": components, **params}, root)
    ((name, text),) = out.items()
    return name, yaml.safe_load(text)


def resources(root, **spec):
    _, doc = run(root, {"app": base(**spec)})
    return doc["components"][0]["resources"]


def test_unknown_keys():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        raises(lambda: build({"components": {"app": base()}, "extra": 1}, root), "unknown input_params ['extra']")
        raises(lambda: resources(root, images={"scna": ["k8s/*.yaml"]}), "unknown images keys ['scna']")


def test_component_passthrough():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        name, doc = run(
            root,
            {
                "b": base(name="example.org/acme/b", labels=[{"name": "l", "value": "v"}], sources=[{"name": "s"}]),
                "a": base(name="example.org/acme/a", componentReferences=[{"name": "r"}]),
            },
        )
        assert name == "component-constructor.yaml"
        assert [c["name"] for c in doc["components"]] == ["example.org/acme/a", "example.org/acme/b"]
        a, b = doc["components"]
        assert a == {**base(name="example.org/acme/a", componentReferences=[{"name": "r"}]), "resources": []}
        assert b["labels"] == [{"name": "l", "value": "v"}] and b["sources"] == [{"name": "s"}]
        assert run(root, {"app": base()}, file="ocm/c.yaml")[0] == "ocm/c.yaml"


def test_component_required():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        for key in ("name", "version", "provider"):
            spec = base()
            del spec[key]
            raises(lambda: run(root, {"app": spec}), f"component app: missing ['{key}']")
        raises(lambda: build({"components": {}}, root), "components is empty")


def test_resources():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        res = resources(
            root,
            resources={
                "manifests": {"type": "ociArtifact", "version": "${VERSION}", "access": {"type": "ociArtifact", "imageReference": "r/m:v${VERSION}"}},
                "git": {"name": "repo", "type": "blob", "input": {"type": "file", "path": "${WORK}/zone.bundle"}},
            },
            images={"refs": ["redis:8"]},
        )
        assert [r["name"] for r in res] == ["manifests", "repo", "redis"]
        assert res[0]["access"]["imageReference"] == "r/m:v${VERSION}"


def test_name_collision():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        raises(lambda: resources(root, images={"refs": ["redis:8", "docker.io/bitnami/redis:7"]}), "redis: docker.io/bitnami/redis:7, redis:8")
        raises(lambda: resources(root, resources={"redis": {"type": "blob"}}, images={"refs": ["redis:8"]}), "redis: resources.redis, redis:8")


def test_scan():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        res = resources(root, images={"scan": ["k8s/**/*.yml", "k8s/*.yaml"]})
        assert [r["access"]["imageReference"] for r in res] == [
            "busybox:1.37",
            "ghcr.io/org/web:1.0@sha256:aaa",
            "quay.io/org/agent:v2",
        ]


def test_scan_errors():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        raises(lambda: resources(root, images={"scan": ["k8s/*.json"]}), "'k8s/*.json' matches no file")
        with open(os.path.join(root, "k8s", "bad.yml"), "w") as f:
            f.write("a: [\n")
        raises(lambda: resources(root, images={"scan": ["k8s/*.yml"]}), "k8s/bad.yml: not YAML")
        with open(os.path.join(root, "k8s", "bad.yml"), "wb") as f:
            f.write(b"image: \xff\n")
        raises(lambda: resources(root, images={"scan": ["k8s/*.yml"]}), "k8s/bad.yml: not YAML")
        write(os.path.join(d, "outside.yml"), "image: a:1\n")
        raises(lambda: resources(root, images={"scan": ["../outside.yml"]}), "outside the compile root")
        raises(lambda: resources(root, images={"scan": ["/etc/*.yml"]}), "images.scan '/etc/*.yml'")


def test_refs_dedup_order():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        res = resources(root, images={"scan": ["k8s/*.yaml"], "refs": ["quay.io/org/agent:v2", "busybox:1.37"]})
        assert [r["access"]["imageReference"] for r in res] == ["busybox:1.37", "quay.io/org/agent:v2"]


def test_image_resource():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        assert parse_ref("redis:8") == {
            "registry": "docker.io",
            "path": "library/redis:8",
            "repository": "docker.io/library/redis",
            "name": "redis",
            "tag": "8",
            "digest": "",
        }
        assert parse_ref("localhost:5000/a/b@sha256:1")["registry"] == "localhost:5000"
        assert parse_ref("bitnami/redis")["repository"] == "docker.io/bitnami/redis"
        (r,) = resources(root, images={"refs": ["registry.example.org:5000/team/app:1.2@sha256:abc"]})
        assert r == {
            "name": "app",
            "type": "ociImage",
            "version": "1.2",
            "access": {"type": "ociArtifact", "imageReference": "registry.example.org:5000/team/app:1.2@sha256:abc"},
        }
        (r,) = resources(root, images={"refs": ["nginx"]})
        assert r["version"] == "latest"


def test_untagged_digest():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        raises(lambda: resources(root, images={"refs": ["busybox@sha256:1"]}), "image busybox@sha256:1 has a digest but no tag")


def test_access_template():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        res = resources(root, images={"refs": ["redis:8", "ghcr.io/org/web:1.0@sha256:aaa"], "access": "${PROXY_%registry_id%}/%path% %registry% %ref%"})
        assert [r["access"]["imageReference"] for r in res] == [
            "${PROXY_ghcr_io}/org/web:1.0@sha256:aaa ghcr.io ghcr.io/org/web:1.0@sha256:aaa",
            "${PROXY_docker_io}/library/redis:8 docker.io redis:8",
        ]


def test_label_digest():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        (r,) = resources(root, images={"refs": ["ghcr.io/org/web:1.0@sha256:aaa"], "label": "upstream", "require_digest": True})
        assert r["labels"] == [{"name": "upstream", "value": "ghcr.io/org/web:1.0@sha256:aaa"}]
        raises(lambda: resources(root, images={"refs": ["redis:8"], "require_digest": True}), "image redis:8 has no digest")


def test_names():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        res = resources(root, images={"refs": ["redis:8", "bitnami/redis:7"], "names": {"docker.io/bitnami/redis": "bitnami-redis"}})
        assert [r["name"] for r in res] == ["bitnami-redis", "redis"]
        raises(lambda: resources(root, images={"refs": ["redis:8"], "names": {"docker.io/gone": "x"}}), "images.names ['docker.io/gone'] match no image")


def test_schema():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        with open(os.path.join(HERE, "constructor.schema.json")) as f:
            schema = json.load(f)
        _, doc = run(
            root,
            {
                "app": base(
                    resources={"git": {"type": "blob", "input": {"type": "file", "path": "${WORK}/zone.bundle"}}},
                    images={"scan": ["k8s/**/*.yml", "k8s/*.yaml"], "label": "upstream", "access": "${PROXY_%registry_id%}/%path%"},
                )
            },
        )
        jsonschema.Draft202012Validator(schema).validate(doc)


def test_dedup_parsed():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        (r,) = resources(root, images={"refs": ["redis:8", "docker.io/library/redis:8", "DOCKER.IO/library/redis:8"], "label": "l"})
        assert r["labels"] == [{"name": "l", "value": "DOCKER.IO/library/redis:8"}]
        (r,) = resources(root, images={"refs": ["ghcr.io/org/web:1.0", "ghcr.io/org/web:1.0@sha256:aaa"], "require_digest": True})
        assert r["access"]["imageReference"] == "ghcr.io/org/web:1.0@sha256:aaa"
        raises(
            lambda: resources(root, images={"refs": ["ghcr.io/org/web:1.0@sha256:aaa", "ghcr.io/org/web:1.0@sha256:bbb"]}),
            "web: ghcr.io/org/web:1.0@sha256:aaa, ghcr.io/org/web:1.0@sha256:bbb",
        )


def test_image_key_types():
    with tempfile.TemporaryDirectory() as d:
        root = compiled(d)
        for key, value in (
            ("scan", "k8s/*.yaml"),
            ("scan", [2024]),
            ("refs", "redis:8"),
            ("access", 1),
            ("label", ["x"]),
            ("require_digest", "false"),
            ("names", {"docker.io/library/redis": 1}),
        ):
            raises(lambda: resources(root, images={"refs": ["redis:8"], key: value}), f"images.{key} must be")
