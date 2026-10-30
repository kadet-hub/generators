"""Unit tests of the tetragon generator (docs/specs/tetragon.md); command in the spec's implementation inventory."""

import logging

from box import Box

from .. import inv, main

KPROBE = {"call": "security_file_permission", "syscall": False}


def render(parameters_namespace=None, **generator):
    inv["parameters"] = Box(generators={"tetragon": generator})
    if parameters_namespace:
        inv["parameters"]["namespace"] = parameters_namespace
    return {key: obj.root.to_dict() for key, obj in main({}).root.items()}


def test_tracing_policy():
    out = render(parameters_namespace="workloads", tracing_policies={"write-etc": {"kprobes": [KPROBE]}})
    assert out == {
        "write-etc-tracingpolicy": {
            "apiVersion": "cilium.io/v1alpha1",
            "kind": "TracingPolicy",
            "metadata": {"name": "write-etc", "labels": {"name": "write-etc"}},
            "spec": {"kprobes": [KPROBE]},
        }
    }


def test_namespace_fallback():
    policies = {"a": {}, "b": {"namespace": "data"}}
    assert set(render(tracing_policies_namespaced=policies)) == {
        "default/a-tracingpolicynamespaced",
        "data/b-tracingpolicynamespaced",
    }
    assert set(render(parameters_namespace="workloads", tracing_policies_namespaced=policies)) == {
        "workloads/a-tracingpolicynamespaced",
        "data/b-tracingpolicynamespaced",
    }
    out = render(parameters_namespace="workloads", namespace="apps", tracing_policies_namespaced=policies)
    assert out["apps/a-tracingpolicynamespaced"]["metadata"]["namespace"] == "apps"
    assert out["data/b-tracingpolicynamespaced"]["metadata"]["namespace"] == "data"


def test_name_names_the_resource():
    out = render(tracing_policies={"sigkill": {"name": "kill-tmp"}, "other": {}})
    assert set(out) == {"kill-tmp-tracingpolicy", "other-tracingpolicy"}
    assert out["kill-tmp-tracingpolicy"]["metadata"]["name"] == "kill-tmp"


def test_same_name_fails():
    try:
        render(tracing_policies_namespaced={"a": {"name": "b"}, "b": {}})
    except ValueError as e:
        assert str(e) == "tetragon: tracing_policies_namespaced 'a' and 'b' both render 'b' in namespace 'default'"
    else:
        raise AssertionError("two entries rendering one name compiled")
    # Different namespaces do not clash.
    assert len(render(tracing_policies_namespaced={"a": {"name": "b", "namespace": "x"}, "b": {}})) == 2


def test_spec_and_flat_keys(caplog):
    with caplog.at_level(logging.WARNING):
        out = render(
            tracing_policies={
                "p": {
                    "labels": {"team": "platform"},
                    "annotations": {"example.com/owner": "platform"},
                    "spec": {"kprobes": [KPROBE], "podSelector": {"matchLabels": {"app": "old"}}},
                    "pod_selector": {"matchLabels": {"app": "web"}},
                    "selectors_macros": {"m": [{"matchBinaries": []}]},
                }
            }
        )["p-tracingpolicy"]
    assert out["metadata"]["labels"] == {"name": "p", "team": "platform"}
    assert out["metadata"]["annotations"] == {"example.com/owner": "platform"}
    assert out["spec"] == {
        "kprobes": [KPROBE],
        "podSelector": {"matchLabels": {"app": "web"}},
        "selectorsMacros": {"m": [{"matchBinaries": []}]},
    }
    assert "Flat key 'pod_selector' overrides spec passthrough 'podSelector'" in caplog.text
