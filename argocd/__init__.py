from __future__ import annotations

import logging
from typing import Any


"""ArgoCD resource generators for Kapitan.

This module provides classes and functions for generating ArgoCD resources
using Kapitan's kadet input type. Supports Application, AppProject, and
ApplicationSet resources.

BACKEND COMPATIBILITY
─────────────────────
The generator must work with ALL valid Kapitan inventory backends:
  - reclass / reclass-rs  → plain Python dicts
  - omegaconf             → OmegaConf DictConfig / ListConfig

RULES for inventory access:
  1. Always use `.get("key", default)` — never direct attribute access.
     OmegaConf raises ConfigAttributeError on missing keys.
  2. Always call `_convert_to_dict()` on any nested value before passing
     it to a resource class or mutating it.
  3. Never assume `isinstance(obj, dict)` is enough — OmegaConf objects
     pass that check but behave differently.
"""

__version__ = "1.0.3"

from kapitan.inputs.kadet import BaseObj, inventory, topics

from . import k8s


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()


inv = inventory()

logger = logging.getLogger(__name__)


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj / OmegaConf objects to plain Python dicts.

    Kapitan inventory values arrive as OmegaConf DictConfig objects.
    This function converts them so they can be serialised to YAML without surprises.
    """
    if _OMEGACONF_TYPES and isinstance(obj, _OMEGACONF_TYPES):
        from omegaconf import OmegaConf

        return _convert_to_dict(OmegaConf.to_container(obj, resolve=True))
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "root"):
        return _convert_to_dict(obj.root)
    if isinstance(obj, dict):
        return {k: _convert_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_to_dict(item) for item in obj]
    return obj


def _merge_spec_passthrough(spec_target: Any, config: dict) -> None:
    """Merge user-provided `spec` dict into the resource spec verbatim."""
    override = config.get("spec")
    if override:
        spec_target.update(_convert_to_dict(override))


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when a flat abstraction key would overwrite a value from `spec`."""
    spec = _convert_to_dict(config.get("spec")) or {}
    if not spec:
        return
    flat = _convert_to_dict(config)
    for flat_key, crd_key in mapping.items():
        flat_value, spec_value = flat, spec
        for part in flat_key.split("."):
            flat_value = flat_value.get(part) if isinstance(flat_value, dict) else None
        for part in crd_key.split("."):
            spec_value = spec_value.get(part) if isinstance(spec_value, dict) else None
        if flat_value is not None and spec_value is not None:
            logger.warning(
                "Flat key '%s' overrides spec passthrough '%s' for resource '%s'",
                flat_key,
                crd_key,
                name,
            )


class ArgoCDAppProject(k8s.Base):
    """ArgoCD AppProject resource.

    Generates an AppProject for organizing and controlling access to Applications.

    Required kwargs:
        name: Resource name.
        config: AppProject configuration dictionary.
    """

    _FLAT_KEY_MAP = {
        "source_repos": "sourceRepos",
        "destinations": "destinations",
        "cluster_resource_whitelist": "clusterResourceWhitelist",
        "namespace_resource_blacklist": "namespaceResourceBlacklist",
        "namespace_resource_whitelist": "namespaceResourceWhitelist",
        "orphaned_resources": "orphanedResources",
        "roles": "roles",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "argoproj.io/v1alpha1"
        self.kwargs.kind = "AppProject"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self.add_namespace(
            config.get(
                "namespace",
                inv.parameters.get("generators", {})
                .get("argocd", {})
                .get("namespace", "argocd"),
            )
        )
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Optional opt-in finalizer (upstream does NOT auto-set this on
        # AppProjects; auto-adding it can leave projects undeletable).
        finalizers = config.get("finalizers")
        if finalizers:
            self.root.metadata.finalizers = list(finalizers)

        # 1. Passthrough — merge any unmodelled fields first.
        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # 2. Explicit abstractions — flat keys take precedence.
        if config.get("source_repos"):
            self.root.spec.sourceRepos = config.get("source_repos")
        if config.get("destinations"):
            self.root.spec.destinations = config.get("destinations")
        if config.get("cluster_resource_whitelist"):
            self.root.spec.clusterResourceWhitelist = config.get(
                "cluster_resource_whitelist"
            )
        if config.get("namespace_resource_blacklist"):
            self.root.spec.namespaceResourceBlacklist = config.get(
                "namespace_resource_blacklist"
            )
        if config.get("namespace_resource_whitelist"):
            self.root.spec.namespaceResourceWhitelist = config.get(
                "namespace_resource_whitelist"
            )
        if config.get("orphaned_resources"):
            self.root.spec.orphanedResources = config.get("orphaned_resources")
        if config.get("roles"):
            self.root.spec.roles = config.get("roles")


class ArgoCDApplicationSet(k8s.Base):
    """ArgoCD ApplicationSet resource.

    Generates an ApplicationSet that templates multiple Applications using
    generator strategies (cluster, git, list, matrix, merge, etc.).

    Required kwargs:
        name: Resource name.
        config: ApplicationSet configuration dictionary.
    """

    _FLAT_KEY_MAP = {
        "generators": "generators",
        "template": "template",
        "template_patch": "templatePatch",
        "sync_policy": "syncPolicy",
        "go_template": "goTemplate",
        "go_template_options": "goTemplateOptions",
        "ignore_application_differences": "ignoreApplicationDifferences",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "argoproj.io/v1alpha1"
        self.kwargs.kind = "ApplicationSet"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self.add_namespace(
            config.get(
                "namespace",
                inv.parameters.get("generators", {})
                .get("argocd", {})
                .get("namespace", "argocd"),
            )
        )
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        if config.get("generators"):
            self.root.spec.generators = config.get("generators")
        if config.get("template"):
            self.root.spec.template = config.get("template")
        if config.get("template_patch"):
            self.root.spec.templatePatch = config.get("template_patch")
        if config.get("sync_policy"):
            self.root.spec.syncPolicy = config.get("sync_policy")
        if config.get("go_template") is not None:
            self.root.spec.goTemplate = config.get("go_template")
        if config.get("go_template_options"):
            self.root.spec.goTemplateOptions = config.get("go_template_options")
        if config.get("ignore_application_differences"):
            self.root.spec.ignoreApplicationDifferences = config.get(
                "ignore_application_differences"
            )


class ArgoCDApplication(k8s.Base):
    """ArgoCD Application resource.

    Generates an Application that defines a source repository and destination cluster.

    Required kwargs:
        name: Resource name.
        config: Application configuration dictionary.
    """

    _FLAT_KEY_MAP = {
        "project": "project",
        "destination": "destination",
        "source": "source",
        "sources": "sources",
        "sync_policy": "syncPolicy",
        "ignore_differences": "ignoreDifferences",
        "revision_history_limit": "revisionHistoryLimit",
    }

    def new(self) -> None:
        self.need("config")
        self.kwargs.apiVersion = "argoproj.io/v1alpha1"
        self.kwargs.kind = "Application"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self.add_namespace(
            config.get(
                "namespace",
                inv.parameters.get("generators", {})
                .get("argocd", {})
                .get("namespace", "argocd"),
            )
        )
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Opt-in cascade-delete finalizer (documented upstream behaviour).
        if config.get("cascade_delete", False):
            self.root.metadata.finalizers = ["resources-finalizer.argocd.argoproj.io"]

        _merge_spec_passthrough(self.root.spec, config)
        _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

        # No project default: the shipped "default" AppProject allows every
        # repo, cluster and kind, so the CRD's required project stays unset.
        if config.get("project") is not None:
            self.root.spec.project = config.get("project")

        destination = config.get("destination")
        if isinstance(destination, str):
            destination = {"namespace": destination}
        if destination:
            self.root.spec.destination = destination
        # Argo CD rejects a destination without server or name.
        dest = self.root.spec.get("destination")
        if dest is not None and "server" not in dest and "name" not in dest:
            dest["server"] = "https://kubernetes.default.svc"
        if config.get("source"):
            self.root.spec.source = config.get("source")
        if config.get("sources"):
            self.root.spec.sources = config.get("sources")
        if config.get("sync_policy"):
            self.root.spec.syncPolicy = config.get("sync_policy")
        if config.get("ignore_differences"):
            self.root.spec.ignoreDifferences = config.get("ignore_differences")
        if config.get("revision_history_limit") is not None:
            self.root.spec.revisionHistoryLimit = config.get("revision_history_limit")


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base: dicts merge recursively, other values replace."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def main(input_params: dict | None = None) -> BaseObj:
    """Main entry point for the ArgoCD generator.

    Generates ArgoCD resources from inventory parameters.

    Expected inventory structure:
        parameters:
          generators:
            argocd:
              namespace: argocd
              applications:
                my-app:
                  project: my-project
                  destination: my-namespace
                  source:
                    repoURL: https://git.example.com/platform/my-app.git
                    path: manifests
                    targetRevision: HEAD
              projects:
                my-project:
                  source_repos:
                    - https://git.example.com/platform/my-app.git
                  destinations:
                    - namespace: my-namespace
                      server: https://kubernetes.default.svc

    Args:
        input_params: Input parameters from Kapitan compile configuration.

    Returns:
        BaseObj containing all generated ArgoCD resources.
    """
    obj = BaseObj()

    argocd_config = inv.parameters.get("generators", {}).get("argocd", {}) or {}
    argocd_config = _convert_to_dict(argocd_config)
    default_namespace = argocd_config.get("namespace", "argocd")

    # Generate Applications
    for name, config in argocd_config.get("applications", {}).items():
        app_name = config.get("name", name)
        app = ArgoCDApplication(name=app_name, config=config)
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{app_name}-application"] = app

    # One Application per target publishing kapitan.topics.<topic>.parameters,
    # merged over the topic's defaults. Kapitan requires the compiling target
    # to declare kapitan.topics.<topic>.consume: true.
    for topic, defaults in argocd_config.get("topics", {}).items():
        targets = _convert_to_dict(topics(topic).parameters.targets)
        for target in sorted(targets):
            config = _deep_merge(defaults or {}, targets[target] or {})
            app_name = config.get("name", target)
            namespace = config.get("namespace", default_namespace)
            key = f"{namespace}/{app_name}-application"
            if key in obj.root:
                raise ValueError(
                    f"argocd: Application {key} is defined twice (topic {topic})"
                )
            obj.root[key] = ArgoCDApplication(name=app_name, config=config)

    # Generate AppProjects
    for name, config in argocd_config.get("projects", {}).items():
        project_name = config.get("name", name)
        project = ArgoCDAppProject(name=project_name, config=config)
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{project_name}-appproject"] = project

    # Generate ApplicationSets
    for name, config in argocd_config.get("application_sets", {}).items():
        appset_name = config.get("name", name)
        appset = ArgoCDApplicationSet(name=appset_name, config=config)
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{appset_name}-appset"] = appset

    return obj


__all__ = [
    "ArgoCDAppProject",
    "ArgoCDApplication",
    "ArgoCDApplicationSet",
    "inv",
    "k8s",
    "main",
]
