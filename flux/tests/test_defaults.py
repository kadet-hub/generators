"""Unit tests of the flux generator (docs/specs/flux.md); command in the spec's implementation inventory."""

from kapitan.inputs.kadet import inventory_global

from .. import main


def render(**sections):
    inventory_global()["unit-test"] = {"parameters": {"generators": {"flux": sections}}}
    return {key: obj for key, obj in main({}).root.items()}


def test_oci_repository_defaults():
    out = render(oci_repositories={"plain": {"url": "oci://r.example/a"}, "set": {"url": "oci://r.example/b", "provider": "aws", "spec": {"timeout": "2m"}}})
    plain, other = out["flux-system/plain-ocirepository"]["spec"], out["flux-system/set-ocirepository"]["spec"]
    assert (plain["provider"], plain["timeout"]) == ("generic", "60s"), plain
    assert (other["provider"], other["timeout"]) == ("aws", "2m"), other


def test_helm_chart_template_defaults():
    out = render(
        helm_repositories={"charts": {"url": "https://charts.example"}},
        helm_releases={
            "plain": {"source": "charts"},
            "pinned": {"source": "charts", "version": "1.2.3"},
            "passthrough": {"spec": {"chart": {"spec": {"chart": "x", "sourceRef": {"kind": "HelmRepository", "name": "charts"}, "reconcileStrategy": "Revision"}}}},
        },
    )
    chart = {name: out[f"flux-system/{name}-helmrelease"]["spec"]["chart"]["spec"] for name in ("plain", "pinned", "passthrough")}
    assert (chart["plain"]["version"], chart["plain"]["reconcileStrategy"]) == ("*", "ChartVersion"), chart
    assert (chart["pinned"]["version"], chart["pinned"]["reconcileStrategy"]) == ("1.2.3", "ChartVersion"), chart
    assert (chart["passthrough"]["version"], chart["passthrough"]["reconcileStrategy"]) == ("*", "Revision"), chart


def test_oci_chart_template_passes_through():
    chart = {"kind": "OCIRepository", "spec": {"url": "oci://r.example/charts/x", "ref": {"tag": "1.0.0"}}}
    out = render(helm_releases={"inline": {"spec": {"chart": chart}}})
    assert out["flux-system/inline-helmrelease"]["spec"]["chart"] == chart


def test_non_mapping_chart_passes_through():
    # no template, so no defaults; the gate's schema check reports it as before (FLX-2)
    out = render(helm_releases={"bad": {"spec": {"chart": "podinfo"}}, "bad-spec": {"spec": {"chart": {"spec": "podinfo"}}}})
    assert out["flux-system/bad-helmrelease"]["spec"]["chart"] == "podinfo"
    assert out["flux-system/bad-spec-helmrelease"]["spec"]["chart"] == {"spec": "podinfo"}
