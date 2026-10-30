"""Flux resource generator for Kapitan.

Renders GitRepository, OCIRepository and HelmRepository sources and the
Kustomizations and HelmReleases that consume them; see README.md for the
inventory contract.
"""

from __future__ import annotations

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

__version__ = "1.1.0"

logger = logging.getLogger(__name__)
WARNING = "Flat key '%s' overrides spec passthrough '%s' for resource '%s'"

SOURCE = "source.toolkit.fluxcd.io/v1"
HELM_CHART_LAYER = {
    "mediaType": "application/vnd.cncf.helm.chart.content.v1.tar+gzip",
    "operation": "copy",
}

# section: (apiVersion, kind, output suffix, defaults, {flat key: spec field})
SECTIONS = {
    "git_repositories": (
        SOURCE,
        "GitRepository",
        "gitrepository",
        {"interval": "1m0s"},
        {
            "url": "url",
            "ref": "ref",
            "interval": "interval",
            "timeout": "timeout",
            "secret_ref": "secretRef",
            "ignore": "ignore",
        },
    ),
    "oci_repositories": (
        SOURCE,
        "OCIRepository",
        "ocirepository",
        # provider and timeout: CRD defaults until source-controller 1.9 (FLX-1)
        {"interval": "5m", "provider": "generic", "timeout": "60s"},
        {
            "url": "url",
            "ref": "ref",
            "interval": "interval",
            "timeout": "timeout",
            "secret_ref": "secretRef",
            "provider": "provider",
            "layer_selector": "layerSelector",
        },
    ),
    "helm_repositories": (
        SOURCE,
        "HelmRepository",
        "helmrepository",
        {},
        {
            "url": "url",
            "type": "type",
            "interval": "interval",
            "timeout": "timeout",
            "secret_ref": "secretRef",
            "provider": "provider",
        },
    ),
    "kustomizations": (
        "kustomize.toolkit.fluxcd.io/v1",
        "Kustomization",
        "kustomization",
        {"interval": "60m0s", "retryInterval": "2m0s", "timeout": "3m0s", "wait": True, "prune": False},
        {
            "path": "path",
            "prune": "prune",
            "interval": "interval",
            "retry_interval": "retryInterval",
            "timeout": "timeout",
            "wait": "wait",
            "target_namespace": "targetNamespace",
            "depends_on": "dependsOn",
            "service_account_name": "serviceAccountName",
            "post_build": "postBuild",
            "patches": "patches",
            "components": "components",
        },
    ),
    "helm_releases": (
        "helm.toolkit.fluxcd.io/v2",
        "HelmRelease",
        "helmrelease",
        {"interval": "30m"},
        {
            "release_name": "releaseName",
            "target_namespace": "targetNamespace",
            "interval": "interval",
            "timeout": "timeout",
            "depends_on": "dependsOn",
            "service_account_name": "serviceAccountName",
            "values": "values",
            "values_from": "valuesFrom",
            "install": "install",
            "upgrade": "upgrade",
        },
    ),
}
SOURCE_SECTIONS = ("git_repositories", "oci_repositories", "helm_repositories")
CHART_REF_KINDS = ("OCIRepository", "HelmChart", "ExternalArtifact")
KUSTOMIZATION_SOURCES = ("GitRepository", "OCIRepository", "Bucket", "ExternalArtifact")
REF_SHORTHAND = {"git_repositories": "branch", "oci_repositories": "tag"}


def _plain(obj: Any) -> Any:
    """Inventory values (dicts or OmegaConf containers) as plain Python values."""
    if type(obj).__name__ in ("DictConfig", "ListConfig"):
        from omegaconf import OmegaConf

        obj = OmegaConf.to_container(obj, resolve=True)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


def _ref(value: Any) -> Any:
    """A bare string names the referenced object: ``x`` -> ``{name: x}``."""
    return {"name": value} if isinstance(value, str) else value


def _flat(section: str, key: str, value: Any) -> Any:
    """A flat key's value with its shorthand expanded."""
    if key == "secret_ref":
        return _ref(value)
    if key == "depends_on":
        return [_ref(v) for v in value]
    if key == "ref" and isinstance(value, str):
        return {REF_SHORTHAND[section]: value}
    return value


def _source_ref(value: Any, sources: dict, consumer: str, namespace: str) -> dict:
    """``source`` -> {kind, name, namespace}; a name is looked up among the sources of this inventory."""
    if isinstance(value, str):
        found = [(kind, ns) for (kind, name), ns in sources.items() if name == value]
        if len(found) != 1:
            what = "no source" if not found else "several sources"
            raise ValueError(f"flux: {consumer} names {what} '{value}'; use source: {{kind, name}}")
        kind, ns = found[0]
        return {"kind": kind, "name": value, "namespace": ns}
    if not value.get("kind") or not value.get("name"):
        raise ValueError(f"flux: {consumer} source {value} has no kind or name; use source: {{kind, name}}")
    return {"namespace": namespace, **value}


def _consumer(section: str, name: str, config: dict, ref: dict) -> tuple[str, dict]:
    """(spec field, value) that links a Kustomization or HelmRelease to its source."""
    consumer = f"{SECTIONS[section][1]} {ref['consumer']}/{name}"
    if section == "kustomizations":
        if ref["kind"] not in KUSTOMIZATION_SOURCES:
            raise ValueError(f"flux: {consumer} source '{ref['name']}' is a {ref['kind']}; use a GitRepository or OCIRepository")
        return "sourceRef", ref["ref"]
    if ref["kind"] in CHART_REF_KINDS:
        if config.get("chart") is not None or config.get("version") is not None:
            raise ValueError(f"flux: {consumer} takes its chart from {ref['kind']} '{ref['name']}'; set the version as its ref, not chart or version")
        return "chartRef", ref["ref"]
    if ref["kind"] != "HelmRepository" and config.get("chart") is None:
        raise ValueError(f"flux: {consumer} needs chart, the chart's path in {ref['kind']} '{ref['name']}'")
    if isinstance(config.get("version"), float):
        raise ValueError(f"flux: {consumer} version {config['version']} is a number; quote it")
    chart = {"chart": config.get("chart", name), "sourceRef": ref["ref"]}
    if config.get("version") is not None:
        chart["version"] = str(config["version"])
    return "chart", {"spec": chart}


def _resource(section: str, name: str, config: dict, namespace: str, ref: dict | None) -> dict:
    api_version, kind, _, defaults, flat_keys = SECTIONS[section]
    passthrough = config.get("spec") or {}
    spec = {**defaults, **passthrough}
    for key, field in flat_keys.items():
        if config.get(key) is None:
            continue
        if field in passthrough:
            logger.warning(WARNING, key, field, name)
        spec[field] = _flat(section, key, config[key])

    if section == "helm_repositories" and str(spec.get("url", "")).startswith("oci://"):
        spec.setdefault("type", "oci")
    if ref is not None:
        field, value = _consumer(section, name, config, ref)
        if field in passthrough:
            logger.warning(WARNING, "source", field, name)
        spec[field] = value
    if section == "helm_releases" and ("chart" in spec) == ("chartRef" in spec):
        raise ValueError(f"flux: HelmRelease {namespace}/{name} needs exactly one of source, spec.chart or spec.chartRef")
    # CRD defaults of a HelmChart template until helm-controller 1.6 (FLX-2)
    if section == "helm_releases" and "chart" in spec and spec["chart"].get("kind", "HelmChart") == "HelmChart":
        chart_spec = {"version": "*", "reconcileStrategy": "ChartVersion", **(spec["chart"].get("spec") or {})}
        spec["chart"] = {**spec["chart"], "spec": chart_spec}

    metadata = {"name": name, "namespace": namespace}
    for key in ("labels", "annotations"):
        if config.get(key):
            metadata[key] = {str(k): str(v) for k, v in config[key].items()}
    return {"apiVersion": api_version, "kind": kind, "metadata": metadata, "spec": spec}


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.flux."""
    config = _plain(inventory().parameters.get("generators", {}).get("flux", {}) or {})
    default_namespace = config.get("namespace", "flux-system")
    entries = {
        section: {name: entry or {} for name, entry in (config.get(section) or {}).items()}
        for section in SECTIONS
    }
    sources = {
        (SECTIONS[section][1], name): entry.get("namespace", default_namespace)
        for section in SOURCE_SECTIONS
        for name, entry in entries[section].items()
    }
    # Resolve every source once; record which consumers use each OCIRepository.
    refs, oci_users = {}, {}
    for section in ("kustomizations", "helm_releases"):
        for name, entry in entries[section].items():
            if entry.get("source") is None:
                continue
            namespace = entry.get("namespace", default_namespace)
            consumer = f"{SECTIONS[section][1]} {namespace}/{name}"
            ref = _source_ref(entry["source"], sources, consumer, namespace)
            if ref["kind"] == "OCIRepository":
                oci_users.setdefault((ref["name"], ref["namespace"]), set()).add(section)
            link = {k: v for k, v in ref.items() if k != "namespace" or v != namespace}
            refs[section, name] = {"kind": ref["kind"], "name": ref["name"], "consumer": namespace, "ref": link}
    for (oci, namespace), users in oci_users.items():
        if len(users) > 1:
            raise ValueError(
                f"flux: OCIRepository {namespace}/{oci} is used by a HelmRelease and a Kustomization; "
                "the HelmRelease needs the chart layer, the Kustomization the manifests; define two OCIRepositories"
            )

    obj = BaseObj()
    for section, (_, _, suffix, _, _) in SECTIONS.items():
        for name, entry in entries[section].items():
            namespace = entry.get("namespace", default_namespace)
            resource = _resource(section, name, entry, namespace, refs.get((section, name)))
            # An OCIRepository a HelmRelease takes its chart from serves the chart layer as is.
            if section == "oci_repositories" and oci_users.get((name, namespace)) == {"helm_releases"}:
                resource["spec"].setdefault("layerSelector", dict(HELM_CHART_LAYER))
            obj.root[f"{namespace}/{name}-{suffix}"] = resource
    return obj
