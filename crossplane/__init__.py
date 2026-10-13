"""Crossplane v2 resource generator for Kapitan.

Renders Provider and Function packages, CompositeResourceDefinitions,
Compositions and ProviderConfigs from parameters.generators.crossplane;
see README.md for the inventory contract.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

PKG = "pkg.crossplane.io/v1"
COMPOSITION = "apiextensions.crossplane.io/v1"
XRD = "apiextensions.crossplane.io/v2"
# spec.package CEL rule of the Provider and Function CRDs at v2.4.2
PACKAGE = re.compile(r"[^./]+(\.[^./]+)+(/[^/:@]+)+(:[^:@]+(@sha256.+)?|@sha256.+)")

try:
    from omegaconf import DictConfig, ListConfig, OmegaConf
except ImportError:
    DictConfig = ListConfig = OmegaConf = None


def _plain(obj: Any) -> Any:
    """Inventory values (reclass dicts or OmegaConf containers) as plain dicts and lists."""
    if OmegaConf is not None and isinstance(obj, (DictConfig, ListConfig)):
        return OmegaConf.to_container(obj, resolve=True)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


def _get(tree: dict, path: str) -> Any:
    for part in path.split("."):
        tree = tree.get(part) if isinstance(tree, dict) else None
    return tree


def _merge(target: dict, override: dict) -> dict:
    """Deep-merge override into target; lists and scalars replace."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


def _spec(name: str, config: dict, defaults: dict, flat: dict) -> dict:
    """Generator defaults < config.spec < flat keys and shorthands (flat: {inventory key: (CRD path, value)})."""
    spec = _merge(defaults, copy.deepcopy(config.get("spec") or {}))
    for key, (path, value) in flat.items():
        if value is None:
            continue
        if _get(config.get("spec") or {}, path) is not None:
            logger.warning("Flat key '%s' overrides spec passthrough '%s' for resource '%s'", key, path, name)
        *parents, leaf = path.split(".")
        node = spec
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return spec


def _resource(api_version: str, kind: str, name: str, config: dict, spec: dict, namespace: str | None = None) -> dict:
    metadata = {"name": name}
    if namespace:
        metadata["namespace"] = namespace
    for key in ("labels", "annotations"):
        if config.get(key):
            metadata[key] = config[key]
    return {"apiVersion": api_version, "kind": kind, "metadata": metadata, "spec": spec}


def _ref(value: Any) -> Any:
    """A bare string names the referenced object: x -> {name: x}."""
    return {"name": value} if isinstance(value, str) else value


def _package(name: str, config: dict) -> dict:
    """Provider or Function spec; spec.package must be fully qualified and pinned (Crossplane v2 has no default registry)."""
    package = config.get("package")
    if package is not None and config.get("version"):
        package = f"{package}:{config['version']}"
    if package is not None and config.get("digest"):
        package = f"{package}@{config['digest']}"
    spec = _spec(name, config, {}, {
        "package": ("package", package),
        "package_pull_policy": ("packagePullPolicy", config.get("package_pull_policy")),
        "package_pull_secrets": ("packagePullSecrets", config.get("package_pull_secrets")),
        "revision_activation_policy": ("revisionActivationPolicy", config.get("revision_activation_policy")),
        "revision_history_limit": ("revisionHistoryLimit", config.get("revision_history_limit")),
        "runtime_config": ("runtimeConfigRef", _ref(config.get("runtime_config"))),
        "skip_dependency_resolution": ("skipDependencyResolution", config.get("skip_dependency_resolution")),
        "ignore_crossplane_constraints": ("ignoreCrossplaneConstraints", config.get("ignore_crossplane_constraints")),
        "common_labels": ("commonLabels", config.get("common_labels")),
        "common_annotations": ("commonAnnotations", config.get("common_annotations")),
    })
    ref = str(spec.get("package") or "")
    m = PACKAGE.fullmatch(ref)
    if not m or m[3] == ":latest":
        raise ValueError(
            f"package '{name}': '{ref}' is not a fully qualified package pinned by a tag other than latest "
            "or a sha256 digest (registry.example.com/repo/package[:tag]@sha256:<hex>)"
        )
    return spec


def _xrd(name: str, config: dict) -> dict:
    """CompositeResourceDefinition v2; the key is <plural>.<group>, which Crossplane requires as its name."""
    plural, dot, group = name.partition(".")
    if not dot:
        raise ValueError(f"composite resource definition '{name}': the key must be <plural>.<group>")
    versions = config.get("versions")
    if config.get("version") is not None and versions is not None:
        raise ValueError(f"composite resource definition '{name}': set version or versions, not both")
    if config.get("version") is not None:
        version = {"name": config["version"], "referenceable": True, "served": True}
        schema = {"type": "object", "properties": {}}
        for key in ("spec", "status"):
            if config.get(f"{key}_schema") is not None:
                schema["properties"][key] = config[f"{key}_schema"]
        if schema["properties"]:
            version["schema"] = {"openAPIV3Schema": schema}
        versions = [version]
    return _spec(name, config, {"group": group, "names": {"plural": plural}}, {
        "kind": ("names.kind", config.get("kind")),
        ("version" if config.get("version") is not None else "versions"): ("versions", versions),
        "scope": ("scope", config.get("scope")),
        "default_composition": ("defaultCompositionRef", _ref(config.get("default_composition"))),
        "enforced_composition": ("enforcedCompositionRef", _ref(config.get("enforced_composition"))),
        "default_composition_update_policy": ("defaultCompositionUpdatePolicy", config.get("default_composition_update_policy")),
    })


def _composition(name: str, config: dict, xrds: dict) -> dict:
    """Composition in Pipeline mode (the CRD default); compositeTypeRef derives from the XRD's referenceable version."""
    type_ref = config.get("composite_type_ref")
    if config.get("xrd") is not None:
        xrd = xrds.get(config["xrd"])
        if xrd is None:
            raise ValueError(f"composition '{name}': no composite resource definition '{config['xrd']}'")
        version = next((v["name"] for v in xrd.get("versions", []) if v.get("referenceable")), None)
        if version is None:
            raise ValueError(f"composition '{name}': '{config['xrd']}' has no referenceable version")
        type_ref = {"apiVersion": f"{xrd['group']}/{version}", "kind": _get(xrd, "names.kind")}
    pipeline = None
    if config.get("pipeline") is not None:
        pipeline = []
        for step in config["pipeline"]:
            step = dict(step)
            function = step.pop("function", None)
            if function is not None:
                step = {"step": function, "functionRef": {"name": function}, **step}
            pipeline.append(step)
    spec = _spec(name, config, {}, {
        ("xrd" if config.get("xrd") is not None else "composite_type_ref"): ("compositeTypeRef", type_ref),
        "pipeline": ("pipeline", pipeline),
    })
    steps = [step.get("step") for step in spec.get("pipeline") or []]
    if not steps:
        raise ValueError(f"composition '{name}': the pipeline needs at least one step")
    if len(set(steps)) != len(steps):
        raise ValueError(f"composition '{name}': step names must be unique, got {steps}; set step for a function used twice")
    return spec


def _provider_config(name: str, config: dict, namespace: str | None) -> dict:
    """credentials_secret {name, key[, namespace]} -> credentials {source: Secret, secretRef}."""
    secret = config.get("credentials_secret")
    credentials = None
    if secret is not None:
        if namespace and secret.get("namespace") not in (None, namespace):
            raise ValueError(
                f"provider config '{name}': a namespaced ProviderConfig reads its Secret from the namespace of the "
                f"managed resource ({namespace}); drop credentials_secret.namespace or use a ClusterProviderConfig"
            )
        ref = {"namespace": secret.get("namespace") or namespace, "name": secret.get("name"), "key": secret.get("key")}
        if not all(ref.values()):
            raise ValueError(f"provider config '{name}': credentials_secret needs name, key and, for a ClusterProviderConfig, namespace")
        credentials = {"source": "Secret", "secretRef": ref}
    return _spec(name, config, {}, {"credentials_secret": ("credentials", credentials)})


def main(input_params: dict | None = None) -> BaseObj:
    """Kapitan kadet entry point. Reads parameters.generators.crossplane."""
    params = inventory().parameters
    config = _plain(params.get("generators", {}).get("crossplane", {}) or {})
    default_namespace = str(config.get("namespace") or params.get("namespace", "default"))
    obj = BaseObj()

    for section, kind in (("providers", "Provider"), ("functions", "Function")):
        for name, entry in (config.get(section) or {}).items():
            entry = entry or {}
            obj.root[f"{name}-{kind.lower()}"] = _resource(PKG, kind, name, entry, _package(name, entry))

    xrds = {}
    for name, entry in (config.get("composite_resource_definitions") or {}).items():
        entry = entry or {}
        xrds[name] = _xrd(name, entry)
        obj.root[f"{name}-xrd"] = _resource(XRD, "CompositeResourceDefinition", name, entry, xrds[name])

    for name, entry in (config.get("compositions") or {}).items():
        entry = entry or {}
        obj.root[f"{name}-composition"] = _resource(COMPOSITION, "Composition", name, entry, _composition(name, entry, xrds))

    for name, entry in (config.get("provider_configs") or {}).items():
        entry = entry or {}
        if not entry.get("api_version"):
            raise ValueError(f"provider config '{name}': api_version is required, for example aws.m.upbound.io/v1beta1")
        kind = entry.get("kind") or "ProviderConfig"
        namespace = None if kind == "ClusterProviderConfig" else str(entry.get("namespace") or default_namespace)
        key = f"{name}-{kind.lower()}" if namespace is None else f"{namespace}/{name}-{kind.lower()}"
        obj.root[key] = _resource(entry["api_version"], kind, name, entry, _provider_config(name, entry, namespace), namespace)
    return obj
