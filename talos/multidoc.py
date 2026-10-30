"""Translate deprecated v1alpha1 fields into Talos v1.14 multi-document kinds.

Each translator pops the legacy keys it handles from the v1alpha1 machine
and cluster sections and returns the replacement documents. The mapping
follows the legacy bridges of Talos v1.14.5
(pkg/machinery/config/types/v1alpha1/v1alpha1_*_bridge.go) and the
documents `talosctl gen config` writes at that release, so a translated
config behaves like the legacy one. Values the legacy path defaulted
implicitly but a document needs explicitly (images, subnets, the control
plane label and taint, the default authorizers) are filled in here.

A legacy block without a multi-document equivalent stays in the v1alpha1
document, which Talos v1.14 still accepts, and logs a warning.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Newest patch of constants.DefaultKubernetesVersion (1.37.1) at Talos v1.14.5 (TAL-4).
IMAGES = {
    "kubelet": "ghcr.io/siderolabs/kubelet:v1.37.2@sha256:d80d3843530cfae376a0814f73bcc4ac70e32bc157de777b38a90f33b82d1111",
    "apiServer": "registry.k8s.io/kube-apiserver:v1.37.2@sha256:3e563afb5cb5b72a10bac7012698dd09f5a42bde7d22de8d7d3c12e654df86b4",
    "controllerManager": "registry.k8s.io/kube-controller-manager:v1.37.2@sha256:28e62daf706ed815a8bd1dd27b03294ba09421b2e1674e9a83bbac38e24ceb0c",
    "scheduler": "registry.k8s.io/kube-scheduler:v1.37.2@sha256:028c847fc321b8a7f9787f7b1c0840f832d6b68439be2e5c09279ffb14203d6b",
    "proxy": "registry.k8s.io/kube-proxy:v1.37.2@sha256:b2e075697d7ab4f0878775dff9e5dccf818b67644437175210ce72fc1ec70551",
}
# Where each component's block sits in the v1alpha1 config.
COMPONENTS = {
    "kubelet": ("machine", "kubelet"),
    "apiServer": ("cluster", "apiServer"),
    "controllerManager": ("cluster", "controllerManager"),
    "scheduler": ("cluster", "scheduler"),
    "proxy": ("cluster", "proxy"),
}
CONTROL_PLANE_LABEL = "node-role.kubernetes.io/control-plane"

# Kinds Talos rejects on worker machines (ControlplaneOnlyDocument), plus the
# manifest kinds, which only the control plane applies.
CONTROL_PLANE_KINDS = frozenset(
    {
        "KubeAPIServerConfig",
        "KubeAdmissionControlConfig",
        "KubeAggregatorCAConfig",
        "KubeAuditPolicyConfig",
        "KubeAuthenticationConfig",
        "KubeAuthorizerConfig",
        "KubeControllerManagerConfig",
        "KubeCoreDNSConfig",
        "KubeEtcdEncryptionConfig",
        "KubeFlannelCNIConfig",
        "KubeProxyConfig",
        "KubeSchedulerConfig",
        "KubeServiceAccountConfig",
        "KubeTalosAPIAccessConfig",
        "KubeExternalManifestConfig",
        "KubeInlineManifestConfig",
    }
)


def _doc(kind: str, **fields: Any) -> dict:
    """A v1alpha1 multi-document of *kind* without the fields that are None."""
    doc = {"apiVersion": "v1alpha1", "kind": kind}
    doc.update({k: v for k, v in fields.items() if v is not None})
    return doc


def _pick(src: dict, *keys: str) -> dict:
    return {k: src[k] for k in keys if src.get(k) is not None}


def _pem(value: Any) -> Any:
    """Legacy certificates and keys are base64-encoded PEM, documents take PEM.

    Values that are not base64 PEM (PEM already, or a Kapitan ref) pass
    through unchanged.
    """
    if not isinstance(value, str) or value.lstrip().startswith("-----BEGIN"):
        return value
    try:
        decoded = base64.b64decode(value, validate=True).decode()
    except ValueError:
        return value
    return decoded if decoded.lstrip().startswith("-----BEGIN") else value


def _keep(node: str, path: str) -> None:
    logger.warning(
        "node '%s': %s has no Talos v1.14 multi-document equivalent; "
        "kept in the deprecated v1alpha1 form",
        node,
        path,
    )


def _drop_empty(section: dict, key: str) -> None:
    if key in section and not section[key]:
        del section[key]


# ---------------------------------------------------------------- network


def _routes(routes: list) -> list:
    out = []
    for route in routes or []:
        r = _pick(route, "gateway", "source", "metric", "mtu")
        # A default route has no destination in RouteConfig; 0.0.0.0/0 is rejected.
        if route.get("network") and route["network"] not in ("0.0.0.0/0", "::/0"):
            r["destination"] = route["network"]
        out.append(r)
    return out


def _addresses(device: dict) -> list | None:
    addrs = list(device.get("addresses") or [])
    if device.get("cidr"):
        addrs.append(device["cidr"])
    return [{"address": a} for a in addrs] or None


def _dhcp(name: str, device: dict) -> list:
    if not device.get("dhcp"):
        return []
    opts = device.get("dhcpOptions") or {}
    metric = opts.get("routeMetric")
    docs = []
    if opts.get("ipv4", True):
        docs.append(_doc("DHCPv4Config", name=name, routeMetric=metric))
    if opts.get("ipv6"):
        docs.append(
            _doc("DHCPv6Config", name=name, routeMetric=metric, duidRaw=opts.get("duidv6"))
        )
    return docs


def _vip(name: str, vip: dict | None) -> list:
    if not vip:
        return []
    if (vip.get("hcloud") or {}).get("apiToken"):
        return [
            _doc("HCloudVIPConfig", name=vip["ip"], link=name, apiToken=vip["hcloud"].get("apiToken"))
        ]
    return [_doc("Layer2VIPConfig", name=vip["ip"], link=name)]


BOND_RENAMES = {
    "interfaces": "links",
    "mode": "bondMode",
    "arpIPTarget": "arpIpTargets",
    "resendIgmp": "resendIGMP",
    "tlbDynamicLb": "tlbLogicalLb",
    "peerNotifyDelay": "peerNotifDelay",
}
BOND_UNSUPPORTED = ("deviceSelectors", "primary", "adActorSystem")
DEVICE_UNSUPPORTED = ("deviceSelector",)


def _untranslatable_device(device: dict) -> bool:
    if any(device.get(k) for k in DEVICE_UNSUPPORTED):
        return True
    if any((device.get("bond") or {}).get(k) for k in BOND_UNSUPPORTED):
        return True
    for vip in [device.get("vip")] + [v.get("vip") for v in device.get("vlans") or []]:
        if vip and (vip.get("equinixMetal") or {}).get("apiToken"):
            return True
    return False


def _links(interfaces: list) -> list:
    docs: list = []
    bridge_ports: dict[str, list] = {}
    for device in interfaces:
        master = (device.get("bridgePort") or {}).get("master")
        if master:
            bridge_ports.setdefault(master, []).append(device["interface"])
    for device in interfaces:
        name = device["interface"]
        if device.get("ignore"):
            # Without link documents Talos runs no default DHCP, which is
            # what `ignore` asked for.
            continue
        common = {
            "mtu": device.get("mtu"),
            "addresses": _addresses(device),
            "routes": _routes(device.get("routes")) or None,
        }
        if device.get("bond"):
            bond = device["bond"]
            fields = {BOND_RENAMES.get(k, k): v for k, v in bond.items()}
            docs.append(_doc("BondConfig", name=name, **fields, **common))
        elif device.get("bridge") or name in bridge_ports:
            bridge = device.get("bridge") or {}
            links = list(bridge.get("interfaces") or [])
            links += [p for p in bridge_ports.get(name, []) if p not in links]
            vlan = bridge.get("vlan") or {}
            docs.append(
                _doc(
                    "BridgeConfig",
                    name=name,
                    links=links,
                    stp=bridge.get("stp"),
                    vlan={"filtering": vlan["vlanFiltering"]} if "vlanFiltering" in vlan else None,
                    **common,
                )
            )
        elif device.get("wireguard"):
            docs.append(_doc("WireguardConfig", name=name, **device["wireguard"], **common))
        elif device.get("dummy"):
            docs.append(_doc("DummyLinkConfig", name=name, **common))
        else:
            docs.append(_doc("LinkConfig", name=name, **common))
        docs += _dhcp(name, device)
        docs += _vip(name, device.get("vip"))
        for vlan in device.get("vlans") or []:
            vname = f"{name}.{vlan['vlanId']}"
            docs.append(
                _doc(
                    "VLANConfig",
                    name=vname,
                    vlanID=vlan["vlanId"],
                    parent=name,
                    mtu=vlan.get("mtu"),
                    addresses=_addresses(vlan),
                    routes=_routes(vlan.get("routes")) or None,
                )
            )
            docs += _dhcp(vname, vlan)
            docs += _vip(vname, vlan.get("vip"))
    return docs


def _network(node: str, machine: dict, features: dict) -> list:
    net = machine.get("network") or {}
    docs = []
    hostname = net.pop("hostname", None)
    stable = features.pop("stableHostname", None)
    if hostname:
        docs.append(_doc("HostnameConfig", hostname=hostname))
    elif stable:
        docs.append(_doc("HostnameConfig", auto="stable"))

    resolver = {}
    if net.get("nameservers"):
        resolver["nameservers"] = [{"address": a} for a in net["nameservers"]]
    search = {}
    if net.get("searchDomains"):
        search["domains"] = net["searchDomains"]
    if net.get("disableSearchDomain") is not None:
        search["disableDefault"] = net["disableSearchDomain"]
    if search:
        resolver["searchDomains"] = search
    if features.get("hostDNS"):
        resolver["hostDNS"] = features["hostDNS"]
    features.pop("hostDNS", None)
    for key in ("nameservers", "searchDomains", "disableSearchDomain"):
        net.pop(key, None)
    if resolver:
        docs.append(_doc("ResolverConfig", **resolver))

    for entry in net.pop("extraHostEntries", None) or []:
        docs.append(_doc("StaticHostConfig", name=entry["ip"], hostnames=entry.get("aliases")))

    if net.get("kubespan"):
        docs.append(_doc("KubeSpanConfig", **net.pop("kubespan")))
    net.pop("kubespan", None)

    interfaces = net.get("interfaces")
    if interfaces:
        links = [] if any(_untranslatable_device(d) for d in interfaces) else _links(interfaces)
        if links:
            docs += links
            net.pop("interfaces")
        else:
            # Also when every interface is `ignore`: without a link document
            # Talos would run DHCP on them.
            _keep(node, "machine.network.interfaces (deviceSelector, bond deviceSelectors/primary/"
                        "adActorSystem, equinixMetal VIP, or only ignored links)")
    _drop_empty(net, "interfaces")
    _drop_empty(machine, "network")
    return docs


# ---------------------------------------------------------------- install


def _size_bytes(text: str) -> tuple[str, int]:
    """Parse a legacy size matcher like '>= 100GB' (go-humanize units)."""
    match = re.fullmatch(r"\s*(>=|<=|>|<|==)?\s*([0-9.]+)\s*([A-Za-z]*)\s*", str(text))
    if not match:
        raise ValueError(f"cannot parse install diskSelector size '{text}'")
    op, number, unit = match.groups()
    unit = unit.lower().rstrip("b") or ""
    powers = {"": 1, "k": 10**3, "m": 10**6, "g": 10**9, "t": 10**12, "p": 10**15,
              "ki": 2**10, "mi": 2**20, "gi": 2**30, "ti": 2**40, "pi": 2**50}
    if unit not in powers:
        raise ValueError(f"unknown unit in install diskSelector size '{text}'")
    return op or "==", int(float(number) * powers[unit])


def _cel_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _disk_match(install: dict) -> str:
    """CEL expression of v1alpha1 InstallConfig.DiskMatchExpression at v1.14.5."""
    disk = install.get("disk")
    if disk:
        if disk.startswith("/dev/disk/"):
            return f"{_cel_string(disk)} in disk.symlinks"
        return f"disk.dev_path == {_cel_string(disk)}"
    sel = install["diskSelector"]
    exprs = []
    if sel.get("size") is not None:
        op, size = _size_bytes(sel["size"])
        exprs.append(f"disk.size {op} {size}u")
    for key, field in (("uuid", "uuid"), ("wwid", "wwid"), ("model", "model"),
                       ("serial", "serial"), ("modalias", "modalias")):
        if sel.get(key):
            exprs.append(f"glob({_cel_string(sel[key])}, disk.{field})")
    exprs.append('disk.transport != ""')
    disk_type = sel.get("type")
    if disk_type:
        exprs.append({"nvme": 'disk.transport == "nvme"', "sd": 'disk.transport == "mmc"',
                      "hdd": "disk.rotational", "ssd": "!disk.rotational"}[disk_type])
    if sel.get("busPath"):
        exprs.append(f"glob({_cel_string(sel['busPath'])}, disk.bus_path)")
    exprs += ["!disk.readonly", "!disk.cdrom"]
    return " && ".join(exprs)


INSTALL_KEYS = frozenset({"disk", "diskSelector", "image", "wipe"})


def _install(node: str, machine: dict) -> list:
    install = machine.get("install")
    if not install:
        return []
    extra = sorted(k for k, v in install.items() if k not in INSTALL_KEYS and v)
    if extra or (install.get("diskSelector") or {}).get("name"):
        _keep(node, "machine.install (" + ", ".join(extra or ["diskSelector.name"]) + ")")
        return []
    machine.pop("install")
    return [
        _doc(
            "UnattendedInstallConfig",
            installer={"image": install["image"]},
            provisioning={
                "diskSelector": {"match": _disk_match(install)},
                # The document defaults to wipe: true, the legacy section to false.
                "wipe": bool(install.get("wipe", False)),
            },
        )
    ]


# ---------------------------------------------------------------- machine


def _registries(machine: dict) -> list:
    reg = machine.pop("registries", None) or {}
    docs = []
    for host, mirror in (reg.get("mirrors") or {}).items():
        override = mirror.get("overridePath")
        endpoints = [
            {"url": url, **({"overridePath": override} if override is not None else {})}
            for url in mirror.get("endpoints") or []
        ]
        docs.append(
            _doc("RegistryMirrorConfig", name=host, endpoints=endpoints,
                 skipFallback=mirror.get("skipFallback"))
        )
    for host, cfg in (reg.get("config") or {}).items():
        tls = cfg.get("tls") or {}
        if tls:
            identity = tls.get("clientIdentity")
            docs.append(
                _doc(
                    "RegistryTLSConfig",
                    name=host,
                    clientIdentity={"cert": _pem(identity.get("crt")), "key": _pem(identity.get("key"))}
                    if identity else None,
                    ca=_pem(tls.get("ca")),
                    insecureSkipVerify=tls.get("insecureSkipVerify"),
                )
            )
        auth = cfg.get("auth") or {}
        if auth:
            docs.append(_doc("RegistryAuthConfig", name=host, **auth))
    return docs


def _files(node: str, machine: dict) -> list:
    """/etc/cri/conf.d/<name>.part becomes CRICustomizationConfig <name>."""
    docs, kept = [], []
    for item in machine.get("files") or []:
        path = item.get("path", "")
        if (path.startswith("/etc/cri/conf.d/") and path.endswith(".part")
                and item.get("op", "create") == "create"):
            name = path[len("/etc/cri/conf.d/"):-len(".part")]
            docs.append(_doc("CRICustomizationConfig", name=name, content=item.get("content", "")))
        else:
            kept.append(item)
    if kept:
        _keep(node, "machine.files outside /etc/cri/conf.d/*.part")
        machine["files"] = kept
    else:
        machine.pop("files", None)
    return docs


def _kubelet(node: str, machine: dict, node_cfg: dict) -> list:
    kubelet = machine.get("kubelet")
    if not kubelet:
        return []
    for key in ("registerWithFQDN", "nodeIP", "skipNodeRegistration"):
        if key in kubelet:
            node_cfg[key] = kubelet.pop(key)
    if kubelet.get("extraMounts") or kubelet.get("disableManifestsDirectory") is False:
        _keep(node, "machine.kubelet (extraMounts or disableManifestsDirectory: false)")
        return []
    machine.pop("kubelet")
    docs = []
    if any(k != "disableManifestsDirectory" for k in kubelet):
        docs.append(
            _doc(
                "KubeletConfig",
                image=kubelet.get("image") or IMAGES["kubelet"],
                config=kubelet.get("extraConfig"),
                extraArgs=kubelet.get("extraArgs"),
                clusterDNS=kubelet.get("clusterDNS"),
                defaultRuntimeSeccompProfileEnabled=kubelet.get("defaultRuntimeSeccompProfileEnabled"),
            )
        )
    if kubelet.get("credentialProviderConfig"):
        docs.append(_doc("KubeCredentialProviderConfig", configuration=kubelet["credentialProviderConfig"]))
    return docs


def _machine_docs(node: str, machine: dict, features: dict, node_cfg: dict) -> list:
    docs = _network(node, machine, features)
    docs += _install(node, machine)
    docs += _kubelet(node, machine, node_cfg)
    for pod in machine.pop("pods", None) or []:
        meta = pod.get("metadata") or {}
        name = f"{meta.get('namespace', 'default')}-{meta.get('name', 'default')}"
        docs.append(_doc("KubeStaticPodConfig", name=name, pod=pod))
    docs += _files(node, machine)
    if machine.get("env"):
        docs.append(_doc("EnvironmentConfig", variables=machine["env"]))
    machine.pop("env", None)
    servers = (machine.get("time") or {}).get("servers") or []
    # Legacy servers mix NTP hosts and PTP devices (/dev/...); TimeSyncConfig takes
    # either ntp or ptp, and Talos v1.14.5 rejects PTP devices in ntp.servers.
    ptp = [s for s in servers if str(s).startswith("/dev/")]
    if ptp and len(ptp) < len(servers):
        _keep(node, "machine.time (NTP servers and PTP devices together)")
    elif time := machine.pop("time", None):
        docs.append(
            _doc(
                "TimeSyncConfig",
                enabled=(not time["disabled"]) if "disabled" in time else None,
                bootTimeout=time.get("bootTimeout"),
                ntp={"servers": servers} if servers and not ptp else None,
                ptp={"devices": ptp} if ptp else None,
            )
        )
    for key, kind in (("sysctls", "SysctlConfig"), ("sysfs", "SysfsConfig")):
        params = machine.pop(key, None)
        if params:
            docs.append(_doc(kind, params={k: str(v) for k, v in params.items()}))
    docs += _registries(machine)
    for volume, spec in (machine.pop("systemDiskEncryption", None) or {}).items():
        docs.append(_doc("VolumeConfig", name=volume.upper(), encryption=spec))
    if machine.get("disks"):
        _keep(node, "machine.disks (UserVolumeConfig mounts under /var/mnt/<name>)")
    rules = (machine.pop("udev", None) or {}).get("rules")
    if rules:
        docs.append(_doc("UdevRulesConfig", rules=rules))
    for module in (machine.pop("kernel", None) or {}).get("modules") or []:
        docs.append(_doc("KernelModuleConfig", **module))
    overrides = machine.pop("baseRuntimeSpecOverrides", None)
    if overrides:
        docs.append(_doc("CRIBaseRuntimeSpecConfig", overrides=overrides))
    for key, target in (("nodeLabels", "labels"), ("nodeAnnotations", "annotations"), ("nodeTaints", "taints")):
        if key in machine:
            node_cfg[target] = machine.pop(key)
    access = features.pop("kubernetesTalosAPIAccess", None)
    if access and access.get("enabled"):
        docs.append(_doc("KubeTalosAPIAccessConfig", **_pick(access, "allowedRoles", "allowedKubernetesNamespaces")))
    prism = features.pop("kubePrism", None)
    if prism and prism.get("enabled"):
        docs.append(_doc("KubePrismConfig", port=prism.get("port", 7445)))
    cache = features.pop("imageCache", None)
    if cache:
        docs.append(_doc("ImageCacheConfig", local={"enabled": bool(cache.get("localEnabled"))}))
    return docs


# ---------------------------------------------------------------- cluster


def _component(cluster: dict, mcp: dict, key: str, kind: str, node: str, fields: tuple) -> list:
    """kube-controller-manager or kube-scheduler; mcp is machine.controlPlane."""
    src = cluster.get(key)
    if src is None and key not in mcp:
        return []
    src = src or {}
    if src.get("extraVolumes"):
        _keep(node, f"cluster.{key} (extraVolumes)")
        return []
    cluster.pop(key, None)
    enabled = False if (mcp.pop(key, None) or {}).get("disabled") else None
    return [_doc(kind, enabled=enabled, image=src.get("image") or IMAGES[key], **_pick(src, *fields))]


# deniedArgPrefixes of the KubeAPIServerConfig document (types/k8s/apiserver.go).
AUTH_FLAGS = re.compile(r"^(anonymous-auth|oidc-.*|authentication-config|authorization-config"
                        r"|authorization-mode|authorization-webhook-.*)$")


def _api_server_stays_legacy(api: dict | None) -> bool:
    api = api or {}
    return bool(api.get("extraVolumes") or any(AUTH_FLAGS.match(k) for k in api.get("extraArgs") or {}))


def _api_server(node: str, cluster: dict, port: int | None) -> list:
    api = cluster.get("apiServer")
    if api is None and port is None:
        return []
    api = api or {}
    if _api_server_stays_legacy(api):
        _keep(node, "cluster.apiServer (extraVolumes or authentication/authorization flags in extraArgs)")
        return []
    cluster.pop("apiServer", None)
    docs = [
        _doc(
            "KubeAPIServerConfig",
            image=api.get("image") or IMAGES["apiServer"],
            apiPort=port,
            certExtraSANs=api.get("certSANs"),
            **_pick(api, "extraArgs", "env", "resources"),
        ),
        # DefaultAuthenticationConfig of types/k8s/authentication.go, what
        # `talosctl gen config` writes: the document enables startup probes,
        # which call these paths unauthenticated.
        _doc("KubeAuthenticationConfig", configuration={
            "anonymous": {"conditions": [{"path": "/livez"}, {"path": "/readyz"}, {"path": "/healthz"}],
                          "enabled": True},
            "jwt": [],
        }),
    ]
    authorizers = list(api.get("authorizationConfig") or [])
    # The legacy path inserted Node at 0 and then RBAC at 1 when missing
    # (controllers/k8s/control_plane.go).
    if not any(a.get("type") == "Node" for a in authorizers):
        authorizers.insert(0, {"type": "Node", "name": "node"})
    if not any(a.get("type") == "RBAC" for a in authorizers):
        authorizers.insert(1, {"type": "RBAC", "name": "rbac"})
    docs += [_doc("KubeAuthorizerConfig", **_pick(a, "name", "type", "webhook")) for a in authorizers]
    docs += [_doc("KubeAdmissionControlConfig", **_pick(p, "name", "configuration"))
             for p in api.get("admissionControl") or []]
    if api.get("auditPolicy"):
        docs.append(_doc("KubeAuditPolicyConfig", configuration=api["auditPolicy"]))
    return docs


def _manifest(url: str, headers: dict | None) -> dict:
    """The legacy path named manifests by URL; documents need a DNS subdomain."""
    name = re.sub(r"[^a-z0-9.]+", "-", url.split("://", 1)[-1].lower()).strip("-.")[:253]
    return _doc("KubeExternalManifestConfig", name=name, url=url, headers=headers)


def _cluster_docs(node: str, cluster: dict, machine: dict, node_cfg: dict) -> list:
    docs = []
    discovery = cluster.get("discovery")
    legacy_discovery = bool(discovery) and not (
        ((discovery.get("registries") or {}).get("kubernetes") or {}).get("disabled", True))
    if legacy_discovery:
        # DiscoveryServiceConfig conflicts with any .cluster.discovery block
        # (types/cluster/discovery_service.go) and has no Kubernetes registry;
        # the legacy discovery then also needs .cluster.id/.cluster.secret.
        _keep(node, "cluster.discovery (registries.kubernetes enabled)")
    elif cluster.get("id") and cluster.get("secret"):
        docs.append(_doc("DiscoveryIdentityConfig", clusterID=cluster.pop("id"), clusterSecret=cluster.pop("secret")))

    control_plane = cluster.get("controlPlane") or {}
    endpoint = control_plane.get("endpoint")
    # localAPIServerPort moves to KubeAPIServerConfig; with a legacy apiServer
    # it has to stay, and Talos then needs the endpoint and name next to it.
    port = control_plane.get("localAPIServerPort")
    if port is not None and _api_server_stays_legacy(cluster.get("apiServer")):
        port = None
    else:
        cluster.pop("controlPlane", None)
    if "controlPlane" not in cluster and (cluster.get("clusterName") or endpoint):
        docs.append(_doc("KubeClusterConfig", clusterName=cluster.pop("clusterName", None), endpoint=endpoint))

    net = cluster.pop("network", None)
    if net is not None:
        docs.append(
            _doc(
                "KubeNetworkConfig",
                dnsDomain=net.get("dnsDomain") or "cluster.local",
                podSubnets=net.get("podSubnets") or ["10.244.0.0/16"],
                serviceSubnets=net.get("serviceSubnets") or ["10.96.0.0/12"],
            )
        )
        cni = net.get("cni") or {"name": "flannel"}
        if cni.get("name") == "flannel":
            # The legacy flannel ran the vxlan backend; the document requires it set.
            # BackendType/BackendPort of the legacy FlannelCNIConfig (v1alpha1_cniconfig.go).
            docs.append(_doc("KubeFlannelCNIConfig", backendType="vxlan", backendPort=4789,
                             **_pick(cni.get("flannel") or {}, "extraArgs", "kubeNetworkPoliciesEnabled")))
        elif cni.get("name") == "custom":
            # Legacy ExtraManifestURLs() served CNI URLs with extraManifestHeaders.
            docs += [_manifest(url, cluster.get("extraManifestHeaders")) for url in cni.get("urls") or []]

    providers = []
    if cluster.get("secretboxEncryptionSecret"):
        providers.append({"secretbox": {"keys": [{"name": "key2", "secret": cluster.pop("secretboxEncryptionSecret")}]}})
    if cluster.get("aescbcEncryptionSecret"):
        providers.append({"aescbc": {"keys": [{"name": "key1", "secret": cluster.pop("aescbcEncryptionSecret")}]}})
    if providers:
        providers.append({"identity": {}})
        docs.append(_doc("KubeEtcdEncryptionConfig", config={"resources": [{"resources": ["secrets"], "providers": providers}]}))

    ca = cluster.pop("ca", None) or {}
    accepted = [_pem(a.get("crt")) for a in cluster.pop("acceptedCAs", None) or []]
    if ca or accepted:
        issuing = None
        if ca.get("key"):
            issuing = {"cert": _pem(ca.get("crt")), "key": _pem(ca["key"])}
        elif ca.get("crt"):
            accepted.insert(0, _pem(ca["crt"]))
        docs.append(_doc("KubeAPIServerCAConfig", issuingCA=issuing, acceptedCAs=accepted or None))

    agg = cluster.pop("aggregatorCA", None)
    if agg and agg.get("key"):
        docs.append(_doc("KubeAggregatorCAConfig", issuingCA={"cert": _pem(agg.get("crt")), "key": _pem(agg["key"])}))

    sa = cluster.pop("serviceAccount", None)
    if sa and sa.get("key") and endpoint:
        docs.append(_doc("KubeServiceAccountConfig", issuer={"privateKey": _pem(sa["key"]), "issuerURL": endpoint}))

    docs += _api_server(node, cluster, port)
    mcp = machine.get("controlPlane") or {}
    docs += _component(cluster, mcp, "controllerManager", "KubeControllerManagerConfig",
                       node, ("extraArgs", "env", "resources"))
    docs += _component(cluster, mcp, "scheduler", "KubeSchedulerConfig",
                       node, ("extraArgs", "env", "resources", "config"))
    _drop_empty(machine, "controlPlane")
    proxy = cluster.pop("proxy", None)
    if proxy is not None:
        docs.append(
            _doc(
                "KubeProxyConfig",
                enabled=False if proxy.get("disabled") else None,
                image=proxy.get("image") or IMAGES["proxy"],
                **_pick(proxy, "mode", "extraArgs"),
            )
        )
    dns = cluster.pop("coreDNS", None)
    if dns is not None:
        docs.append(_doc("KubeCoreDNSConfig", enabled=False if dns.get("disabled") else None, image=dns.get("image")))

    if legacy_discovery:
        discovery = None
    else:
        cluster.pop("discovery", None)
    if discovery and discovery.get("enabled"):
        service = (discovery.get("registries") or {}).get("service") or {}
        if not service.get("disabled"):
            docs.append(_doc("DiscoveryServiceConfig", name="default",
                             endpoint=service.get("endpoint") or "https://discovery.talos.dev/"))

    headers = cluster.pop("extraManifestHeaders", None)
    docs += [_manifest(url, headers) for url in cluster.pop("extraManifests", None) or []]
    docs += [_doc("KubeInlineManifestConfig", name=m["name"], manifest=m.get("contents", ""))
             for m in cluster.pop("inlineManifests", None) or []]

    for key in ("allowSchedulingOnControlPlanes", "allowSchedulingOnMasters"):
        if key in cluster:
            node_cfg["allowScheduling"] = bool(cluster.pop(key)) or node_cfg.get("allowScheduling", False)

    etcd = cluster.get("etcd") or {}
    if etcd.get("subnet"):
        etcd.setdefault("advertisedSubnets", [etcd["subnet"]])
        etcd.pop("subnet")
    return docs


def _node_config(node_cfg: dict, control_plane: bool) -> list:
    if not node_cfg:
        return []
    allow = node_cfg.pop("allowScheduling", False)
    if control_plane:
        # The legacy bridge added these to control plane nodes implicitly.
        node_cfg["labels"] = {**(node_cfg.get("labels") or {}), CONTROL_PLANE_LABEL: ""}
        if not allow:
            node_cfg["taints"] = {**(node_cfg.get("taints") or {}), CONTROL_PLANE_LABEL: "NoSchedule"}
    return [_doc("KubeNodeConfig", **node_cfg)]


def _tag(image: str) -> str:
    name = image.split("@", 1)[0]
    last = name.rsplit("/", 1)[-1]
    return last.rsplit(":", 1)[1] if ":" in last else ""


def _component_images(node: str, config: dict) -> None:
    """One Kubernetes version for all component images (docs/specs/talos.md TAL-1, TAL-2).

    Once the inventory sets one component image, every component gets an
    image of that tag, so neither this module's IMAGES nor Talos' runtime
    default can mix in another version.
    """
    blocks = {key: (config.get(a) or {}).get(b) or {} for key, (a, b) in COMPONENTS.items()}
    tags = {key: _tag(block["image"]) for key, block in blocks.items() if block.get("image")}
    if not tags:
        return
    if len(set(tags.values())) > 1 or "" in tags.values():
        found = ", ".join(f"{key} {tag or '(no tag)'}" for key, tag in tags.items())
        raise ValueError(f"talos: node {node}: Kubernetes component images need one common tag: {found}")
    (tag,) = set(tags.values())
    for key, (a, b) in COMPONENTS.items():
        if key not in tags:
            block = config.setdefault(a, {}).setdefault(b, None) or {}
            block["image"] = f"{IMAGES[key].split('@', 1)[0].rsplit(':', 1)[0]}:{tag}"
            config[a][b] = block


def split(node: str, config: dict) -> list:
    """Return [v1alpha1 config, documents...] for one node config.

    *config* is the legacy v1alpha1 dict the generator built; it is changed
    in place.
    """
    config.pop("persist", None)  # deprecated: "Not supported anymore"
    _component_images(node, config)
    machine = config.setdefault("machine", {})
    cluster = config.get("cluster") or {}
    features = machine.get("features") or {}
    node_cfg: dict = {}
    control_plane = machine.get("type") in ("controlplane", "init")

    docs = _machine_docs(node, machine, features, node_cfg)
    docs += _cluster_docs(node, cluster, machine, node_cfg)
    docs += _node_config(node_cfg, control_plane)
    _drop_empty(machine, "features")
    if "cluster" in config:
        _drop_empty(config, "cluster")
    if not control_plane:
        docs = [d for d in docs if d["kind"] not in CONTROL_PLANE_KINDS]
    return [config, *docs]
