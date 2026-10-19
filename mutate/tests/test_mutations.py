"""Unit tests of mutate (docs/specs/mutate.md); command in the spec's implementation inventory."""

import os
import tempfile

from mutations import MutationError, apply, check_entries, load, read_files

DEPLOYMENT = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "web", "namespace": "apps", "labels": {"app": "web", "tier": "front"}},
    "spec": {
        "replicas": 1,
        "template": {
            "spec": {
                "initContainers": [{"name": "init", "image": "busybox"}],
                "containers": [
                    {
                        "name": "web",
                        "image": "ghcr.io/org/web:1.0",
                        "env": [{"name": "A", "value": "1"}, {"name": "B", "value": "2"}],
                        "ports": [{"containerPort": 80, "name": "http"}],
                    },
                    {"name": "sidecar", "image": "docker.io/envoy@sha256:aaa"},
                ],
            }
        },
    },
}
SERVICE = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "web", "namespace": "apps", "labels": {"app": "web"}}}
CONFIGMAP = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "cfg"}, "data": {"a": "x\ny\n"}}


def files():
    return {"web/deployment.yaml": [DEPLOYMENT], "web/service.yaml": [SERVICE, CONFIGMAP]}


def run(mutations, f=None):
    out = apply(f or files(), mutations)
    return {path: load(text) for path, text in out.items()}, out


def raises(fn, *fragments):
    try:
        fn()
    except MutationError as e:
        for fragment in fragments:
            assert fragment in str(e), (fragment, str(e))
        return str(e)
    raise AssertionError("no MutationError")


def test_reads_yaml_files_only():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "chart", "templates"))
        for name, text in {
            "chart/templates/a.yaml": "a: 1\n---\n---\nb: 2\n",
            "chart/templates/b.yml": "c: 3\n",
            "chart/NOTES.txt": "not: [yaml",
        }.items():
            with open(os.path.join(root, name), "w") as f:
                f.write(text)
        assert read_files(root) == {"chart/templates/a.yaml": [{"a": 1}, {"b": 2}], "chart/templates/b.yml": [{"c": 3}]}
        with open(os.path.join(root, "bad.yaml"), "w") as f:
            f.write("a: [1\n")
        raises(lambda: read_files(root), "bad.yaml", "not YAML")


def test_equals_sign_is_a_string():
    assert load("enum: [=, '!=']\n") == [{"enum": ["=", "!="]}]


def test_untouched_files_are_not_returned():
    docs, out = run({"r": {"match": {"kind": "Deployment"}, "merge": {"spec": {"replicas": 3}}}})
    assert list(out) == ["web/deployment.yaml"]
    assert docs["web/deployment.yaml"][0]["spec"]["replicas"] == 3
    # key order is kept and multi-line strings become literal blocks
    docs, out = run({"c": {"match": {"kind": "ConfigMap"}, "merge": {"data": {"b": "1"}}}})
    text = out["web/service.yaml"]
    assert text.index("apiVersion") < text.index("kind") < text.index("metadata")
    assert "a: |\n    x\n    y\n" in text
    assert docs["web/service.yaml"] == [SERVICE, {**CONFIGMAP, "data": {"a": "x\ny\n", "b": "1"}}]


def test_file_emptied_by_delete_is_a_comment():
    docs, out = run(
        {
            "z-svc": {"match": {"kind": "Service"}, "delete": True},
            "a-cm": {"match": {"kind": "ConfigMap"}, "delete": True},
        }
    )
    assert out["web/service.yaml"] == "# all objects removed by mutation a-cm, z-svc\n"
    assert docs["web/service.yaml"] == []
    docs, _ = run({"svc": {"match": {"kind": "Service"}, "delete": True}})
    assert docs["web/service.yaml"] == [CONFIGMAP]


def test_output_type_must_be_plain():
    ok = {"input_type": "kadet", "output_path": "p", "output_type": "plain", "input_params": {"mutations": {}}}
    check_entries([ok, {"input_type": "helm", "output_path": "p"}, {"input_type": "kadet", "output_path": "q"}])
    raises(lambda: check_entries([{**ok, "output_type": "auto"}]), "needs output_type: plain", "has auto")
    raises(lambda: check_entries([{k: v for k, v in ok.items() if k != "output_type"}]), "has yaml")


def test_order_sorted_deletes_last():
    mutations = {
        # "a" deletes, but runs after "b", which relabels the Service so "c" matches it
        "a": {"match": {"labels": {"gone": "yes"}}, "delete": True},
        "b": {"match": {"kind": "Service"}, "merge": {"metadata": {"labels": {"gone": "yes"}}}},
        "c": {"match": {"kind": "*", "labels": {"gone": "yes"}}, "merge": {"metadata": {"annotations": {"seen": "c"}}}},
    }
    docs, _ = run(mutations)
    assert docs["web/service.yaml"] == [CONFIGMAP]
    # adjacent objects matched by one delete are all removed
    f = {"x.yaml": [SERVICE, SERVICE, CONFIGMAP]}
    docs, _ = run({"d": {"match": {"kind": "Service"}, "delete": True, "expects": 2}}, f)
    assert docs["x.yaml"] == [CONFIGMAP]


def test_invalid_mutations_fail():
    cases = [
        ({"match": {"kind": "Service"}}, "exactly one of"),
        ({"match": {"kind": "Service"}, "merge": {}, "delete": True}, "exactly one of"),
        ({"match": {}, "delete": True}, "match must be a non-empty map"),
        ({"delete": True}, "match must be a non-empty map"),
        ({"match": {"kind": "Service", "group": "x"}, "delete": True}, "unknown match keys"),
        ({"match": {"kind": "Service"}, "delete": True, "patch": {}}, "unknown keys"),
        ({"match": {"kind": "Service"}, "delete": False}, "delete must be true"),
        ({"match": {"kind": "Service"}, "delete": True, "expects": "2+"}, "expects must be"),
        ({"match": {"kind": "Service"}, "delete": True, "merge_lists": {"a": "b"}}, "merge_lists needs merge"),
        ({"match": {"kind": "Service"}, "json6902": [{"op": "add", "path": "/a"}]}, "takes exactly"),
        ({"match": {"kind": "Service"}, "json6902": [{"op": "drop", "path": "/a"}]}, "needs op"),
        ({"match": {"kind": "Deployment"}, "images": {"busybox": {"version": "1"}}}, "takes one or more"),
        ({"match": {"labels": {"app": 1}}, "delete": True}, "match.labels"),
    ]
    for mutation, fragment in cases:
        raises(lambda: run({"m1": mutation}), "mutation m1:", fragment)


def test_result_keeps_identity():
    raises(
        lambda: run({"n": {"match": {"kind": "Service"}, "merge": {"metadata": {"name": None}}}}),
        "mutation n:",
        "web/service.yaml",
        "lost apiVersion, kind or metadata.name",
    )
    raises(
        lambda: run({"n": {"match": {"kind": "Service"}, "json6902": [{"op": "remove", "path": "/kind"}]}}),
        "web/service.yaml",
    )


def test_match_is_exact_and_anded():
    def count(match):
        try:
            run({"m": {"match": match, "merge": {}, "expects": 0}})
            return 0
        except MutationError as e:
            return int(str(e).rsplit(" ", 1)[1])

    assert count({"kind": "Service"}) == 1
    assert count({"kind": "service"}) == 0
    assert count({"kind": "*"}) == 3
    assert count({"kind": "*", "name": "web"}) == 2
    assert count({"kind": "*", "namespace": "apps"}) == 2
    assert count({"kind": "*", "apiVersion": "v1"}) == 2
    assert count({"name": "web", "namespace": "other"}) == 0
    assert count({"labels": {"app": "web"}}) == 2
    assert count({"labels": {"app": "web", "tier": "front"}}) == 1
    assert count({"namespace": "apps", "kind": "ConfigMap"}) == 0  # no metadata.namespace, no match


def test_expects():
    m = {"match": {"kind": "Secret"}, "delete": True}
    raises(lambda: run({"s": m}), "mutation s:", "expects 1+, matched 0")
    assert run({"s": {**m, "expects": "0+"}})[1] == {}
    assert run({"s": {**m, "expects": 0}})[1] == {}
    raises(lambda: run({"s": {"match": {"name": "web"}, "merge": {}, "expects": 1}}), "expects 1, matched 2")


def test_merge_rfc7386():
    merge = {
        "metadata": {"labels": {"tier": None, "new": "x"}},
        "spec": {
            "replicas": None,
            "strategy": {"type": "Recreate", "rollingUpdate": None},
            "template": {"spec": {"initContainers": [{"name": "other", "image": "x"}]}},
        },
    }
    docs, _ = run({"m": {"match": {"kind": "Deployment"}, "merge": merge}})
    d = docs["web/deployment.yaml"][0]
    assert d["metadata"]["labels"] == {"app": "web", "new": "x"}
    assert "replicas" not in d["spec"]
    assert d["spec"]["strategy"] == {"type": "Recreate"}
    assert d["spec"]["template"]["spec"]["initContainers"] == [{"name": "other", "image": "x"}]
    assert d["spec"]["template"]["spec"]["containers"] == DEPLOYMENT["spec"]["template"]["spec"]["containers"]


def test_merge_lists_by_key():
    merge = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "web",
                            "env": [{"name": "B", "value": "two"}, {"name": "C", "value": "3"}],
                            "ports": [{"containerPort": 80, "protocol": "TCP"}, {"containerPort": 9090}],
                            "resources": {"limits": {"memory": "64Mi"}},
                        },
                        {"name": "new", "image": "new:1", "args": None},
                    ]
                }
            }
        }
    }
    lists = {"containers": "name", "env": "name", "ports": "containerPort"}
    docs, _ = run({"m": {"match": {"kind": "Deployment"}, "merge": merge, "merge_lists": lists}})
    containers = docs["web/deployment.yaml"][0]["spec"]["template"]["spec"]["containers"]
    assert [c["name"] for c in containers] == ["web", "sidecar", "new"]
    assert containers[0]["image"] == "ghcr.io/org/web:1.0"
    assert containers[0]["env"] == [{"name": "A", "value": "1"}, {"name": "B", "value": "two"}, {"name": "C", "value": "3"}]
    assert containers[0]["ports"] == [{"containerPort": 80, "name": "http", "protocol": "TCP"}, {"containerPort": 9090}]
    assert containers[0]["resources"] == {"limits": {"memory": "64Mi"}}
    assert containers[2] == {"name": "new", "image": "new:1"}
    # without merge_lists the list replaces
    docs, _ = run({"m": {"match": {"kind": "Deployment"}, "merge": merge}})
    assert [c["name"] for c in docs["web/deployment.yaml"][0]["spec"]["template"]["spec"]["containers"]] == ["web", "new"]
    raises(
        lambda: run({"m": {"match": {"kind": "Deployment"}, "merge": {"spec": {"template": {"spec": {"containers": [{"image": "x"}]}}}}, "merge_lists": lists}}),
        "web/deployment.yaml",
        "every merge item needs name",
    )
    dup = {"spec": {"template": {"spec": {"containers": [{"name": "a"}, {"name": "a"}]}}}}
    raises(lambda: run({"m": {"match": {"kind": "Deployment"}, "merge": dup, "merge_lists": lists}}), "duplicate name 'a' in the merge")


def test_json6902():
    ops = [
        {"op": "test", "path": "/spec/replicas", "value": 1.0},
        {"op": "replace", "path": "/spec/replicas", "value": 2},
        {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "Z", "value": "z"}},
        {"op": "add", "path": "/spec/template/spec/containers/0/env/0", "value": {"name": "FIRST"}},
        {"op": "remove", "path": "/spec/template/spec/containers/1"},
        {"op": "add", "path": "/metadata/annotations", "value": {"a~b/c": "1"}},
        {"op": "copy", "from": "/metadata/annotations/a~0b~1c", "path": "/metadata/labels/copied"},
        {"op": "move", "from": "/metadata/labels/tier", "path": "/metadata/labels/moved"},
    ]
    docs, _ = run({"j": {"match": {"kind": "Deployment"}, "json6902": ops}})
    d = docs["web/deployment.yaml"][0]
    assert d["spec"]["replicas"] == 2
    assert [e["name"] for e in d["spec"]["template"]["spec"]["containers"][0]["env"]] == ["FIRST", "A", "B", "Z"]
    assert [c["name"] for c in d["spec"]["template"]["spec"]["containers"]] == ["web"]
    assert d["metadata"]["labels"] == {"app": "web", "copied": "1", "moved": "front"}
    for op, fragment in [
        ({"op": "test", "path": "/spec/replicas", "value": 2}, "test of '/spec/replicas' failed"),
        ({"op": "test", "path": "/spec/replicas", "value": True}, "test of '/spec/replicas' failed"),
        ({"op": "remove", "path": "/spec/missing"}, "does not exist"),
        ({"op": "replace", "path": "/spec/template/spec/containers/5", "value": {}}, "does not exist"),
        ({"op": "add", "path": "/spec/nope/x", "value": 1}, "does not exist"),
        ({"op": "remove", "path": ""}, "removed the document"),
        ({"op": "add", "path": "spec", "value": 1}, "must be empty or start with /"),
        ({"op": "move", "from": "/spec", "path": "/spec/x"}, "into itself"),
    ]:
        raises(lambda: run({"j": {"match": {"kind": "Deployment"}, "json6902": [op]}}), "mutation j:", "web/deployment.yaml", fragment)


def test_images():
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "p"}, "spec": {"containers": [{"name": "c", "image": "busybox:1.36"}]}}
    cron = {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {"name": "cj"},
        "spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [{"name": "c", "image": "localhost:5000/tool"}]}}}}},
    }
    f = {**files(), "extra.yaml": [pod, cron]}
    images = {
        "busybox": {"tag": "1.37"},
        "ghcr.io/org/web": {"name": "registry.example/web", "digest": "sha256:bbb"},
        "docker.io/envoy": {"tag": "v1"},
        "localhost:5000/tool": {"name": "tool", "tag": "2", "digest": "sha256:ccc"},
    }
    docs, _ = run({"i": {"match": {"kind": "*"}, "images": images}}, f)
    spec = docs["web/deployment.yaml"][0]["spec"]["template"]["spec"]
    assert spec["initContainers"][0]["image"] == "busybox:1.37"
    assert [c["image"] for c in spec["containers"]] == ["registry.example/web@sha256:bbb", "docker.io/envoy:v1"]
    assert docs["extra.yaml"][0]["spec"]["containers"][0]["image"] == "busybox:1.37"
    assert docs["extra.yaml"][1]["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["image"] == "tool:2@sha256:ccc"
    # name only keeps tag and digest
    docs, _ = run({"i": {"match": {"kind": "Deployment"}, "images": {"docker.io/envoy": {"name": "envoy"}}}})
    assert docs["web/deployment.yaml"][0]["spec"]["template"]["spec"]["containers"][1]["image"] == "envoy@sha256:aaa"
    # names compare as written, without registry defaults
    raises(lambda: run({"i": {"match": {"kind": "Deployment"}, "images": {"envoy": {"tag": "v1"}}}}), "mutation i:", "['envoy'] match no container")
    raises(lambda: run({"i": {"match": {"kind": "Service"}, "images": {"busybox": {"tag": "1"}}}}), "match no container")


def test_matched_but_unchanged_files_are_not_returned():
    _, out = run({"t": {"match": {"name": "web"}, "json6902": [{"op": "test", "path": "/metadata/name", "value": "web"}], "expects": 2}})
    assert out == {}
    _, out = run({"i": {"match": {"kind": "*"}, "images": {"busybox": {"tag": "1"}}}})
    assert list(out) == ["web/deployment.yaml"]
