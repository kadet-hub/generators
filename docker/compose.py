"""Docker Compose file from the components of the kubernetes generator (docs/specs/docker.md)."""

import copy
import re
from decimal import Decimal

import yaml

# DKR-3: application and enabled are read by _components, service and
# enable_service_links have no effect inside the container.
KEYS = {
    "image", "command", "args", "env", "secrets", "config_maps", "ports", "volume_mounts",
    "volume_claims", "healthcheck", "resources", "security_context", "read_only_root_filesystem",
    "type", "application", "enabled", "service", "enable_service_links",
}
SOURCES = {"secretKeyRef": ("secrets", "string_data"), "configMapKeyRef": ("config_maps", "data")}
CONTEXT = {"runAsUser", "runAsGroup", "readOnlyRootFilesystem"}
MOUNT = {"mount_path", "volume", "read_only"}
PROBE = {"type", "command", "initial_delay_seconds", "period_seconds", "timeout_seconds", "failure_threshold"}
CPU = re.compile(r"(\d+(?:\.\d+)?)(m?)")
MEMORY = re.compile(r"(\d+)(Ki|Mi|Gi)")
UNITS = {"Ki": "k", "Mi": "m", "Gi": "g"}


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True  # no anchors, even for objects the inventory shares


def _fail(name, what):
    raise ValueError(f"components.{name}: no Compose mapping for {what}")


def _text(value):
    """A literal for Compose, which interpolates $ (DKR-4)."""
    return str(value).replace("$", "$$")


def _expanded(name, what, value):
    """A value Kubernetes expands $( and $$ in (DKR-4)."""
    text = str(value)
    if "$(" in text or "$$" in text:
        raise ValueError(
            f"components.{name}: {what}: Kubernetes expands $( and $$ here and Compose does not"
        )
    return _text(text)


def _strings(name, what, value):
    if not isinstance(value, list):
        raise ValueError(f"components.{name}: {what} must be a list")
    return [_expanded(name, what, v) for v in value]


def _fill(source, destination):
    """The kubernetes generator's merge: fill keys destination leaves unset or null (DKR-2)."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _fill(value, destination[key])
        elif destination.get(key) is None:
            destination[key] = copy.deepcopy(value)
    return destination


def _components(parameters):
    manifest = parameters.get("generators", {}).get("manifest", {})
    for name, component in parameters.get("components", {}).items():
        if not component.get("enabled", True):
            continue
        component = copy.deepcopy(component)
        if "application" in component:
            application = parameters.get("applications", {}).get(component["application"], {})
            _fill(application.get("component_defaults", {}), component)
        _fill(manifest.get("default_config", {}), component)
        component["type"] = component.get("type") or "deployment"
        _fill(manifest.get("resource_defaults", {}).get(component["type"], {}), component)
        yield name, component


def _env(name, component):
    for section, field in SOURCES.values():
        for entry_name, entry in (component.get(section) or {}).items():
            extra = sorted(set(entry or {}) - {field})
            if extra:
                _fail(name, ", ".join(f"{section}.{entry_name}.{k}" for k in extra))
            for key, item in ((entry or {}).get(field) or {}).items():
                if not isinstance(item, dict) or set(item) != {"value"}:
                    _fail(name, f"{section}.{entry_name}.{field}.{key} other than value")
    env = {}
    for var, value in (component.get("env") or {}).items():
        if not isinstance(value, dict):
            env[var] = _expanded(name, f"env.{var}", value)
            continue
        kind = next(iter(value), None)
        if len(value) != 1 or kind not in SOURCES or set(value[kind] or {}) != {"key"}:
            _fail(name, f"env.{var}")
        section, field = SOURCES[kind]
        key = value[kind]["key"]
        found = [e[field][key] for e in (component.get(section) or {}).values() if key in ((e or {}).get(field) or {})]
        if not found:
            raise ValueError(f"components.{name}: env.{var}: no {section} entry has {field}.{key}")
        # Secret and ConfigMap data reach the container unexpanded.
        env[var] = _text(found[0]["value"])
    return env


def _healthcheck(name, probes):
    out = None
    for kind, probe in probes.items():
        if not (probe or {}).get("type"):
            continue
        if kind != "readiness":
            _fail(name, f"healthcheck.{kind}: Docker runs one health check, the readiness probe")
        if probe["type"] != "command":
            _fail(
                name,
                f"healthcheck.readiness type {probe['type']}: a Compose health check runs a command "
                f"in the container; set it in generators.docker.compose.services.{name}.healthcheck",
            )
        extra = sorted(set(probe) - PROBE)
        if extra or not isinstance(probe.get("command"), list):
            _fail(name, ", ".join(f"healthcheck.readiness.{k}" for k in extra) or "healthcheck.readiness.command other than a list")
        # The kubernetes generator's defaults; probes are not expanded by Kubernetes.
        out = {
            "test": ["CMD", *(_text(a) for a in probe["command"])],
            "interval": f"{probe.get('period_seconds', 10)}s",
            "timeout": f"{probe.get('timeout_seconds', 5)}s",
            "retries": probe.get("failure_threshold", 3),
        }
        if probe.get("initial_delay_seconds"):
            out["start_period"] = f"{probe['initial_delay_seconds']}s"
    return out


def _resources(name, resources):
    extra = sorted(set(resources) - {"limits", "requests"})
    if extra:
        _fail(name, ", ".join(f"resources.{k}" for k in extra))
    out = {}
    for section, target in (("limits", "limits"), ("requests", "reservations")):
        for resource, quantity in (resources.get(section) or {}).items():
            cpu, memory = CPU.fullmatch(str(quantity)), MEMORY.fullmatch(str(quantity))
            if resource == "cpu" and cpu:
                cores = Decimal(cpu[1]) / (1000 if cpu[2] else 1)
                out.setdefault(target, {})["cpus"] = format(cores, "f")
            elif resource == "memory" and memory:
                out.setdefault(target, {})["memory"] = memory[1] + UNITS[memory[2]]
            else:
                _fail(name, f"resources.{section}.{resource} {quantity}")
    return out


def _service(name, component):
    extra = sorted(set(component) - KEYS)
    if extra:
        _fail(name, ", ".join(extra))
    if component["type"] not in ("deployment", "statefulset"):
        _fail(name, f"type {component['type']}")
    if component.get("enable_service_links") not in (None, False):
        _fail(name, "enable_service_links other than false")
    if not component.get("image"):
        raise ValueError(f"components.{name}: image is required")
    out = {"image": _text(component["image"])}

    context = component.get("security_context") or {}
    extra = sorted(set(context) - CONTEXT)
    if extra:
        _fail(name, ", ".join(f"security_context.{k}" for k in extra))
    if context.get("runAsUser") is not None:
        out["user"] = ":".join(str(context[k]) for k in ("runAsUser", "runAsGroup") if context.get(k) is not None)
    elif context.get("runAsGroup") is not None:
        _fail(name, "security_context.runAsGroup without runAsUser")
    read_only = context.get("readOnlyRootFilesystem")
    if read_only is True or (read_only is None and component.get("read_only_root_filesystem") is True):
        out["read_only"] = True

    if component.get("command"):
        out["entrypoint"] = _strings(name, "command", component["command"])
    args = component.get("args")
    if isinstance(args, dict):  # K8S-4 of the kubernetes generator
        listed = []
        for key, value in args.items():
            if isinstance(value, dict):
                raise ValueError(f"components.{name}: args.{key} must be a string or a list, not a mapping")
            if value is not None:
                listed += value if isinstance(value, list) else [value]
        args = listed
    if args:
        out["command"] = _strings(name, "args", args)

    env = _env(name, component)
    if env:
        out["environment"] = env
    expose = []
    for _, port in sorted((component.get("ports") or {}).items()):
        number = port.get("container_port", port.get("service_port"))
        protocol = port.get("protocol", "TCP")
        expose.append(str(number) if protocol == "TCP" else f"{number}/{protocol.lower()}")
    if expose:
        out["expose"] = expose

    claims = component.get("volume_claims") or {}
    volumes = []
    for key, mount in (component.get("volume_mounts") or {}).items():
        extra = sorted(set(mount) - MOUNT)
        if extra:
            _fail(name, ", ".join(f"volume_mounts.{key}.{k}" for k in extra))
        volume = mount.get("volume") or key
        if volume not in claims:
            _fail(name, f"volume_mounts.{key}: volume {volume} is no volume_claims entry")
        volumes.append(f"{volume}:{_text(mount['mount_path'])}" + (":ro" if mount.get("read_only") else ""))
    if volumes:
        out["volumes"] = volumes

    healthcheck = _healthcheck(name, component.get("healthcheck") or {})
    if healthcheck:
        out["healthcheck"] = healthcheck
    resources = _resources(name, component.get("resources") or {})
    if resources:
        out["deploy"] = {"resources": resources}
    out["restart"] = "always"
    return out


def _merge(base, over):
    """DKR-9: mappings key by key, other values replace, null removes."""
    for key, value in over.items():
        if value is None:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


def render(parameters):
    """compose.yml for parameters with components, applications and generators as plain dicts."""
    services, claims = {}, {}
    for name, component in _components(parameters):
        services[name] = _service(name, component)
        for claim in component.get("volume_claims") or {}:
            if claim in claims:
                raise ValueError(
                    f"components.{name}: volume_claims.{claim}: components.{claims[claim]} has a claim "
                    "of that name, and Compose would give both the same volume"
                )
            claims[claim] = name
    document = {"services": services}
    if claims:
        document["volumes"] = {claim: {} for claim in claims}
    _merge(document, parameters["generators"]["docker"]["compose"])
    return yaml.dump(document, Dumper=_Dumper, sort_keys=False, default_flow_style=False)
