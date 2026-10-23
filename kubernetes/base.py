"""Base classes for Kubernetes workloads and shared configuration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, cast

from kapitan.inputs.kadet import BaseObj

from .utils import _convert_to_dict, get_namespace, inv, j2, merge


logger = logging.getLogger(__name__)

# =============================================================================
# Validation Constants (from Kubernetes API)
# =============================================================================

VALID_IMAGE_PULL_POLICIES = {"Always", "IfNotPresent", "Never"}
VALID_RESTART_POLICIES = {"Always", "OnFailure", "Never"}
VALID_SERVICE_TYPES = {"ClusterIP", "NodePort", "LoadBalancer", "ExternalName"}
VALID_DNS_POLICIES = {"ClusterFirst", "Default", "ClusterFirstWithHostNet", "None"}
VALID_PROTOCOL_TYPES = {"TCP", "UDP", "SCTP"}
VALID_SECURITY_PROFILES = {"baseline", "restricted"}

# Pod Security Standards allowed values:
# https://kubernetes.io/docs/concepts/security/pod-security-standards/
PSS_BASELINE_CAPABILITIES = {
    "AUDIT_WRITE",
    "CHOWN",
    "DAC_OVERRIDE",
    "FOWNER",
    "FSETID",
    "KILL",
    "MKNOD",
    "NET_BIND_SERVICE",
    "SETFCAP",
    "SETGID",
    "SETPCAP",
    "SETUID",
    "SYS_CHROOT",
}
PSS_SAFE_SYSCTLS = {
    "kernel.shm_rmid_forced",
    "net.ipv4.ip_local_port_range",
    "net.ipv4.ip_unprivileged_port_start",
    "net.ipv4.tcp_syncookies",
    "net.ipv4.ping_group_range",
    "net.ipv4.ip_local_reserved_ports",
    "net.ipv4.tcp_keepalive_time",
    "net.ipv4.tcp_fin_timeout",
    "net.ipv4.tcp_keepalive_intvl",
    "net.ipv4.tcp_keepalive_probes",
}
PSS_SELINUX_TYPES = {
    None,
    "",
    "container_t",
    "container_init_t",
    "container_kvm_t",
    "container_engine_t",
}
PSS_RESTRICTED_VOLUME_TYPES = {
    "configMap",
    "csi",
    "downwardAPI",
    "emptyDir",
    "ephemeral",
    "persistentVolumeClaim",
    "projected",
    "secret",
}
PSS_SECCOMP_TYPES = {"RuntimeDefault", "Localhost"}


# =============================================================================
# Helper Functions
# =============================================================================


def _set_if_truthy(target: Any, attr: str, value: Any) -> None:
    """Set an attribute on target only if value is truthy.

    Args:
        target: Object to set attribute on
        attr: Attribute name to set
        value: Value to set (only if truthy)
    """
    if value:
        setattr(target, attr, value)


def _validate_enum(value: str, valid_values: set[str], field_name: str) -> str:
    """Validate a value is in the set of valid values.

    Args:
        value: The value to validate
        valid_values: Set of valid string values
        field_name: Name of the field for error messages

    Returns:
        The validated value

    Raises:
        ValueError: If value is not in valid_values
    """
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            f"Must be one of: {', '.join(sorted(valid_values))}"
        )
    return value


def _fill(target: dict, key: str, value: Any) -> None:
    """Set target[key] unless the user set it (None and {} count as unset)."""
    if target.get(key) in (None, {}):
        target[key] = value


def _apply_security_profile(pod_spec: Any, component: Any) -> None:
    """Fill security_profile restricted and read_only_root_filesystem fields."""
    restricted = component.get("security_profile") == "restricted"
    read_only = component.get("read_only_root_filesystem") is True
    if restricted:
        pod_context = _convert_to_dict(pod_spec.get("securityContext")) or {}
        _fill(pod_context, "runAsNonRoot", True)
        _fill(pod_context, "seccompProfile", {"type": "RuntimeDefault"})
        pod_spec.securityContext = pod_context
    if not (restricted or read_only):
        return
    for container in pod_spec.containers + pod_spec.initContainers:
        context = _convert_to_dict(container.get("securityContext")) or {}
        if restricted:
            _fill(context, "allowPrivilegeEscalation", False)
            _fill(context, "capabilities", {})
            _fill(context["capabilities"], "drop", ["ALL"])
        if read_only:
            _fill(context, "readOnlyRootFilesystem", True)
        container["securityContext"] = context


def _pss_violations(profile: str, pod_spec: dict) -> list[str]:
    """Return the fields of a rendered pod spec that the PSS profile forbids."""
    restricted = profile == "restricted"
    found = [
        f"spec.{field}"
        for field in ("hostNetwork", "hostPID", "hostIPC")
        if pod_spec.get(field) is True
    ]
    for volume in pod_spec.get("volumes") or []:
        for kind in sorted(set(volume) - {"name"}):
            if kind == "hostPath" or (
                restricted and kind not in PSS_RESTRICTED_VOLUME_TYPES
            ):
                found.append(f"spec.volumes[{volume.get('name')}].{kind}")
    pod_context = pod_spec.get("securityContext") or {}
    containers = [
        (
            f"spec.{kind}[{container.get('name')}]",
            container.get("securityContext") or {},
        )
        for kind in ("containers", "initContainers")
        for container in pod_spec.get(kind) or []
    ]
    for sysctl in pod_context.get("sysctls") or []:
        if sysctl.get("name") not in PSS_SAFE_SYSCTLS:
            found.append(f"spec.securityContext.sysctls[{sysctl.get('name')}]")
    allowed_caps = {"NET_BIND_SERVICE"} if restricted else PSS_BASELINE_CAPABILITIES
    for path, context in [("spec", pod_context)] + containers:
        capabilities = context.get("capabilities") or {}
        selinux = context.get("seLinuxOptions") or {}
        checks = {
            "privileged": context.get("privileged") is True,
            "capabilities.add": bool(set(capabilities.get("add") or []) - allowed_caps),
            "procMount": context.get("procMount") not in (None, "Default"),
            "windowsOptions.hostProcess": (context.get("windowsOptions") or {}).get(
                "hostProcess"
            )
            is True,
            "seccompProfile.type": (context.get("seccompProfile") or {}).get("type")
            == "Unconfined",
            "appArmorProfile.type": (context.get("appArmorProfile") or {}).get("type")
            == "Unconfined",
            "seLinuxOptions.type": selinux.get("type") not in PSS_SELINUX_TYPES,
            "seLinuxOptions.user": bool(selinux.get("user")),
            "seLinuxOptions.role": bool(selinux.get("role")),
        }
        if restricted:
            checks["runAsNonRoot"] = context.get("runAsNonRoot") is False
            checks["runAsUser"] = context.get("runAsUser") == 0
            if path != "spec":
                checks["allowPrivilegeEscalation"] = (
                    context.get("allowPrivilegeEscalation") is not False
                )
                checks["capabilities.drop"] = "ALL" not in (
                    capabilities.get("drop") or []
                )
        found += [
            f"{path}.securityContext.{field}"
            for field, failed in checks.items()
            if failed
        ]
    if restricted:
        # Container fields may stay unset when the pod-level field is compliant.
        if pod_context.get("runAsNonRoot") is not True and not all(
            context.get("runAsNonRoot") is True for _, context in containers
        ):
            found.append("spec.securityContext.runAsNonRoot")
        seccomp = (pod_context.get("seccompProfile") or {}).get("type")
        if seccomp not in PSS_SECCOMP_TYPES and not all(
            (context.get("seccompProfile") or {}).get("type") in PSS_SECCOMP_TYPES
            for _, context in containers
        ):
            found.append("spec.securityContext.seccompProfile.type")
    return sorted(set(found))


def _warn_best_practices(name: str, component: Any, pod_spec: dict) -> None:
    """Log best-practice warnings for a component's rendered pod spec."""
    batch = component.get("type") == "job" or bool(component.get("schedule"))
    containers = pod_spec.get("containers") or []
    for container in containers + (pod_spec.get("initContainers") or []):
        container_name = container.get("name")
        image = container.get("image")
        tag = str(image).rsplit("/", 1)[-1].partition(":")[2]
        if isinstance(image, str) and "@" not in image and tag in ("", "latest"):
            policy = container.get("imagePullPolicy")
            logger.warning(
                "%s: container %s image %r has no pinned tag or digest; "
                "imagePullPolicy is %s%s",
                name,
                container_name,
                image,
                policy,
                ", the generator default, so nodes keep running a stale cached image"
                if policy == "IfNotPresent"
                else "",
            )
        resources = container.get("resources") or {}
        missing = [
            f"{section}.{key}"
            for section, key in (
                ("requests", "cpu"),
                ("requests", "memory"),
                ("limits", "memory"),
            )
            if not (resources.get(section) or {}).get(key)
        ]
        if missing:
            logger.warning(
                "%s: container %s has no resources %s; requests drive scheduling "
                "and a memory limit bounds the impact of a leak",
                name,
                container_name,
                ", ".join(missing),
            )
    for container in [] if batch else containers:
        if container.get("ports") and not container.get("readinessProbe"):
            logger.warning(
                "%s: container %s has ports but no readiness probe "
                "(healthcheck.readiness); it receives traffic before it is ready",
                name,
                container.get("name"),
            )
    min_available = component.get("pdb_min_available")
    if batch or component.get("type") == "daemonset" or component.get("auto_pdb"):
        return
    replicas = (component.get("hpa") or {}).get("min_replicas")
    if not isinstance(replicas, int):
        replicas = component.get("replicas")
    if not isinstance(replicas, int):
        replicas = 1
    if min_available == "100%" or (
        isinstance(min_available, int) and min_available >= replicas
    ):
        logger.warning(
            "%s: pdb_min_available %s >= %s replicas allows no eviction, "
            "which blocks node drains",
            name,
            min_available,
            replicas,
        )


class WorkloadCommon(BaseObj):
    """Common functionality shared by all workload types."""

    def set_replicas(self, replicas):
        # An HPA owns the replica count; a static value would reset it on every
        # apply: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#migrating-deployments-and-statefulsets-to-horizontal-autoscaling
        if not self.kwargs.component.get("hpa"):
            self.root.spec.replicas = replicas

    def add_containers(self, containers):
        if not self.root.spec.template.spec.containers:
            self.root.spec.template.spec.containers = []
        self.root.spec.template.spec.containers += [
            container.root for container in containers
        ]

    def add_init_containers(self, containers):
        if not self.root.spec.template.spec.initContainers:
            self.root.spec.template.spec.initContainers = []
        self.root.spec.template.spec.initContainers += [
            container.root for container in containers
        ]

    def add_volumes(self, volumes):
        if volumes:
            self.root.spec.template.spec.volumes = []
        for name, volume in volumes.items():
            if not volume.get("name"):
                volume.name = name
            volume_type = next(iter(volume))
            if volume_type == "configMap":
                config_name = volume["configMap"].get("name")
                # check versioning (requires generators.kubernetes.[configs|secrets] to be versioned)
                generator_configs = (
                    inv.parameters.get("generators", {})
                    .get("kubernetes", {})
                    .get("configs", {})
                )
                config = generator_configs.get(config_name)
                if config and config.get("versioned"):
                    config_hash = config.get("hash")
                    if config_hash:
                        volume["configMap"]["name"] += f"-{config_hash}"

            self.root.spec.template.spec.volumes.append(volume)

    def add_volume_claims(self, volume_claims):
        templates = []
        for key, value in volume_claims.items():
            value = _convert_to_dict(value)
            merge({"metadata": {"name": key, "labels": {"name": key}}}, value)
            templates.append(value)
        if templates:
            self.root.spec.volumeClaimTemplates = templates

    def add_volumes_for_objects(self, objects):
        # Import here to avoid circular imports
        from .config import ComponentConfig
        from .workloads import CronJob

        for object in objects.root:
            object_name = object.name
            rendered_name = object.root.metadata.name

            if type(object) is ComponentConfig:
                key = "configMap"
                name_key = "name"
            else:
                key = "secret"
                name_key = "secretName"

            # Do not touch spec.template on CronJobs — kadet auto-vivifies
            # accessed paths, which would leak an invalid spec.template key.
            if isinstance(self, CronJob):
                template = self.root.spec.jobTemplate.spec.template
            else:
                template = self.root.spec.template

            # Append to existing volumes (user-defined volumes and volumes
            # from a previous call for the other object class must survive).
            if not template.spec.get("volumes"):
                template.spec.volumes = []
            source = {
                "defaultMode": object.config.get("default_mode", 420),
                name_key: rendered_name,
            }
            if object.items:
                source["items"] = [{"key": v, "path": v} for v in object.items]
            template.spec.volumes += [{"name": object_name, key: source}]

            # versioned: env and envFrom refs carry the hashed name
            unhashed = object.kwargs.get("rendered_name", object_name)
            if rendered_name != unhashed:
                ref_key = "configMapKeyRef" if key == "configMap" else "secretKeyRef"
                env_from_key = "configMapRef" if key == "configMap" else "secretRef"
                for container in template.spec.get("containers", []) + (
                    template.spec.get("initContainers") or []
                ):
                    for env in container.get("env") or []:
                        ref = (env.get("valueFrom") or {}).get(ref_key)
                        if ref and ref.get("name") == unhashed:
                            ref["name"] = rendered_name
                    for env_from in container.get("envFrom") or []:
                        ref = env_from.get(env_from_key)
                        if ref and ref.get("name") == unhashed:
                            ref["name"] = rendered_name


class SharedConfig:
    """Shared class to use for both Secrets and ConfigMaps classes.

    Contains anything needed by both classes, so that their behavior is basically the same.
    Each subclass will then implement its own way of adding the data depending on their implementation.
    """

    def setup_metadata(self):
        # Import here to avoid circular imports
        from .config import ConfigMap

        # Use get_namespace helper to safely get namespace value
        namespace = get_namespace(self.config) or get_namespace(self.kwargs.component)
        if namespace:
            self.add_namespace(namespace)

        self.add_annotations(self.config.get("annotations", {}))
        self.add_labels(self.config.get("labels", {}))

        self.items = self.config.get("items", [])
        try:
            if isinstance(self, ConfigMap):
                globals = (
                    inv.parameters.get("generators", {})
                    .get("manifest", {})
                    .get("default_config", {})
                    .get("globals", {})
                    .get("config_maps", {})
                )
            else:
                globals = (
                    inv.parameters.get("generators", {})
                    .get("manifest", {})
                    .get("default_config", {})
                    .get("globals", {})
                    .get("secrets", {})
                )
            self.add_annotations(globals.get("annotations", {}))
            self.add_labels(globals.get("labels", {}))
        except AttributeError:
            pass

    def add_directory(self, directory, encode=False):
        import os

        stringdata = inv.parameters.get("use_tesoro", False)
        if directory and os.path.isdir(directory):
            # Sorted: filesystem enumeration order varies by machine and
            # feeds the versioning() content hash.
            for filename in sorted(os.listdir(directory)):
                with open(f"{directory}/{filename}") as f:
                    file_content = f.read()
                    self.add_item(
                        filename,
                        file_content,
                        request_encode=encode,
                        stringdata=stringdata,
                    )

    def add_data(self, data):
        from .config import ConfigMap

        stringdata = inv.parameters.get("use_tesoro", False)

        for key, spec in data.items():
            # Secret data must be base64 (core/v1 Secret.data); ConfigMap data is plain.
            encode = spec.get("b64_encode", not isinstance(self, ConfigMap))

            value = None
            has_source = False
            if "value" in spec:
                value = spec.get("value")
                has_source = True
            if "template" in spec:
                value = j2(spec.get("template"), spec.get("values", {}))
                has_source = True
            if "file" in spec:
                with open(spec.get("file")) as f:
                    value = f.read()
                has_source = True
            if not has_source:
                raise ValueError(
                    f"data entry '{key}' needs one of 'value', 'template' or 'file'"
                )

            self.add_item(key, value, request_encode=encode, stringdata=stringdata)

    def add_string_data(self, string_data, encode=False):
        stringdata = True

        for key, spec in string_data.items():
            value = None
            has_source = False
            if "value" in spec:
                value = spec.get("value")
                has_source = True
            if "template" in spec:
                value = j2(spec.get("template"), spec.get("values", {}))
                has_source = True
            if "file" in spec:
                with open(spec.get("file")) as f:
                    value = f.read()
                has_source = True
            if not has_source:
                raise ValueError(
                    f"string_data entry '{key}' needs one of 'value', 'template' or 'file'"
                )

            self.add_item(key, value, request_encode=encode, stringdata=stringdata)

    def versioning(self):
        # Import here to avoid circular imports
        from .config import ComponentConfig, ComponentSecret, ConfigMap

        keys_of_interest = ["data", "binaryData", "stringData"]
        subset = {
            key: value
            for key, value in self.root.dump().items()
            if key in keys_of_interest
        }
        self.hash = hashlib.sha256(str(subset).encode()).hexdigest()[:8]
        self.root.metadata.name += f"-{self.hash}"

        # add hash to inv to link components later. The container must support
        # item assignment for both backends: plain dict (reclass) and
        # OmegaConf DictConfig - an isinstance(dict) check silently skipped
        # the write-back under OmegaConf.
        if isinstance(self, (ComponentConfig, ConfigMap)):
            configs = (
                inv.parameters.get("generators", {})
                .get("kubernetes", {})
                .get("configs", {})
            )
            if configs and self.name in configs:
                configs[self.name]["hash"] = self.hash
        elif isinstance(self, (ComponentSecret)):
            secrets = (
                inv.parameters.get("generators", {})
                .get("kubernetes", {})
                .get("secrets", {})
            )
            if secrets and self.name in secrets:
                secrets[self.name]["hash"] = self.hash


class Container(BaseObj):
    """Container specification for pods."""

    def new(self):
        self.need("name")
        self.need("container")
        self.root.env = []
        self.root.envFrom = []
        self.root.volumeMounts = []
        self.root.ports = []

    @staticmethod
    def find_key_in_config(key, configs):
        import os

        for name, config in configs.items():
            keys = set(config.get("data") or {}) | set(config.get("string_data") or {})
            directory = config.get("directory")
            if directory and os.path.isdir(directory):
                keys |= set(os.listdir(directory))
            if key in keys:
                return name
        raise ValueError(f"Unable to find key {key} in your configs definitions")

    def get_detailed_name(self, refs_container, value: dict, ref_type: str) -> str:
        if len(refs_container.keys()) == 1:
            return cast("str", self.kwargs.name)
        config_name = self.find_key_in_config(value[ref_type]["key"], refs_container)
        return f"{self.kwargs.name}-{config_name}"

    def process_envs(self, container):
        for name, value in container.get("env", {}).items():
            if isinstance(value, dict):
                if "fieldRef" in value:
                    self.root.env += [{"name": name, "valueFrom": value}]
                elif "secretKeyRef" in value:
                    if "name" not in value["secretKeyRef"]:
                        value["secretKeyRef"]["name"] = self.get_detailed_name(
                            container.get("secrets", {}), value, "secretKeyRef"
                        )
                    self.root.env += [{"name": name, "valueFrom": value}]

                if "configMapKeyRef" in value:
                    if "name" not in value["configMapKeyRef"]:
                        value["configMapKeyRef"]["name"] = self.get_detailed_name(
                            container.get("config_maps", {}), value, "configMapKeyRef"
                        )

                    self.root.env += [{"name": name, "valueFrom": value}]
            else:
                self.root.env += [{"name": name, "value": str(value)}]
        # using envFrom
        for name, ref_items in sorted(container.get("env_from", {}).items()):
            for ref in ref_items:
                if not ("secretRef" in ref or "configMapRef" in ref):
                    raise ValueError(f"{name}: {ref} is invalid env_from item")
                # look up name
                ref_type = next(iter(ref))
                ref_name = ref[ref_type].get("name")
                if not ref_name:
                    refs_container = (
                        container.get("secrets", {})
                        if ref_type == "secretRef"
                        else container.get("config_maps", {})
                    )
                    ref_name = self.get_detailed_name(refs_container, ref, ref_type)

                # check versioning (requires generators.kubernetes.[configs|secrets] to be versioned)
                ref_type_short = ref_type[:6] + "s"  # secretRef --> secrets
                generator_refs = (
                    inv.parameters.get("generators", {})
                    .get("kubernetes", {})
                    .get(ref_type_short, {})
                )
                ref_config = generator_refs.get(ref_name)
                if ref_config and ref_config.get("versioned"):
                    ref_name += f"-{ref_config.get('hash')}"

                self.root.envFrom.append({ref_type: {"name": ref_name}})

    def add_volume_mounts_from_configs(self):
        from kapitan.inputs.kadet import CompileError

        name = self.kwargs.name
        container = self.kwargs.container
        configs = container.get("config_maps", {}).items()
        secrets = container.get("secrets", {}).items()
        for object_name, spec in configs:
            if spec is None:
                raise CompileError(
                    f"error with '{object_name}' for component {name}: configuration cannot be empty!"
                )

            if "mount" in spec:
                mount = {"mountPath": spec.get("mount"), "name": object_name}
                if spec.get("readOnly") is not None:
                    mount["readOnly"] = spec.get("readOnly")
                if spec.get("subPath"):
                    mount["subPath"] = spec.get("subPath")
                self.root.volumeMounts += [mount]
        for object_name, spec in secrets:
            if spec is None:
                raise CompileError(
                    f"error with '{object_name}' for component {name}: configuration cannot be empty!"
                )

            if "mount" in spec:
                mount = {"mountPath": spec.get("mount"), "name": object_name}
                if spec.get("readOnly") is not None:
                    mount["readOnly"] = spec.get("readOnly")
                if spec.get("subPath"):
                    mount["subPath"] = spec.get("subPath")
                self.root.volumeMounts += [mount]

    def add_volume_mounts(self, volume_mounts):
        for key, value in volume_mounts.items():
            mount = {
                "name": key,
                "mountPath": value.get("mount_path"),
            }
            # Add optional fields if present
            if value.get("sub_path"):
                mount["subPath"] = value.get("sub_path")
            if value.get("read_only") is not None:
                mount["readOnly"] = value.get("read_only")
            if value.get("mount_propagation"):
                mount["mountPropagation"] = value.get("mount_propagation")
            self.root.volumeMounts += [mount]

    @staticmethod
    def create_probe(probe_definition):
        probe = BaseObj()
        if "type" in probe_definition:
            probe.root.initialDelaySeconds = probe_definition.get(
                "initial_delay_seconds", 0
            )
            probe.root.periodSeconds = probe_definition.get("period_seconds", 10)
            probe.root.timeoutSeconds = probe_definition.get("timeout_seconds", 5)
            probe.root.successThreshold = probe_definition.get("success_threshold", 1)
            probe.root.failureThreshold = probe_definition.get("failure_threshold", 3)

            if probe_definition.get("type") == "http":
                probe.root.httpGet.scheme = probe_definition.get("scheme", "HTTP")
                probe.root.httpGet.port = probe_definition.get("port", 80)
                probe.root.httpGet.path = probe_definition.get("path")
                if probe_definition.get("httpHeaders"):
                    probe.root.httpGet.httpHeaders = probe_definition.get("httpHeaders")
            if probe_definition.get("type") == "tcp":
                probe.root.tcpSocket.port = probe_definition.get("port")
            if probe_definition.get("type") == "command":
                probe.root.exec.command = probe_definition.get("command")
            if probe_definition.get("type") == "grpc":
                probe.root.grpc.port = probe_definition.get("port", 80)

        return probe.root

    def body(self):
        name = self.kwargs.name
        container = self.kwargs.container

        self.root.name = name
        self.root.image = container.get("image")

        pull_policy = container.get("pull_policy", "IfNotPresent")
        _validate_enum(pull_policy, VALID_IMAGE_PULL_POLICIES, "imagePullPolicy")
        self.root.imagePullPolicy = pull_policy

        if container.get("lifecycle"):
            self.root.lifecycle = container.get("lifecycle")
        self.root.resources = container.get("resources", {})
        args = container.get("args")
        if isinstance(args, dict):
            # A mapping lets a target override or drop one argument by key (K8S-4).
            listed = []
            for key, value in args.items():
                if isinstance(value, dict):
                    raise ValueError(f"{name}: args.{key} must be a string or a list, not a mapping")
                if value is not None:
                    listed += [str(v) for v in value] if isinstance(value, list) else [str(value)]
            args = listed
        if args:
            self.root.args = args
        if container.get("command"):
            self.root.command = container.get("command")
        self.root.securityContext = container.get("security_context", {})
        self.add_volume_mounts_from_configs()
        self.add_volume_mounts(container.get("volume_mounts", {}))

        # Validate protocol in ports
        for name, port in sorted(container.get("ports", {}).items()):
            protocol = port.get("protocol", "TCP")
            _validate_enum(protocol, VALID_PROTOCOL_TYPES, "protocol")
            self.root.ports += [
                {
                    "containerPort": port.get(
                        "container_port", port.get("service_port")
                    ),
                    "name": name,
                    "protocol": protocol,
                }
            ]

        # Init containers run to completion: the API rejects probes on them.
        healthcheck = {} if self.kwargs.get("init") else container.get("healthcheck", {})
        for key, field in (
            ("startup", "startupProbe"),
            ("liveness", "livenessProbe"),
            ("readiness", "readinessProbe"),
        ):
            if (healthcheck.get(key) or {}).get("type"):
                self.root[field] = self.create_probe(healthcheck.get(key))
        self.process_envs(container)
        for field in ("env", "envFrom", "volumeMounts", "ports"):
            if not self.root[field]:
                del self.root[field]


class Workload(WorkloadCommon):
    """Factory class that creates the appropriate workload type."""

    def new(self):
        self.need("name")
        self.need("component")

    def body(self):
        # Import here to avoid circular imports
        from .workloads import DaemonSet, Deployment, Job, StatefulSet

        component = self.kwargs.component
        name = self.kwargs.name
        component_type = component.get("type")
        if component_type == "deployment":
            workload = Deployment(name=name, component=self.kwargs.component)
        elif component_type == "statefulset":
            workload = StatefulSet(name=name, component=self.kwargs.component)
        elif component_type == "daemonset":
            workload = DaemonSet(name=name, component=self.kwargs.component)
        elif component_type == "job":
            workload = Job(name=name, component=self.kwargs.component)
        else:
            raise ValueError(
                f"Unknown workload type '{component_type}' for component '{name}'. "
                "Must be one of: deployment, statefulset, daemonset, job"
            )

        # Use get_namespace helper to safely get namespace value
        namespace = get_namespace(component)
        if namespace:
            workload.root.metadata.namespace = namespace
        workload.add_annotations(component.get("annotations", {}))
        _set_if_truthy(
            workload.root.spec.template.metadata,
            "annotations",
            component.get("pod_annotations"),
        )
        if component.get("recommended_labels"):
            # https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/
            # Added after the selector snapshot, so selectors never change.
            recommended = {
                "app.kubernetes.io/name": name,
                "app.kubernetes.io/managed-by": "kapitan",
            }
            if component.get("application"):
                recommended["app.kubernetes.io/part-of"] = component.get("application")
            workload.add_labels(recommended)
            workload.root.spec.template.metadata.labels.update(recommended)
        workload.add_labels(component.get("labels", {}))
        workload.root.spec.template.metadata.labels.update(
            component.get("pod_labels", {})
        )
        workload.add_volumes(component.get("volumes", {}))
        workload.add_volume_claims(component.get("volume_claims", {}))

        # Optional fields - only set if truthy to avoid OmegaConf empty dicts
        pod_spec = workload.root.spec.template.spec
        _set_if_truthy(
            pod_spec, "securityContext", component.get("workload_security_context")
        )
        _set_if_truthy(
            pod_spec, "priorityClassName", component.get("priority_class_name")
        )
        _set_if_truthy(pod_spec, "resourceClaims", component.get("resource_claims"))
        _set_if_truthy(
            workload.root.spec, "minReadySeconds", component.get("min_ready_seconds")
        )

        service_account = component.get("service_account", {})
        if service_account.get("enabled") or service_account.get("create"):
            workload.root.spec.template.spec.serviceAccountName = service_account.get(
                "name", name
            )
        # Opt out of API credential automounting unless the component opts in:
        # https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#opt-out-of-api-credential-automounting
        automount = component.get("automount_service_account_token")
        workload.root.spec.template.spec.automountServiceAccountToken = (
            automount if automount is not None else False
        )
        if component.get("enable_service_links") is not None:
            workload.root.spec.template.spec.enableServiceLinks = component.get(
                "enable_service_links"
            )

        container = []
        container = Container(name=name, container=component)
        additional_containers = []
        additional_containers = [
            Container(name=name, container=component)
            for name, component in component.get("additional_containers", {}).items()
        ]
        workload.add_containers([container])
        workload.add_containers(additional_containers)
        init_containers = []
        init_containers = [
            Container(name=name, container=component, init=True)
            for name, component in component.get("init_containers", {}).items()
        ]

        workload.add_init_containers(init_containers)

        profile = component.get("security_profile")
        if profile:
            _validate_enum(profile, VALID_SECURITY_PROFILES, "security_profile")
        _apply_security_profile(pod_spec, component)
        rendered = _convert_to_dict(pod_spec)
        _warn_best_practices(name, component, rendered)
        if profile:
            for field in _pss_violations(profile, rendered):
                logger.warning(
                    "%s: %s violates the Pod Security Standards %s profile "
                    "(security_profile); keeping the configured value",
                    name,
                    field,
                    profile,
                )

        _inv_pull_secrets = inv.parameters.get("image_pull_secrets")
        if component.get("image_pull_secrets") or _inv_pull_secrets:
            workload.root.spec.template.spec.imagePullSecrets = component.get(
                "image_pull_secrets", _inv_pull_secrets
            )
        if component.get("dns_policy"):
            workload.root.spec.template.spec.dnsPolicy = component.get("dns_policy")
        if component.get("grace_period") is not None:
            workload.root.spec.template.spec.terminationGracePeriodSeconds = (
                component.get("grace_period")
            )

        if component.get("node_selector"):
            workload.root.spec.template.spec.nodeSelector = component.get(
                "node_selector"
            )

        if component.get("tolerations"):
            workload.root.spec.template.spec.tolerations = component.get("tolerations")

        # The affinity block passes through; the prefer_* shorthands append to it.
        affinity = _convert_to_dict(component.get("affinity")) or {}

        def prefer(section, term):
            preferred = affinity.setdefault(section, {}).setdefault(
                "preferredDuringSchedulingIgnoredDuringExecution", []
            )
            preferred.append(term)

        if component.get("prefer_pods_in_node_with_expression") and not component.get(
            "node_selector"
        ):
            prefer(
                "nodeAffinity",
                {
                    "preference": {
                        "matchExpressions": [
                            component.get("prefer_pods_in_node_with_expression")
                        ]
                    },
                    "weight": 1,
                },
            )
        for key, topology in (
            ("prefer_pods_in_different_nodes", "kubernetes.io/hostname"),
            ("prefer_pods_in_different_zones", "topology.kubernetes.io/zone"),
        ):
            if component.get(key):
                prefer(
                    "podAntiAffinity",
                    {
                        "podAffinityTerm": {
                            "labelSelector": {
                                "matchExpressions": [
                                    {"key": "name", "operator": "In", "values": [name]}
                                ]
                            },
                            "topologyKey": topology,
                        },
                        "weight": 1,
                    },
                )
        if affinity:
            workload.root.spec.template.spec.affinity = affinity
        if not pod_spec.initContainers:
            del pod_spec["initContainers"]

        self.root = workload.root
