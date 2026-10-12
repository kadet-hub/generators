"""Tests for tools/upstream.py (docs/specs/upstream.md); no network."""

import base64
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import upstream
import yaml

GH = "https://api.github.com/"
RAW = "https://raw.githubusercontent.com/"


def crd(kind, versions):
    spec = {"type": "object", "properties": {"replicas": {"type": "integer"}}}
    schema = {"type": "object", "properties": {"spec": spec}}
    return yaml.safe_dump({
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "spec": {"names": {"kind": kind}, "versions": [{"name": v, "schema": {"openAPIV3Schema": schema}} for v in versions]},
    })


def releases(*tags, prerelease=(), draft=()):
    return [{"tag_name": t, "prerelease": t in prerelease, "draft": t in draft} for t in tags]


class Web:
    """Stub for upstream.get: url -> str (served as is) or JSON-serialisable value; anything else is a 404."""

    def __init__(self, pages):
        self.pages = pages

    def __call__(self, url):
        if url not in self.pages:
            raise OSError(f"404 {url}")
        page = self.pages[url]
        return (page if isinstance(page, str) else json.dumps(page)).encode()


def widget_pages(new_versions=("v1alpha1",)):
    """Upstream example/widgets with a widgets CRD at v1.0.0 and v1.1.0."""
    pages = {f"{GH}repos/example/widgets/releases?per_page=100": releases("v1.1.0", "v1.0.0")}
    for ref, versions in (("v1.0.0", ("v1alpha1",)), ("v1.1.0", new_versions)):
        pages[f"{GH}repos/example/widgets/contents/crds?ref={ref}"] = [
            {"type": "file", "name": "widgets.yaml", "path": "crds/widgets.yaml"},
            {"type": "file", "name": "README.md", "path": "crds/README.md"},
        ]
        pages[f"{RAW}example/widgets/{ref}/crds/widgets.yaml"] = crd("Widget", versions)
    # v1.1.0 changes the schema, so the regenerated file differs from the committed one.
    pages[f"{RAW}example/widgets/v1.1.0/crds/widgets.yaml"] = pages[f"{RAW}example/widgets/v1.1.0/crds/widgets.yaml"].replace("integer", "number")
    return pages


OLD = "https://github.com/example/widgets/tree/v1.0.0/crds"
NEW = "https://github.com/example/widgets/tree/v1.1.0/crds"
GO = "https://github.com/example/gadgets/blob/v2.0.0/pkg/crds_generated.go"
IRONCORE = "https://github.com/ironcore-dev/ironcore/blob/v0.8.0/gen/v3/apis__compute.ironcore.dev__v1alpha1_openapi.json"
WIDGET = {
    "additionalProperties": False,
    "properties": {
        "apiVersion": {"type": "string"},
        "kind": {"type": "string"},
        "metadata": {"type": "object"},
        "spec": {"additionalProperties": False, "properties": {"replicas": {"type": "integer"}}, "type": "object"},
    },
    "type": "object",
}


class Repo(unittest.TestCase):
    """A temporary repository root with one generator, gen, whose example.io group is at widgets v1.0.0."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.group = self.root / "gen" / "schemas" / "example.io"
        self.group.mkdir(parents=True)
        self.sources = self.root / "gen" / "schemas" / "sources.yaml"
        self.sources.write_text(f"# comment\nexample.io:\n  software: Widgets\n  version: 1.0.0\n  source: {OLD}\n  license: Apache-2.0\n")
        (self.root / "gen" / "README.md").write_text("Built for Widgets 1.0.0.\n")
        self.web = Web(widget_pages())
        (self.group / "widget_v1alpha1.json").write_text(json.dumps(WIDGET, indent=2) + "\n")
        for patch in (mock.patch.object(upstream, "ROOT", self.root), mock.patch.object(upstream, "get", self.web)):
            patch.start()
            self.addCleanup(patch.stop)


class Versions(unittest.TestCase):
    def test_semver_after_the_ref_prefix(self):
        self.assertEqual(upstream.semver("v1.10.0", "v"), (1, 10, 0))
        self.assertEqual(upstream.semver("edge-26.10.1", "edge-"), (26, 10, 1))
        self.assertEqual(upstream.semver("26.8.0", ""), (26, 8, 0))
        self.assertIsNone(upstream.semver("v27.0.0", ""))
        self.assertIsNone(upstream.semver("stable-2.14.10", "edge-"))
        self.assertIsNone(upstream.semver("v1.2.0-rc.1", "v"))

    def test_semver_of_a_version_field(self):
        self.assertEqual(upstream.semver("3.5.4"), (3, 5, 4))
        self.assertEqual(upstream.semver("edge-26.6.3"), (26, 6, 3))
        self.assertIsNone(upstream.semver("main@1b6edfb"))

    def test_latest_compares_numerically_and_skips_prereleases_and_drafts(self):
        web = Web({f"{GH}repos/o/r/releases?per_page=100": releases("v1.40.16", "v1.9.0", "v1.44.0", "v1.45.0-rc.1", "v1.46.0", "v1.47.0", prerelease={"v1.46.0"}, draft={"v1.47.0"})})
        with mock.patch.object(upstream, "get", web):
            self.assertEqual(upstream.latest("tag", "o/r", "v1.9.0"), "v1.44.0")

    def test_latest_keeps_the_prefix_of_the_ref(self):
        web = Web({f"{GH}repos/o/r/releases?per_page=100": releases("edge-26.9.3", "edge-26.10.1", "stable-2.99.0", "26.11.0", "v26.12.0")})
        with mock.patch.object(upstream, "get", web):
            self.assertEqual(upstream.latest("tag", "o/r", "edge-26.6.3"), "edge-26.10.1")
            self.assertEqual(upstream.latest("tag", "o/r", "26.8.0"), "26.11.0")
            self.assertEqual(upstream.latest("tag", "o/r", "v26.0.0"), "v26.12.0")

    def test_latest_of_a_commit_is_any_release(self):
        sha = "1b6edfbba0e54af83870b158ee1124e499455b43"
        web = Web({f"{GH}repos/o/r/releases?per_page=100": [], f"{GH}repos/o/r/tags?per_page=100": []})
        with mock.patch.object(upstream, "get", web):
            self.assertIsNone(upstream.latest("commit", "o/r", sha))
        web.pages[f"{GH}repos/o/r/releases?per_page=100"] = releases("v0.1.0")
        with mock.patch.object(upstream, "get", web):
            self.assertEqual(upstream.latest("commit", "o/r", sha), "v0.1.0")

    def test_latest_falls_back_to_tags_without_releases(self):
        web = Web({
            f"{GH}repos/o/r/releases?per_page=100": [],
            f"{GH}repos/o/r/tags?per_page=100": [{"name": n} for n in ("nightly", "26.10.0-rc1", "26.9.0", "26.8.0", "v27.0.0")],
        })
        with mock.patch.object(upstream, "get", web):
            self.assertEqual(upstream.latest("tag", "o/r", "26.8.0"), "26.9.0")

    def test_latest_ignores_tags_when_there_are_releases(self):
        web = Web({f"{GH}repos/o/r/releases?per_page=100": releases("v2.0.0-rc.1", prerelease={"v2.0.0-rc.1"})})
        with mock.patch.object(upstream, "get", web):
            self.assertIsNone(upstream.latest("tag", "o/r", "v1.0.0"))

    def test_latest_terraform_provider(self):
        web = Web({"https://registry.terraform.io/v1/providers/hashicorp/aws": {"version": "6.69.0", "versions": ["6.68.0", "6.69.0", "7.0.0-beta1"]}})
        with mock.patch.object(upstream, "get", web):
            self.assertEqual(upstream.latest("terraform", "hashicorp/aws", "6.68.0"), "6.69.0")


class Sources(unittest.TestCase):
    def test_classify_every_row(self):
        sha = "1b6edfbba0e54af83870b158ee1124e499455b43"
        cases = {
            "https://github.com/argoproj/argo-cd/tree/v3.5.4/manifests/crds": ("tag", "argoproj/argo-cd", "v3.5.4"),
            "https://github.com/projectcalico/calico/blob/v3.33.0/manifests/v3_projectcalico_org.yaml": ("tag", "projectcalico/calico", "v3.33.0"),
            IRONCORE: ("tag", "ironcore-dev/ironcore", "v0.8.0"),
            "https://github.com/yannh/kubernetes-json-schema/tree/8df8a883b68a24a104b4a9e43c1288090ae60b3b/v1.35.0-standalone-strict": ("kubernetes", "kubernetes/kubernetes", "8df8a883b68a24a104b4a9e43c1288090ae60b3b"),
            "https://registry.terraform.io/providers/hashicorp/aws/6.68.0": ("terraform", "hashicorp/aws", "6.68.0"),
            f"https://github.com/thanos-community/thanos-operator/tree/{sha}/config/crd/bases": ("commit", "thanos-community/thanos-operator", sha),
            "https://gitlab.com/o/r/-/tree/v1.0.0/crds": None,
            "https://example.org/crds.yaml": None,
        }
        for url, expected in cases.items():
            self.assertEqual(upstream.classify(url), expected, url)

    def test_not_regenerable(self):
        cases = {
            "https://github.com/kubevirt/kubevirt/blob/v1.9.0/pkg/virt-operator/resource/generate/components/validations_generated.go": "Go code",
            "https://github.com/linkerd/linkerd2/tree/edge-26.6.3/charts/linkerd-crds/templates": "Helm templates",
            "https://github.com/linkerd/linkerd2/tree/edge-26.6.3/charts/linkerd-crds/templates/policy": "Helm templates",
            "https://registry.terraform.io/providers/hashicorp/aws/6.68.0": "Terraform extract",
            "https://github.com/yannh/kubernetes-json-schema/tree/8df8a883b68a24a104b4a9e43c1288090ae60b3b/v1.35.0-standalone-strict": "kubernetes-json-schema",
            "https://github.com/argoproj/argo-cd/tree/v3.5.4/manifests/crds": None,
            "https://github.com/projectcalico/calico/blob/v3.33.0/manifests/v3_projectcalico_org.yaml": None,
            IRONCORE: None,
        }
        for url, expected in cases.items():
            self.assertEqual(upstream.not_regenerable(upstream.classify(url)[0], url), expected, url)


class Render(unittest.TestCase):
    def test_closes_like_kubeconform_strict_and_adds_the_implicit_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "properties": {
                    "properties": {"type": "object", "properties": {"a": {"type": "string"}}},
                    "open": {"type": "object", "x-kubernetes-preserve-unknown-fields": True, "properties": {"b": {"type": "object", "properties": {"c": {"type": "string"}}}}},
                    "labels": {"type": "object", "additionalProperties": {"type": "object", "properties": {"d": {"type": "string"}}}},
                    "list": {"type": "array", "items": {"type": "object", "properties": {"e": {"type": "string"}}}},
                    "either": {"type": "object", "properties": {"f": {"type": "string"}}, "anyOf": [{"properties": {"f": {"type": "string"}}}]},
                }},
            },
        }
        out = json.loads(upstream.render(schema, '{\n  "type": "object"\n}\n'))
        spec = out["properties"]["spec"]
        self.assertFalse(out["additionalProperties"])
        self.assertEqual(out["properties"]["metadata"], {"type": "object"})
        self.assertEqual(out["properties"]["apiVersion"], {"type": "string"})
        self.assertFalse(spec["additionalProperties"])
        self.assertNotIn("additionalProperties", spec["properties"])  # a field named properties is a field
        self.assertFalse(spec["properties"]["properties"]["additionalProperties"])
        self.assertNotIn("additionalProperties", spec["properties"]["open"])
        self.assertFalse(spec["properties"]["open"]["properties"]["b"]["additionalProperties"])
        self.assertEqual(spec["properties"]["labels"]["additionalProperties"]["additionalProperties"], False)
        self.assertFalse(spec["properties"]["list"]["items"]["additionalProperties"])
        self.assertFalse(spec["properties"]["either"]["additionalProperties"])
        self.assertNotIn("additionalProperties", spec["properties"]["either"]["anyOf"][0])

    def upstream_schema(self):
        return {"description": "Upstream text.", "properties": {"spec": {"type": "object", "properties": {"b": {"type": "string"}, "a": {"type": "string"}}}}, "type": "object"}

    def closed(self, top):
        spec = {"type": "object", "properties": {"b": {"type": "string"}, "a": {"type": "string"}}, "additionalProperties": False}
        props = {"spec": spec, "apiVersion": {"type": "string"}, "kind": {"type": "string"}, "metadata": {"type": "object"}}
        values = {"description": "Hand-written.", "properties": props, "type": "object", "additionalProperties": False, "$id": "https://example.io/v1/widget.json", "$schema": "http://json-schema.org/draft-07/schema#", "title": "Widget"}
        return {k: values[k] for k in top}

    def test_keeps_annotations_and_sorted_layout(self):
        for indent in (2, 4):
            committed = json.dumps(self.closed(["description", "properties", "type", "additionalProperties", "$id", "$schema", "title"]), indent=indent, sort_keys=True) + "\n"
            self.assertEqual(upstream.render(self.upstream_schema(), committed), committed)

    def test_keeps_a_compact_layout(self):
        committed = json.dumps(self.closed(["$id", "description", "properties", "type", "additionalProperties"]), separators=(",", ":"), sort_keys=True) + "\n"
        self.assertEqual(upstream.render(self.upstream_schema(), committed), committed)

    def test_unsorted_keeps_upstream_order_below_and_the_committed_order_on_top(self):
        for top in (
            ["description", "properties", "type", "$schema", "$id", "title", "additionalProperties"],
            ["description", "type", "properties", "additionalProperties", "$schema", "$id", "title"],
            ["description", "properties", "type", "additionalProperties"],
        ):
            committed = json.dumps(self.closed(top), indent=2) + "\n"
            self.assertEqual(upstream.render(self.upstream_schema(), committed), committed, top)

    def test_does_not_add_annotations_the_committed_file_lacks(self):
        committed = json.dumps(self.closed(["additionalProperties", "properties", "type"]), indent=2, sort_keys=True) + "\n"
        out = json.loads(upstream.render({"properties": {"spec": self.upstream_schema()["properties"]["spec"]}, "type": "object"}, committed))
        self.assertNotIn("$id", out)
        self.assertNotIn("description", out)


class Gate(Repo):
    def test_reproduces_then_regenerates_at_the_new_tag(self):
        files, cause = upstream.gate(self.group, [OLD], [NEW])
        self.assertIsNone(cause)
        self.assertIn('"type": "number"', files["widget_v1alpha1.json"])

    def test_differs_is_an_issue_cause(self):
        path = self.group / "widget_v1alpha1.json"
        path.write_text(path.read_text().replace('"integer"', '"string"'))
        files, cause = upstream.gate(self.group, [OLD], [NEW])
        self.assertIsNone(files)
        self.assertEqual(cause, "does not reproduce: widget_v1alpha1.json differs")

    def test_missing_kind_or_version_at_the_new_tag_is_an_issue_cause(self):
        self.web.pages.update(widget_pages(new_versions=("v1beta1",)))
        files, cause = upstream.gate(self.group, [OLD], [NEW])
        self.assertIsNone(files)
        self.assertEqual(cause, "missing at the new release: widget_v1alpha1.json")

    def test_crd_patch_without_versions_is_skipped(self):
        patch = yaml.safe_dump({"apiVersion": "apiextensions.k8s.io/v1", "kind": "CustomResourceDefinition",
                                "spec": {"conversion": {"strategy": "Webhook"}}})
        for ref in ("v1.0.0", "v1.1.0"):
            self.web.pages[f"{RAW}example/widgets/{ref}/crds/widgets.yaml"] += "---\n" + patch
        files, cause = upstream.gate(self.group, [OLD], [NEW])
        self.assertIsNone(cause)
        self.assertEqual(list(files), ["widget_v1alpha1.json"])

    def test_no_crd_at_the_current_ref_does_not_reproduce(self):
        self.web.pages[f"{RAW}example/widgets/v1.0.0/crds/widgets.yaml"] = crd("Gadget", ("v1alpha1",))
        self.assertEqual(upstream.gate(self.group, [OLD], [NEW]), (None, "does not reproduce: no CRD for widget_v1alpha1.json"))

    def test_unreadable_source_at_the_new_tag_raises(self):
        del self.web.pages[f"{GH}repos/example/widgets/contents/crds?ref=v1.1.0"]
        with self.assertRaises(OSError):
            upstream.gate(self.group, [OLD], [NEW])


def openapi(replicas="integer", kind="Gizmo"):
    """OpenAPI v3 document of an aggregated API server with one kind; components unsorted, one self-referencing, one unused."""
    ref = "#/components/schemas/"
    return {"openapi": "3.0.0", "components": {"schemas": {
        "meta.ObjectMeta": {"type": "object", "properties": {"name": {"type": "string"}}},
        "io.example.v1alpha1.Gizmo": {
            "type": "object",
            "properties": {
                "apiVersion": {"type": "string"},
                "kind": {"type": "string"},
                "metadata": {"default": {}, "allOf": [{"$ref": ref + "meta.ObjectMeta"}]},
                "spec": {"default": {}, "allOf": [{"$ref": ref + "io.example.v1alpha1.GizmoSpec"}]},
            },
            "x-kubernetes-group-version-kind": [{"group": "gizmos.example.io", "kind": kind, "version": "v1alpha1"}],
        },
        "io.example.v1alpha1.GizmoSpec": {"type": "object", "properties": {
            "replicas": {"type": replicas},
            "size": {"$ref": ref + "Quantity"},
            "parts": {"type": "array", "items": {"$ref": ref + "io.example.v1alpha1.GizmoSpec"}},
        }},
        "Quantity": {"type": "string"},
        "meta.Unused": {"type": "object", "properties": {"x": {"type": "string"}}},
    }}}


OAPI = "gen/v3/apis__gizmos.example.io__v1alpha1_openapi.json"
OAPI_OLD = f"https://github.com/example/gizmos/blob/v1.0.0/{OAPI}"
OAPI_NEW = f"https://github.com/example/gizmos/blob/v1.1.0/{OAPI}"
GIZMO = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "apiVersion": {"type": "string"},
        "kind": {"type": "string"},
        "metadata": {"default": {}, "allOf": [{"$ref": "#/definitions/meta.ObjectMeta"}]},
        "spec": {"default": {}, "allOf": [{"$ref": "#/definitions/io.example.v1alpha1.GizmoSpec"}]},
    },
    "x-kubernetes-group-version-kind": [{"group": "gizmos.example.io", "kind": "Gizmo", "version": "v1alpha1"}],
    "additionalProperties": False,
    "definitions": {
        "Quantity": {"type": "string"},
        "io.example.v1alpha1.GizmoSpec": {"type": "object", "properties": {
            "replicas": {"type": "integer"},
            "size": {"$ref": "#/definitions/Quantity"},
            "parts": {"type": "array", "items": {"$ref": "#/definitions/io.example.v1alpha1.GizmoSpec"}},
        }, "additionalProperties": False},
        "meta.ObjectMeta": {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False},
    },
}


class OpenAPI(Repo):
    """gizmos.example.io, a group served by an aggregated API server, from its OpenAPI v3 document."""

    def setUp(self):
        super().setUp()
        self.group = self.root / "gen" / "schemas" / "gizmos.example.io"
        self.group.mkdir()
        (self.group / "gizmo_v1alpha1.json").write_text(json.dumps(GIZMO, indent=2) + "\n")
        self.web.pages[f"{RAW}example/gizmos/v1.0.0/{OAPI}"] = openapi()
        self.web.pages[f"{RAW}example/gizmos/v1.1.0/{OAPI}"] = openapi(replicas="number")

    def test_reproduces_then_regenerates_at_the_new_tag(self):
        files, cause = upstream.gate(self.group, [OAPI_OLD], [OAPI_NEW])
        self.assertIsNone(cause)
        self.assertEqual(json.loads(files["gizmo_v1alpha1.json"])["definitions"]["io.example.v1alpha1.GizmoSpec"]["properties"]["replicas"], {"type": "number"})

    def test_missing_kind_at_the_new_tag_is_an_issue_cause(self):
        self.web.pages[f"{RAW}example/gizmos/v1.1.0/{OAPI}"] = openapi(kind="Widget")
        self.assertEqual(upstream.gate(self.group, [OAPI_OLD], [OAPI_NEW]), (None, "missing at the new release: gizmo_v1alpha1.json"))

    def test_json_without_components_does_not_reproduce(self):
        self.web.pages[f"{RAW}example/gizmos/v1.0.0/{OAPI}"] = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"}
        self.assertEqual(upstream.gate(self.group, [OAPI_OLD], [OAPI_NEW]), (None, "does not reproduce: no CRD for gizmo_v1alpha1.json"))


class Outdated(Repo):
    def test_reports_the_newer_release_with_files(self):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            (update,) = upstream.outdated("gen")
        self.assertEqual(update["old"], [(OLD, "1.0.0")])
        self.assertEqual(update["new"], [(NEW, "1.1.0")])
        self.assertIsNone(update["cause"])
        self.assertEqual(list(update["files"]), ["widget_v1alpha1.json"])
        self.assertIn("gen example.io: current 1.0.0, latest v1.1.0", log.getvalue())

    def test_up_to_date_is_no_update(self):
        self.web.pages[f"{GH}repos/example/widgets/releases?per_page=100"] = releases("v1.0.0")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(upstream.outdated("gen"), [])

    def test_source_not_regenerable_is_an_issue_cause(self):
        go = "https://github.com/example/widgets/blob/v1.0.0/pkg/crds_generated.go"
        self.sources.write_text(self.sources.read_text().replace(OLD, go))
        with contextlib.redirect_stdout(io.StringIO()):
            (update,) = upstream.outdated("gen")
        self.assertEqual(update["cause"], "not regenerable: Go code")
        self.assertIsNone(update["files"])


UPDATE = {"group": "kubevirt.io", "software": "KubeVirt", "old": [("u", "1.9.0")], "new": [("u", "1.10.0")], "files": {}, "cause": None}


class Titles(unittest.TestCase):
    def test_issue_title(self):
        updates = [UPDATE, dict(UPDATE, group="pool.kubevirt.io"), dict(UPDATE, software="KubeVirt Containerized Data Importer (CDI)", new=[("u", "1.67.0")])]
        self.assertEqual(upstream.issue_title("kubevirt", updates), "[upstream] kubevirt: KubeVirt 1.10.0, KubeVirt Containerized Data Importer (CDI) 1.67.0")

    def test_issue_title_of_a_group_with_two_sources(self):
        update = dict(UPDATE, software="RabbitMQ Cluster Operator / Messaging Topology Operator", new=[("a", "2.24.0"), ("b", "1.20.3")])
        self.assertEqual(upstream.issue_title("rabbitmq", [update]), "[upstream] rabbitmq: RabbitMQ Cluster Operator / Messaging Topology Operator 2.24.0 / 1.20.3")

    def test_pr_title_is_a_conventional_commit(self):
        self.assertEqual(upstream.pr_title("kubevirt", [UPDATE]), "feat(kubevirt): update schemas to KubeVirt 1.10.0")

    def test_bodies(self):
        pr = upstream.body([UPDATE], "check passed", True)
        self.assertIn("| `kubevirt.io` | KubeVirt | 1.9.0 | 1.10.0 |\n", pr)
        self.assertIn("```\ncheck passed\n```", pr)
        issue = upstream.body([dict(UPDATE, cause="not regenerable: Go code")], None, False)
        self.assertIn("| `kubevirt.io` | KubeVirt | 1.9.0 | 1.10.0 | not regenerable: Go code |\n", issue)
        mixed = upstream.body([UPDATE, dict(UPDATE, group="core", cause="not regenerable: kubernetes-json-schema")], None, False)
        self.assertIn("| `kubevirt.io` | KubeVirt | 1.9.0 | 1.10.0 | regenerates |\n", mixed)


class Edits(unittest.TestCase):
    def test_bump_sources_changes_one_group_and_keeps_comments(self):
        text = "# KubeVirt 1.9.0\nkubevirt.io:\n  software: KubeVirt\n  version: 1.9.0\n  source: https://x/v1.9.0/a.go\npool.kubevirt.io:\n  software: KubeVirt\n  version: 1.9.0\n  source: https://x/v1.9.0/a.go\n"
        update = dict(UPDATE, new=[("https://x/v1.10.0/a.go", "1.10.0")])
        self.assertEqual(upstream.bump_sources(text, update), text.replace("  version: 1.9.0\n  source: https://x/v1.9.0/a.go\npool", "  version: 1.10.0\n  source: https://x/v1.10.0/a.go\npool"))

    def test_bump_readme_changes_built_for_lines_only(self):
        text = "Built for Calico 3.33.0 (Tigera operator 1.44.0), not 11.44.0 or 1.44.01.\nTigera operator 1.44.0 elsewhere.\n"
        update = dict(UPDATE, old=[("u", "1.44.0")], new=[("u", "1.45.0")])
        self.assertEqual(upstream.bump_readme(text, [update]), "Built for Calico 3.33.0 (Tigera operator 1.45.0), not 11.44.0 or 1.44.01.\nTigera operator 1.44.0 elsewhere.\n")


class Mixed(Repo):
    """gen with example.io, which regenerates, and other.io, whose source is Go code."""

    def setUp(self):
        super().setUp()
        self.sources.write_text(self.sources.read_text() + f"other.io:\n  software: Gadgets\n  version: 2.0.0\n  source: {GO}\n")
        self.web.pages[f"{GH}repos/example/gadgets/releases?per_page=100"] = releases("v2.1.0")
        with contextlib.redirect_stdout(io.StringIO()):
            self.updates = upstream.outdated("gen")

    def act(self, check=None):
        calls = []
        checker = mock.patch.object(subprocess, "run", return_value=check) if check else mock.patch.object(subprocess, "run", refuse)
        with mock.patch.object(upstream, "run", lambda *cmd: calls.append(cmd)), checker, contextlib.redirect_stdout(io.StringIO()) as log:
            upstream.act("gen", self.updates, {}, [], check is None)
        return calls, log.getvalue()

    def test_dry_run_proposes_a_pull_request_and_an_issue(self):
        calls, log = self.act()
        self.assertEqual(calls, [])
        self.assertIn("gen: would open a pull request from upstream/gen if ./check passes: feat(gen): update schemas to Widgets 1.1.0", log)
        self.assertIn("gen: would open an issue: [upstream] gen: Gadgets 2.1.0", log)

    def test_passing_check_opens_both_and_bumps_only_the_regenerated_group(self):
        calls, _ = self.act(subprocess.CompletedProcess(["./check", "gen"], 0, stdout="check passed\n"))
        self.assertEqual([c[:3] for c in calls[-2:]], [("gh", "pr", "create"), ("gh", "issue", "create")])
        self.assertEqual(calls[-1][4], "[upstream] gen: Gadgets 2.1.0")
        self.assertNotIn("Widgets", calls[-1][6])
        self.assertIn(f"  version: 1.1.0\n  source: {NEW}\n", self.sources.read_text())
        self.assertIn(f"  version: 2.0.0\n  source: {GO}\n", self.sources.read_text())

    def test_failing_check_puts_every_group_in_the_issue(self):
        calls, _ = self.act(subprocess.CompletedProcess(["./check", "gen"], 1, stdout="E501 line too long\n"))
        (call,) = calls
        self.assertEqual(call[:5], ("gh", "issue", "create", "--title", "[upstream] gen: Widgets 1.1.0, Gadgets 2.1.0"))
        self.assertIn("| `example.io` | Widgets | 1.0.0 | 1.1.0 | `./check` fails |", call[6])
        self.assertIn("| `other.io` | Gadgets | 2.0.0 | 2.1.0 | not regenerable: Go code |", call[6])
        self.assertIn("E501 line too long", call[6])


def refuse(*cmd, **_):
    raise AssertionError(f"write in a dry run: {cmd}")


class Act(Repo):
    def updates(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return upstream.outdated("gen")

    def act(self, updates, prs=None, issues=(), dry_run=True):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            upstream.act("gen", updates, prs or {}, list(issues), dry_run)
        return log.getvalue()

    def test_dry_run_prints_the_pull_request_and_writes_nothing(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(upstream, "run", refuse), mock.patch.object(subprocess, "run", refuse):
            log = self.act(self.updates())
        self.assertIn("gen: would open a pull request from upstream/gen if ./check passes: feat(gen): update schemas to Widgets 1.1.0", log)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_dry_run_prints_the_issue(self):
        updates = [dict(u, cause="does not reproduce: widget_v1alpha1.json", files=None) for u in self.updates()]
        issue = {"number": 7, "title": "[upstream] gen: Widgets 1.0.5", "body": "old"}
        with mock.patch.object(upstream, "run", refuse), mock.patch.object(subprocess, "run", refuse):
            self.assertIn("gen: would open an issue: [upstream] gen: Widgets 1.1.0", self.act(updates))
            self.assertIn("gen: would update issue #7: [upstream] gen: Widgets 1.1.0", self.act(updates, issues=[issue]))
            current = dict(issue, title="[upstream] gen: Widgets 1.1.0", body=upstream.body(updates, None, False))
            self.assertIn("gen: issue #7 is up to date", self.act(updates, issues=[current]))

    def test_open_pull_request_with_these_versions_is_left_alone(self):
        updates = self.updates()
        sources = upstream.bump_sources(self.sources.read_text(), updates[0])
        self.web.pages[f"{upstream.REPO}contents/gen/schemas/sources.yaml?ref=upstream/gen"] = {"content": base64.b64encode(sources.encode()).decode()}
        with mock.patch.object(upstream, "run", refuse), mock.patch.object(subprocess, "run", refuse):
            self.assertIn("gen: pull request #3 already proposes these versions", self.act(updates, prs={"upstream/gen": {"number": 3}}, dry_run=False))

    def test_passing_check_opens_a_pull_request_with_the_bumped_files(self):
        calls = []
        check = subprocess.CompletedProcess(["./check", "gen"], 0, stdout="check passed\n")
        with mock.patch.object(upstream, "run", lambda *cmd: calls.append(cmd)), mock.patch.object(subprocess, "run", return_value=check):
            self.act(self.updates(), dry_run=False)
        self.assertEqual([c[:2] for c in calls], [("git", "checkout"), ("git", "add"), ("git", "commit"), ("git", "push"), ("gh", "pr")])
        self.assertEqual(calls[3], ("git", "push", "--force", "origin", "upstream/gen"))
        self.assertEqual(calls[4][:3], ("gh", "pr", "create"))
        self.assertIn(f"  version: 1.1.0\n  source: {NEW}\n", self.sources.read_text())
        self.assertEqual((self.root / "gen" / "README.md").read_text(), "Built for Widgets 1.1.0.\n")
        self.assertIn('"type": "number"', (self.group / "widget_v1alpha1.json").read_text())

    def test_failing_check_is_an_issue_cause_with_its_tail(self):
        calls = []
        check = subprocess.CompletedProcess(["./check", "gen"], 1, stdout="## ruff (QA-3)\nE501 line too long\n")
        with mock.patch.object(upstream, "run", lambda *cmd: calls.append(cmd)), mock.patch.object(subprocess, "run", return_value=check):
            self.act(self.updates(), dry_run=False)
        (call,) = calls
        self.assertEqual(call[:5], ("gh", "issue", "create", "--title", "[upstream] gen: Widgets 1.1.0"))
        self.assertIn("| `./check` fails |", call[6])
        self.assertIn("E501 line too long", call[6])


if __name__ == "__main__":
    unittest.main()
