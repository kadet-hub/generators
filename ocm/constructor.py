"""Builds the OCM component constructor, without Kapitan (docs/specs/ocm.md)."""

import copy
import json
import os
import re
from pathlib import Path

import yaml

PARAM_KEYS = {"components", "file"}
IMAGE_KEYS = {"scan", "refs", "access", "label", "require_digest", "names"}
REQUIRED = ("name", "version", "provider")


class OcmError(ValueError):
    pass


class Loader(yaml.SafeLoader):
    pass


# A plain "=" is the YAML 1.1 value key, which the safe loader cannot construct.
Loader.add_constructor("tag:yaml.org,2002:value", Loader.construct_yaml_str)


def load(text):
    loader = Loader(text)
    try:
        docs = []
        while loader.check_data():
            docs.append(loader.get_data())
        return docs
    finally:
        loader.dispose()


def plain(value):
    """Inventory Boxes and OmegaConf containers to plain data."""
    return json.loads(json.dumps(value))


def parse_ref(ref):
    """{registry, path, repository, name, tag, digest} of an image reference."""
    rest, _, digest = ref.partition("@")
    first, sep, remainder = rest.partition("/")
    if sep and ("." in first or ":" in first or first == "localhost"):
        registry, path = first.lower(), remainder
    else:
        registry, path = "docker.io", rest if sep else f"library/{rest}"
    repo, tag = path, ""
    last = path.rsplit("/", 1)[-1]
    if ":" in last:
        repo, tag = path.rsplit(":", 1)
    full = path + (f"@{digest}" if digest else "")
    return {
        "registry": registry,
        "path": full,
        "repository": f"{registry}/{repo}",
        "name": repo.rsplit("/", 1)[-1],
        "tag": tag,
        "digest": digest,
    }


def images_in(node):
    if isinstance(node, dict):
        if isinstance(node.get("image"), str):
            yield node["image"]
        for value in node.values():
            yield from images_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from images_in(value)


def scan(root, patterns):
    """Image references of every YAML file the patterns match below root."""
    base = Path(os.path.realpath(root))
    found = set()
    for pattern in patterns:
        matches = sorted(p for p in base.glob(pattern) if p.is_file())
        if not matches:
            raise OcmError(f"ocm: images.scan {pattern!r} matches no file")
        for path in matches:
            if not Path(os.path.realpath(path)).is_relative_to(base):
                raise OcmError(f"ocm: images.scan {pattern!r} matches {path} outside the compile root")
            rel = os.path.relpath(path, base)
            try:
                docs = load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                raise OcmError(f"ocm: {rel}: not YAML: {e}") from e
            for doc in docs:
                found.update(images_in(doc))
    return found


def image_resources(cid, images, root):
    unknown = set(images) - IMAGE_KEYS
    if unknown:
        raise OcmError(f"ocm: component {cid}: unknown images keys {sorted(unknown)}")
    refs = set(images.get("refs") or [])
    if images.get("scan"):
        refs |= scan(root, images["scan"])
    template = images.get("access") or "%ref%"
    names = dict(images.get("names") or {})
    used = set()
    resources = []
    # One image per parsed reference; a tag-only one folds into a pinned one of the same tag.
    unique = {}
    for ref in sorted(refs):
        p = parse_ref(ref)
        unique.setdefault((p["registry"], p["path"]), (ref, p))
    pinned = {(p["repository"], p["tag"]) for _, p in unique.values() if p["digest"]}
    for ref, p in sorted(unique.values(), key=lambda item: item[0]):
        if not p["digest"] and (p["repository"], p["tag"]) in pinned:
            continue
        if p["digest"] and not p["tag"]:
            raise OcmError(f"ocm: component {cid}: image {ref} has a digest but no tag to use as version")
        if images.get("require_digest") and not p["digest"]:
            raise OcmError(f"ocm: component {cid}: image {ref} has no digest")
        name = names.get(p["repository"], p["name"])
        used.add(p["repository"])
        access = template
        for token, value in (
            ("%ref%", ref),
            ("%registry_id%", re.sub(r"[^A-Za-z0-9]", "_", p["registry"])),
            ("%registry%", p["registry"]),
            ("%path%", p["path"]),
        ):
            access = access.replace(token, value)
        resource = {"name": name, "type": "ociImage", "version": p["tag"] or "latest"}
        if images.get("label"):
            resource["labels"] = [{"name": images["label"], "value": ref}]
        resource["access"] = {"type": "ociArtifact", "imageReference": access}
        resources.append((ref, resource))
    dead = set(names) - used
    if dead:
        raise OcmError(f"ocm: component {cid}: images.names {sorted(dead)} match no image")
    return resources


def component(cid, spec, root):
    spec = plain(spec or {})
    missing = [k for k in REQUIRED if k not in spec]
    if missing:
        raise OcmError(f"ocm: component {cid}: missing {missing}")
    images = spec.pop("images", None) or {}
    resources = spec.pop("resources", None) or {}
    out = copy.deepcopy(spec)
    listed, seen = [], {}
    for key, resource in resources.items():
        resource = {"name": key, **(resource or {})}
        listed.append(resource)
        seen.setdefault(resource["name"], []).append(f"resources.{key}")
    for ref, resource in image_resources(cid, images, root):
        listed.append(resource)
        seen.setdefault(resource["name"], []).append(ref)
    clashes = {n: s for n, s in seen.items() if len(s) > 1}
    if clashes:
        detail = "; ".join(f"{n}: {', '.join(s)}" for n, s in sorted(clashes.items()))
        raise OcmError(f"ocm: component {cid}: resource names used twice ({detail}); set images.names")
    out["resources"] = listed
    return out


def build(params, root):
    """{file: text} of the constructor for input_params without compile_path."""
    params = plain(params)
    unknown = set(params) - PARAM_KEYS
    if unknown:
        raise OcmError(f"ocm: unknown input_params {sorted(unknown)}")
    components = params.get("components") or {}
    if not components:
        raise OcmError("ocm: input_params.components is empty")
    constructor = {"components": [component(cid, components[cid], root) for cid in sorted(components)]}
    text = yaml.safe_dump(constructor, sort_keys=False, default_flow_style=False)
    return {params.get("file") or "component-constructor.yaml": text}
