"""Argo CD's release manifest and the Kapitan config management plugin (docs/specs/argocd.md, ACD-1 to ACD-8)."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re

from kapitan.inputs.kadet import BaseObj
from yaml import safe_load, safe_load_all

HERE = os.path.dirname(os.path.abspath(__file__))

# ACD-3: manifests/install.yaml is INSTALL_SOURCE (SHA-256 846c644bc81ce5557dd9048757a9c7353378f25c5eb811c77d32a9e907823599)
# from the line after its third "---" to the end; the three CRDs before it come from schemas/argoproj.io/crds.
INSTALL_VERSION = "3.5.6"
INSTALL_SOURCE = "https://raw.githubusercontent.com/argoproj/argo-cd/c2b1e3017e2cec86b122172e861dcd026453ae44/manifests/install.yaml"
INSTALL_SHA256 = "da75c759694b305f80d4e860fc5ea03fa8eefb1db12fc387d719bae52d9fa054"

# ACD-2, IMG-1: every image of the manifest, pinned by tag and digest.
INSTALL_IMAGES = {
    image.partition("@")[0]: image
    for image in (
        "quay.io/argoproj/argocd:v3.5.6@sha256:8e5cc5bb008df8a09dba439462e58c94c55b7735888d3ebde0c25fc05e4e5335",
        "ghcr.io/dexidp/dex:v2.45.1@sha256:8499afd690c437f52301efd2b05b2455da5bd2dfc20332cd697dc9937f808462",
        "public.ecr.aws/docker/library/redis:8.2.3-alpine@sha256:08ad0b1d280850169a790dba1393ff7a90aef951fc19632cf4d3ce4f78e679ba",
    )
}

# ACD-5: the Kapitan release the generator's manifest requires.
KAPITAN_IMAGE = "docker.io/kapicorp/kapitan:0.36.3@sha256:04b9ca04f5041851631fb1041fbafe37b1ca6c3ad99a81d6ccd40f5ebd20f857"

NAMESPACED = {"ConfigMap", "Deployment", "NetworkPolicy", "Role", "RoleBinding", "Secret", "Service", "ServiceAccount", "StatefulSet"}
CLUSTER_SCOPED = {"ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition"}

# ACD-4: the plugin of kadet-hub/examples argocd-cmp (EX-24).
PLUGIN_YAML = """\
apiVersion: argoproj.io/v1alpha1
kind: ConfigManagementPlugin
metadata:
  name: kapitan
spec:
  # Runs in the Application's path. Compiles the target that the
  # Application sets in its plugin env as TARGET, without --fetch: the
  # repository holds the verified generators and recipes. Prints every
  # YAML file of compiled/<target>, and fails rather than print nothing,
  # which would make an Application with prune delete everything.
  generate:
    command: [bash, -c]
    args:
      - |
        set -euo pipefail
        shopt -s globstar nullglob
        kapitan compile -t "$ARGOCD_ENV_TARGET" >&2
        files=(compiled/"$ARGOCD_ENV_TARGET"/**/*.yml compiled/"$ARGOCD_ENV_TARGET"/**/*.yaml)
        if ((${#files[@]} == 0)); then
          echo "no YAML files in compiled/$ARGOCD_ENV_TARGET" >&2
          exit 1
        fi
        for f in "${files[@]}"; do
          echo ---
          cat "$f"
        done
"""


def _mapping(value: object, where: str, allowed: set[str]) -> dict:
    """ACD-8: a mapping with known keys only."""
    if not isinstance(value, dict):
        raise ValueError(f"argocd: {where} must be a mapping ({{}} for the defaults), not {value!r}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"argocd: unknown keys under {where}: {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")
    return value


def _documents() -> list[dict]:
    """ACD-1, ACD-3: the documents of the pinned install.yaml, checked against the pins."""
    with open(os.path.join(HERE, "manifests", "install.yaml"), "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != INSTALL_SHA256:
        raise ValueError(f"argocd: manifests/install.yaml has SHA-256 {digest}, the pin is {INSTALL_SHA256}; vendor it again as docs/specs/argocd.md describes")
    with open(os.path.join(HERE, "schemas", "sources.yaml"), encoding="utf-8") as f:
        schemas = str(safe_load(f)["argoproj.io"]["version"])
    if schemas != INSTALL_VERSION:
        raise ValueError(f"argocd: the CRDs in schemas/ are Argo CD {schemas}, manifests/install.yaml is {INSTALL_VERSION}; vendor install.yaml of {schemas} as docs/specs/argocd.md describes")
    docs = [doc for doc in safe_load_all(data) if doc]
    for path in sorted(glob.glob(os.path.join(HERE, "schemas", "argoproj.io", "crds", "*"))):
        with open(path, encoding="utf-8") as f:
            docs.append(json.load(f) if path.endswith(".json") else safe_load(f))
    return docs


def _place(doc: dict, namespace: str) -> None:
    """ACD-2: the namespace as kustomize's namespace transformer sets it, and pinned images."""
    kind, name = doc["kind"], doc["metadata"]["name"]
    if kind in NAMESPACED:
        doc["metadata"]["namespace"] = namespace
    elif kind not in CLUSTER_SCOPED:
        raise ValueError(f"argocd: {kind} {name} of the Argo CD manifest is neither in NAMESPACED nor in CLUSTER_SCOPED")
    if kind == "ClusterRoleBinding":
        for subject in doc.get("subjects", []):
            if subject.get("kind") == "ServiceAccount" and subject.get("namespace") == "argocd":
                subject["namespace"] = namespace
    pod = (doc.get("spec") or {}).get("template", {}).get("spec", {})
    for container in pod.get("initContainers", []) + pod.get("containers", []):
        if container["image"] not in INSTALL_IMAGES:
            raise ValueError(f"argocd: image {container['image']} of {kind} {name} has no digest in INSTALL_IMAGES")
        container["image"] = INSTALL_IMAGES[container["image"]]


def _add_cmp(docs: list[dict], cmp: dict, namespace: str) -> None:
    """ACD-4 to ACD-7: the Kapitan sidecar in argocd-repo-server and its plugin.yaml."""
    image = KAPITAN_IMAGE if cmp.get("image") is None else cmp["image"]
    repository, at, digest = str(image).partition("@")
    if not (repository and at and re.fullmatch(r"\S+", repository) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        raise ValueError(f"argocd: install.cmp.image must be pinned by digest, <repository>[:<tag>]@sha256:<64 hex digits>, not {image!r}")
    deployment = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "argocd-repo-server")
    pod = deployment["spec"]["template"]["spec"]
    if pod.get("automountServiceAccountToken") is not False:
        raise ValueError("argocd: install.cmp needs the argocd-repo-server pod without a service account token (automountServiceAccountToken: false)")
    container = {
        "name": "kapitan",
        "image": image,
        "command": ["/var/run/argocd/argocd-cmp-server"],
        # Kapitan's dependencies print deprecation warnings that bury a compile error in Argo CD's UI.
        "env": [{"name": "PYTHONWARNINGS", "value": "ignore"}],
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 999,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "volumeMounts": [
            {"name": "var-files", "mountPath": "/var/run/argocd"},
            {"name": "plugins", "mountPath": "/home/argocd/cmp-server/plugins"},
            {"name": "kapitan-plugin", "mountPath": "/home/argocd/cmp-server/config/plugin.yaml", "subPath": "plugin.yaml"},
            {"name": "kapitan-tmp", "mountPath": "/tmp"},
        ],
    }
    if cmp.get("resources") is not None:
        container["resources"] = cmp["resources"]
    pod["containers"].append(container)
    pod["volumes"] += [{"name": "kapitan-plugin", "configMap": {"name": "kapitan-plugin"}}, {"name": "kapitan-tmp", "emptyDir": {}}]
    docs.append({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "kapitan-plugin", "namespace": namespace}, "data": {"plugin.yaml": PLUGIN_YAML}})


def render(config: object, namespace: str) -> dict[str, BaseObj]:
    """ACD-1: the documents of `generators.argocd.install`, keyed install/<name>-<kind>."""
    cmp = _mapping(config, "install", {"cmp"}).get("cmp")
    if cmp is not None:
        _mapping(cmp, "install.cmp", {"image", "resources"})
    docs = _documents()
    for doc in docs:
        _place(doc, namespace)
    if cmp is not None:
        _add_cmp(docs, cmp, namespace)
    return {f"install/{doc['metadata']['name']}-{doc['kind'].lower()}": BaseObj.from_dict(doc) for doc in docs}
