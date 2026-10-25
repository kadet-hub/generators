"""Manifest generators for Kubernetes resources."""

import logging

from kapitan.inputs.kadet import BaseObj, CompileError

from .base import Workload
from .config import ComponentConfig, ComponentSecret
from .manifests import (
    POLICY_SECTIONS,
    Manifest,
    rbac_manifests,
    policy_manifest,
)
from .networking import (
    BackendConfig,
    BackendTLSPolicy,
    Gateway,
    GatewayClass,
    GatewayRoute,
    Ingress,
    ManagedCertificate,
    NetworkPolicy,
    ReferenceGrant,
    Service,
)
from .rbac import ClusterRole, ClusterRoleBinding, Role, RoleBinding, ServiceAccount
from .scaling import HorizontalPodAutoscaler, PodDisruptionBudget, VerticalPodAutoscaler
from .storage import PersistentVolume, PersistentVolumeClaim
from .utils import get_components, inv
from .webhooks import APIService, MutatingWebhookConfiguration, ValidatingWebhookConfiguration
from .workloads import CronJob


logger = logging.getLogger(__name__)

PROMETHEUS_OPERATOR_HINT = (
    "monitoring.coreos.com resources belong in the prometheus-operator generator "
    "(generators.prometheus_operator, "
    "https://kadet-hub.org/generators/prometheus-operator/)"
)


def _generator_settings():
    """Return parameters.generators.kubernetes."""
    return inv.parameters.get("generators", {}).get("kubernetes", {})


def _default_namespace():
    """Resolve generators.kubernetes.namespace -> parameters.namespace -> default."""
    namespace = _generator_settings().get("namespace")
    # generators.kubernetes.namespace may also be a dict (Namespace labels)
    if isinstance(namespace, str) and namespace:
        return namespace
    return inv.parameters.get("namespace", "default")


def _gateway_section(key):
    """Read a Gateway API section from generators.kubernetes.<key>."""
    return _generator_settings().get(key) or {}


def _put(obj: BaseObj, key: str, value) -> None:
    """Write one output file; two resources mapping to the same file fail the compile."""
    if key in obj.root:
        raise ValueError(f"output {key!r} is produced twice; rename one of the resources")
    obj.root[key] = value


def _add_bundle(obj: BaseObj, key: str, bundle: list) -> None:
    """Add bundle to obj.root only if it has content.

    This prevents Kapitan from creating empty YAML files for optional bundles.
    """
    if bundle:
        _put(obj, key, bundle)


class GenerateMultipleObjectsForClass(BaseObj):
    """Helper to generate multiple classes.

    As a convention for generators we have that if you define only one policy/config/secret configuration
    for your component, then the name of that resource will be the component {name} itself.

    However if there are multiple objects being defined, then we call them: {name}-{object_name}

    This class helps achieve that for policies/config/secrets to avoid duplication.
    """

    def new(self):
        self.need("name")
        self.need("component")
        self.need("objects")
        self.need("generating_class")
        self.need("workload")
        self.root = []

    def body(self):
        objects = self.kwargs.objects
        name = self.kwargs.name
        component = self.kwargs.component
        generating_class = self.kwargs.generating_class
        workload = self.kwargs.workload

        for object_name, object_config in objects.items():
            if object_config is None:
                raise CompileError(
                    f"error with '{object_name}' for component {name}: configuration cannot be empty!"
                )

            if len(objects.items()) == 1:
                rendered_name = f"{name}"
            else:
                rendered_name = f"{name}-{object_name}"

            self.root += [
                generating_class(
                    name=object_name,
                    rendered_name=rendered_name,
                    config=object_config,
                    component=component,
                    workload=workload,
                )
            ]


def generate_resource_manifests(input_params):
    """Generate standalone resource manifests (secrets, configmaps, etc.).

    The ${write:...} resolver in the inventory writes data to generators.kubernetes.*
    paths, which are then processed here to generate the actual K8s manifests.
    """
    obj = BaseObj()

    def _iter_section(section_key):
        """Yield (name, namespace, spec) for each entry in a generator section."""
        section = (
            inv.parameters.get("generators", {})
            .get("kubernetes", {})
            .get(section_key, {})
        )
        for raw_name, spec in section.items():
            name = spec.get("name") or raw_name
            namespace = spec.get("namespace") or inv.parameters.get(
                "namespace", "default"
            )
            yield name, namespace, spec

    simple_sections = (
        (
            "secrets",
            "secret",
            lambda name, spec: ComponentSecret(name=name, config=spec),
        ),
        (
            "configs",
            "config",
            lambda name, spec: ComponentConfig(name=name, config=spec),
        ),
        (
            "services",
            "svc",
            lambda name, spec: Service(
                name=name, component=spec, workload=None, service_spec=spec
            ),
        ),
        (
            "service_accounts",
            "sa",
            lambda name, spec: ServiceAccount(name=name, component=spec),
        ),
        (
            "persistent_volumes",
            "pv",
            lambda name, spec: PersistentVolume(name=name, volume=spec),
        ),
    )
    for section_key, suffix, factory in simple_sections:
        for name, namespace, spec in _iter_section(section_key):
            # PersistentVolumes are cluster-scoped: no namespace directory
            prefix = "" if section_key == "persistent_volumes" else f"{namespace}/"
            _put(obj, f"{prefix}{name}-{suffix}", factory(name, spec))

    # PVCs may additionally bind a generated PV
    for name, namespace, claim in _iter_section("persistent_volume_claims"):
        persistent_volume_claim = PersistentVolumeClaim(name=name, volume_claim=claim)
        if claim.get("create_pv"):
            pv = persistent_volume_claim.bind_persistent_volume()
            _put(obj, f"{pv.root.metadata.name}-pv", pv)
        _put(obj, f"{namespace}/{name}-pvc", persistent_volume_claim)

    for name, _, _ in _iter_section("pod_monitors"):
        logger.warning(
            "generators.kubernetes.pod_monitors.%s is not rendered: %s",
            name,
            PROMETHEUS_OPERATOR_HINT,
        )

    for section, (_, _, suffix, namespaced, _) in POLICY_SECTIONS.items():
        for name, namespace, config in _iter_section(section):
            key = f"{namespace}/{name}-{suffix}" if namespaced else f"{name}-{suffix}"
            _put(
                obj,
                key,
                policy_manifest(
                    section, name, namespace if namespaced else None, config
                ),
            )

    for name, _, config in _iter_section("rbac"):
        for key, manifest in rbac_manifests(name, config):
            _put(obj, key, manifest)

    # The scope of an arbitrary kind is unknown: namespace only when set.
    for name, _, config in _iter_section("manifests"):
        namespace = config.get("namespace")
        manifest = Manifest(name=name, namespace=namespace, config=config)
        key = f"{name}-{manifest.root.kind.lower()}"
        _put(obj, f"{namespace}/{key}" if namespace else key, manifest)

    return obj


def _generate_single_ingress(obj, name, ingress_config):
    """Generate one Ingress (plus its GKE ManagedCertificate if requested)."""
    ingress = Ingress(name=name, ingress=ingress_config)

    namespace_name = ingress.root.metadata.get(
        "namespace", inv.parameters.get("namespace", "default")
    )

    if "managed_certificate" in ingress_config:
        certificate_name = ingress_config.get("managed_certificate")
        additional_domains = ingress_config.get("additional_domains", [])
        domains = [certificate_name] + additional_domains
        ingress.add_annotations(
            {"networking.gke.io/managed-certificates": certificate_name}
        )
        certificate = ManagedCertificate(
            name=certificate_name,
            domains=domains,
            namespace=ingress.root.metadata.get("namespace"),
        )
        _put(obj, f"{namespace_name}/{name}-managed-certificate", certificate)

    _put(obj, f"{namespace_name}/{name}-ingress", ingress)


def generate_ingress(input_params):
    """Generate Ingress manifests."""
    obj = BaseObj()

    for name, ingress_config in inv.parameters.get("ingresses", {}).items():
        if ingress_config.get("enabled", True):
            _generate_single_ingress(obj, name, ingress_config)

    return obj


def _collect_cross_namespace_tls_refs(listeners, gateway_namespace):
    """{namespace: secret names} of the TLS secrets the Gateway references across namespaces."""
    namespaces = {}
    for listener_config in listeners.values():
        for tls_ref in listener_config.get("tls_refs", []):
            ref_ns = tls_ref.get("namespace")
            if ref_ns and ref_ns != gateway_namespace:
                namespaces.setdefault(ref_ns, set()).add(tls_ref.get("name"))
    return namespaces


def _create_reference_grants(obj, gateway_name, gateway_namespace, target_namespaces):
    """Create one ReferenceGrant per target namespace, limited to the referenced Secrets."""
    for target_ns, names in sorted(target_namespaces.items()):
        ref_grant = ReferenceGrant(
            name=f"allow-{gateway_name}-secrets",
            from_namespace=gateway_namespace,
            from_kind="Gateway",
            to_kind="Secret",
            target_namespace=target_ns,
            to_names=sorted(names),
        )
        _put(obj, f"{target_ns}/{gateway_name}-refgrant", ref_grant)


def _expand_gateway_services(gateway_name, gateway_config):
    """
    Expand the high-level 'services' definition into listeners and routes.

    This allows a compact service definition like:
        services:
          open-webui:
            hostname: chat.${domain}
            namespace: ollama
            tls_secret: chat-example-com-tls
            cluster_issuer: letsencrypt-prod
            backend:
              name: open-webui
              port: 80

    To automatically generate:
    - An HTTPS listener for the hostname
    - An HTTP->HTTPS redirect route
    - An HTTPS backend route
    - cert-manager.io/cluster-issuer annotation (if cluster_issuer specified)
    """
    services = gateway_config.get("services", {})
    if not services:
        return gateway_config

    # Initialize listeners and routes if not present
    listeners = dict(gateway_config.get("listeners", {}))
    routes = dict(gateway_config.get("routes", {}))
    annotations = dict(gateway_config.get("annotations", {}))

    _add_cert_manager_annotations(services, annotations)

    # Reuse an HTTP listener on port 80 for the redirects, else add one
    http_listener = next(
        (
            key
            for key, listener in listeners.items()
            if listener.get("protocol") == "HTTP" and listener.get("port_number") == 80
        ),
        None,
    )
    if http_listener is None:
        http_listener = "http"
        listeners["http"] = {"port_number": 80, "protocol": "HTTP"}

    for service_name, service_config in services.items():
        hostname = service_config.get("hostname")
        namespace = service_config.get("namespace") or _default_namespace()
        http_redirect = service_config.get("http_redirect", True)
        # Route type: 'http' (default) or 'grpc'
        route_type = service_config.get("type", "http")

        # Upstream CEL rejects a Terminate listener without certificateRefs.
        if not service_config.get("tls_secret"):
            raise ValueError(
                f"gateway {gateway_name!r} service {service_name!r}: "
                "tls_secret is required for its HTTPS listener"
            )
        status_code = service_config.get("redirect_status_code", 301)
        if type(status_code) is not int or status_code not in (301, 302, 303, 307, 308):
            raise ValueError(
                f"gateway {gateway_name!r} service {service_name!r}: "
                "redirect_status_code must be 301, 302, 303, 307 or 308, "
                f"not {status_code!r}"
            )

        listener_name = f"https-{service_name}"
        listeners[listener_name] = _build_https_listener(service_config)

        # Build HTTP->HTTPS redirect route (if enabled and not gRPC)
        # gRPC clients typically don't follow HTTP redirects
        if http_redirect and route_type == "http":
            routes[f"http-{service_name}-redirect"] = _build_redirect_route(
                hostname, namespace, http_listener, status_code
            )

        routes[f"https-{service_name}-route"] = _build_backend_route(
            service_name, service_config, listener_name, hostname, namespace
        )

    # Return expanded config
    expanded = dict(gateway_config)
    expanded["listeners"] = listeners
    expanded["routes"] = routes
    expanded["annotations"] = annotations
    return expanded


def _add_cert_manager_annotations(services, annotations):
    """Collect cert-manager issuers from services and set gateway annotations.

    cert-manager supports both ClusterIssuer (cluster-scoped) and Issuer
    (namespace-scoped). ClusterIssuer takes precedence if both are specified
    (more common for shared gateways).
    """
    cluster_issuers = set()
    issuers = set()
    for service_config in services.values():
        if service_config.get("cluster_issuer"):
            cluster_issuers.add(service_config.get("cluster_issuer"))
        if service_config.get("issuer"):
            issuers.add(service_config.get("issuer"))

    # Sets iterate in hash order; pick deterministically so the same inventory
    # always compiles to the same annotation.
    if cluster_issuers:
        annotations["cert-manager.io/cluster-issuer"] = min(cluster_issuers)
    elif issuers:
        annotations["cert-manager.io/issuer"] = min(issuers)


def _build_https_listener(service_config):
    """Build the HTTPS listener for an expanded gateway service.

    NOTE: cert-manager gateway-shim requires TLS secrets to be in the same
    namespace as the Gateway. Cross-namespace references are not supported.
    The Secret will be created by cert-manager in the Gateway's namespace.
    """
    tls_refs = [
        {
            "group": "",
            "kind": "Secret",
            "name": service_config.get("tls_secret"),
            # No namespace - must be same as Gateway for cert-manager
        }
    ]

    return {
        "hostname": service_config.get("hostname"),
        "port_number": 443,
        "protocol": "HTTPS",
        "tls_mode": "Terminate",
        "tls_refs": tls_refs,
    }


def _build_redirect_route(hostname, namespace, listener, status_code):
    """Build an HTTP->HTTPS redirect route for an expanded gateway service."""
    return {
        "type": "http",
        "listener": listener,
        "namespace": namespace,
        "hostnames": [hostname],
        "rules": {
            "redirect-to-https": {
                "redirect": {
                    "scheme": "https",
                    "status_code": status_code,
                },
                "matches": {
                    "root-path": {
                        "type": "PathPrefix",
                        "value": "/",
                    }
                },
            }
        },
    }


def _build_backend_route(
    service_name, service_config, listener_name, hostname, namespace
):
    """Build the HTTPS backend route (HTTP or gRPC) for an expanded gateway service."""
    backend = service_config.get("backend", {})
    route_type = service_config.get("type", "http")
    rule = {
        "kind": backend.get("kind", "Service"),
        "name": backend.get("name"),
        "port": backend.get("port"),
        "weight": backend.get("weight", 1),
    }
    # A path prefix only applies to HTTPRoute; a GRPCRoute without matches
    # routes every method of the service.
    if route_type == "http":
        rule["matches"] = {
            "root-path": {"type": "PathPrefix", "value": backend.get("path", "/")}
        }
    return {
        "type": route_type,
        "listener": listener_name,
        "namespace": namespace,
        "hostnames": [hostname],
        "rules": {f"{service_name}-rule": rule},
    }


def _generate_gateway_classes(obj):
    """Generate GatewayClass manifests (cluster-scoped)."""
    gateway_classes = _gateway_section("gateway_classes")
    for class_name, class_config in gateway_classes.items():
        if not class_config.get("enabled", True):
            continue

        gateway_class = GatewayClass(
            name=class_name,
            controller_name=class_config.get("controller_name"),
            description=class_config.get("description"),
            parameters_ref=class_config.get("parameters_ref"),
            annotations=class_config.get("annotations", {}),
            labels=class_config.get("labels", {}),
        )
        _put(obj, f"{class_name}-gatewayclass", gateway_class)


def _generate_gateway_routes(obj, gateway, expanded_config, namespace_name):
    """Generate the routes attached to a single Gateway."""
    for route_name, route_config in expanded_config.get("routes", {}).items():
        route_namespace = route_config.get("namespace", namespace_name)

        route = GatewayRoute(
            name=route_name,
            route=route_config,
            namespace=route_namespace,
            route_type=route_config.get("type"),
            parent_refs=gateway.root.metadata.name,
            parent_namespace=namespace_name,
            available_listeners=list(expanded_config.get("listeners", {}).keys()),
        )

        _put(obj, f"{route_namespace}/{route_name}-gw-routes", route)


def _generate_single_gateway(obj, gateway_name, gateway_config):
    """Generate one Gateway plus its ReferenceGrants and routes."""
    # Expand services into listeners and routes
    expanded_config = _expand_gateway_services(gateway_name, gateway_config)

    namespace_name = gateway_config.get("namespace") or _default_namespace()
    expanded_config = _scope_listeners(expanded_config, namespace_name)
    gateway = Gateway(
        name=gateway_name, gateway=expanded_config, namespace=namespace_name
    )

    _put(obj, f"{namespace_name}/{gateway_name}-gateway", gateway)

    # Generate ReferenceGrants for cross-namespace TLS refs
    cross_ns_refs = _collect_cross_namespace_tls_refs(
        expanded_config.get("listeners", {}), namespace_name
    )
    _create_reference_grants(obj, gateway_name, namespace_name, cross_ns_refs)

    _generate_gateway_routes(obj, gateway, expanded_config, namespace_name)


def _generate_routes(obj):
    """Routes to Gateways outside the inventory, from generators.kubernetes.routes (K8S-6, K8S-7)."""
    for route_name, route_config in _gateway_section("routes").items():
        if not route_config.get("enabled", True):
            continue
        parent_refs = route_config.get("parent_refs")
        if not parent_refs or not isinstance(parent_refs, list):
            raise ValueError(f"route {route_name!r}: parent_refs needs a list of Gateways")
        route_namespace = route_config.get("namespace") or _default_namespace()
        route = GatewayRoute(
            name=route_name,
            route=route_config,
            namespace=route_namespace,
            route_type=route_config.get("type"),
            parent_refs=parent_refs,
        )
        _put(obj, f"{route_namespace}/{route_name}-route", route)


def _scope_listeners(gateway_config, gateway_namespace):
    """Default each listener's allowedRoutes to the namespaces of its routes.

    Upstream defaults to Same; All would let any namespace attach a route to
    the listener's hostnames. A listener whose routes live in other namespaces
    gets a Selector on kubernetes.io/metadata.name instead.
    """
    routes = gateway_config.get("routes", {}).values()
    listeners = {}
    for name, listener in gateway_config.get("listeners", {}).items():
        allowed = dict(listener.get("allowed_routes") or {})
        if allowed.get("selector") and not allowed.get("namespaces_from"):
            allowed["namespaces_from"] = "Selector"
        if not allowed.get("namespaces_from"):
            namespaces = {
                route.get("namespace", gateway_namespace)
                for route in routes
                if route.get("listener") in (None, name)
            }
            if namespaces - {gateway_namespace}:
                allowed["namespaces_from"] = "Selector"
                allowed["selector"] = {
                    "matchExpressions": [
                        {
                            "key": "kubernetes.io/metadata.name",
                            "operator": "In",
                            "values": sorted(namespaces),
                        }
                    ]
                }
            else:
                allowed["namespaces_from"] = "Same"
        listeners[name] = {**listener, "allowed_routes": allowed}
    return {**gateway_config, "listeners": listeners}


def _generate_backend_tls_policies(obj):
    """Generate BackendTLSPolicy manifests."""
    backend_tls_policies = _gateway_section("backend_tls_policies")
    for policy_name, policy_config in backend_tls_policies.items():
        if not policy_config.get("enabled", True):
            continue

        policy_namespace = policy_config.get("namespace") or _default_namespace()
        policy = BackendTLSPolicy(
            name=policy_name,
            namespace=policy_namespace,
            target_refs=policy_config.get("target_refs", []),
            hostname=policy_config.get("hostname"),
            ca_cert_refs=policy_config.get("ca_cert_refs"),
            well_known_ca_certs=policy_config.get("well_known_ca_certs"),
            annotations=policy_config.get("annotations", {}),
            labels=policy_config.get("labels", {}),
        )
        _put(obj, f"{policy_namespace}/{policy_name}-btlspolicy", policy)


_REFERENCE_GRANT_KEYS = (
    "from_namespace",
    "from_kind",
    "from_group",
    "to_kind",
    "to_group",
    "to_names",
)


def _generate_standalone_reference_grants(obj):
    """Generate ReferenceGrants from generators.kubernetes.reference_grants."""
    grants = _generator_settings().get("reference_grants") or {}
    for grant_name, grant_config in grants.items():
        if not grant_config.get("enabled", True):
            continue

        target_namespace = grant_config.get("target_namespace") or _default_namespace()
        # Only pass set keys so ReferenceGrant keeps its own group defaults.
        kwargs = {
            key: grant_config[key]
            for key in _REFERENCE_GRANT_KEYS
            if key in grant_config
        }
        _put(
            obj,
            f"{target_namespace}/{grant_name}-refgrant",
            ReferenceGrant(name=grant_name, target_namespace=target_namespace, **kwargs),
        )


def generate_gateway(input_params):
    """Generate Gateway API manifests including GatewayClass, Gateway, Routes, and ReferenceGrants."""
    obj = BaseObj()

    _generate_gateway_classes(obj)

    gateways = _gateway_section("gateways")
    for gateway_name, gateway_config in gateways.items():
        if gateway_config.get("enabled", True):
            _generate_single_gateway(obj, gateway_name, gateway_config)

    _generate_routes(obj)
    _generate_backend_tls_policies(obj)
    _generate_standalone_reference_grants(obj)

    return obj


def _build_scaling_bundle(name, component, workload_spec):
    """Build VPA / PDB / HPA manifests for a component."""
    bundle = []
    if (
        component.get("vpa")
        and inv.parameters.get("enable_vpa", True)
        and component.get("type") != "job"
    ):
        bundle += [
            VerticalPodAutoscaler(
                name=name, component=component, workload=workload_spec
            ).root
        ]

    # PodDisruptionBudget only makes sense for long-running workloads
    if component.get("type") != "job" and (
        component.get("pdb_min_available") or component.get("auto_pdb")
    ):
        bundle += [
            PodDisruptionBudget(
                name=name, component=component, workload=workload_spec
            ).root
        ]

    if component.get("hpa"):
        bundle += [
            HorizontalPodAutoscaler(
                name=name, component=component, workload=workload_spec
            ).root
        ]
    return bundle


# Keys whose APIs are gone upstream; the compile fails with the replacement.
REMOVED_SECURITY_KEYS = {
    "security": "use security_context (allowPrivilegeEscalation, runAsUser)",
    "pod_security_policy": (
        "policy/v1beta1 PodSecurityPolicy was removed in Kubernetes 1.25; use Pod "
        "Security Admission namespace labels or security_profile"
    ),
    "istio_policy": (
        "authentication.istio.io/v1alpha1 Policy was removed in Istio 1.6; render "
        "PeerAuthentication or RequestAuthentication through "
        "generators.kubernetes.manifests"
    ),
}


def _build_security_bundle(name, component, workload_spec):
    """Build NetworkPolicy manifests for a component."""
    for key, hint in REMOVED_SECURITY_KEYS.items():
        if key in component:
            raise ValueError(f"{name}: {key} is not supported: {hint}")
    bundle = []
    if component.get("network_policies"):
        bundle += GenerateMultipleObjectsForClass(
            name=name,
            component=component,
            generating_class=NetworkPolicy,
            objects=component.get("network_policies"),
            workload=workload_spec,
        ).root
    return bundle


def _build_service_bundle(name, component, workload_spec):
    """Build Service manifests (primary + additional) for a component."""
    bundle = []
    # An empty mapping is a Service with the API defaults (K8S-1).
    if component.get("service") is not None:
        bundle += [
            Service(
                name=name,
                component=component,
                workload=workload_spec,
                service_spec=component.get("service"),
            ).root
        ]
    if component.get("additional_services"):
        for service_name, service_spec in component.get("additional_services").items():
            bundle += [
                Service(
                    name=service_name,
                    component=component,
                    workload=workload_spec,
                    service_spec=service_spec,
                ).root
            ]
    return bundle


def _build_workload_extras(name, component, workload_spec):
    """Build webhook / backend-config manifests for the workload bundle."""
    bundle = []
    if component.get("webhooks"):
        bundle += [MutatingWebhookConfiguration(name=name, component=component).root]
    if component.get("validating_webhooks"):
        bundle += [ValidatingWebhookConfiguration(name=name, component=component).root]
    if component.get("api_service"):
        bundle += [APIService(name=name, component=component, workload=workload_spec).root]
    for key in ("service_monitors", "prometheus_rules"):
        if component.get(key):
            logger.warning(
                "%s: %s is not rendered: %s", name, key, PROMETHEUS_OPERATOR_HINT
            )
    if component.get("backend_config"):
        bundle += [BackendConfig(name=name, component=component).root]
    return bundle


def _build_rbac_bundle(name, component):
    """Build Role / ClusterRole (+bindings) / ServiceAccount manifests."""
    bundle = []
    if component.get("role"):
        bundle += [Role(name=name, component=component).root]
        bundle += [RoleBinding(name=name, component=component).root]
    if component.get("cluster_role"):
        bundle += [ClusterRole(name=name, component=component).root]
        bundle += [ClusterRoleBinding(name=name, component=component).root]
    if component.get("service_account", {}).get("create", False):
        sa_name = component.get("service_account", {}).get("name", name)
        bundle += [ServiceAccount(name=sa_name, component=component).root]
    return bundle


def _build_volume_bundle(component):
    """Build PersistentVolume / PersistentVolumeClaim manifests."""
    bundle = []
    if component.get("persistent_volumes"):
        for pv_name, volume in component.get("persistent_volumes").items():
            bundle.append(
                PersistentVolume(name=pv_name, volume=volume, component=component).root
            )
    if component.get("persistent_volume_claims"):
        for pvc_name, claim in component.get("persistent_volume_claims").items():
            pvc_name = claim.get("name", pvc_name)
            persistent_volume_claim = PersistentVolumeClaim(
                name=pvc_name, volume_claim=claim, component=component
            )
            if claim.get("create_pv"):
                bundle.append(persistent_volume_claim.bind_persistent_volume())
            bundle.append(persistent_volume_claim)
    return bundle


def _workload_suffix(component):
    """Return the Kubernetes shortname suffix for the component's workload type."""
    if component.get("schedule"):
        return "cj"  # CronJob
    if component.get("type") == "statefulset":
        return "sts"
    if component.get("type") == "daemonset":
        return "ds"
    if component.get("type") == "job":
        return "job"
    return "deploy"  # Default to Deployment


def generate_component_manifests(input_params):
    """Generate component-based manifests."""
    obj = BaseObj()
    for name, component in get_components():
        namespace_name = component.get(
            "namespace", inv.parameters.get("namespace", "default")
        )

        workload = Workload(name=name, component=component)
        if component.get("schedule"):
            workload = CronJob(name=name, component=component, job=workload)
        workload_spec = workload.root

        configs = GenerateMultipleObjectsForClass(
            name=name,
            component=component,
            generating_class=ComponentConfig,
            objects=component.get("config_maps", {}),
            workload=workload_spec,
        )
        secrets = GenerateMultipleObjectsForClass(
            name=name,
            component=component,
            generating_class=ComponentSecret,
            objects=component.get("secrets", {}),
            workload=workload_spec,
        )
        workload.add_volumes_for_objects(configs)
        workload.add_volumes_for_objects(secrets)

        bundle_workload = [workload_spec]
        bundle_workload += _build_workload_extras(name, component, workload_spec)

        # Workloads are always written (every component must have at least one)
        _put(obj, f"{namespace_name}/{name}-{_workload_suffix(component)}", bundle_workload)

        # Optional bundles are only written if they have content
        # Using Kubernetes shortnames where applicable (cm, svc, vol)
        _add_bundle(obj, f"{namespace_name}/{name}-cm", list(configs.root))
        _add_bundle(obj, f"{namespace_name}/{name}-secret", list(secrets.root))
        _add_bundle(
            obj,
            f"{namespace_name}/{name}-svc",
            _build_service_bundle(name, component, workload_spec),
        )
        _add_bundle(
            obj, f"{namespace_name}/{name}-rbac", _build_rbac_bundle(name, component)
        )
        _add_bundle(
            obj,
            f"{namespace_name}/{name}-scaling",
            _build_scaling_bundle(name, component, workload_spec),
        )
        _add_bundle(
            obj,
            f"{namespace_name}/{name}-security",
            _build_security_bundle(name, component, workload_spec),
        )
        _add_bundle(
            obj, f"{namespace_name}/{name}-vol", _build_volume_bundle(component)
        )

    return obj


def _ready_status(workload, component):
    """The status of a ready workload as a Chainsaw assertion tree."""
    spec = workload.spec
    replicas = spec.get("replicas")
    if workload.kind == "Deployment":
        # With an HPA the workload has no replicas to compare with.
        if replicas is None:
            return {"(conditions[?type == 'Available'])": [{"status": "True"}]}
        return {"availableReplicas": replicas}
    if workload.kind == "StatefulSet":
        # The HPA scales the StatefulSet up to min_replicas after its creation.
        if replicas is None:
            minimum = component.get("hpa", {}).get("min_replicas") or 1
            return {f"(readyReplicas >= `{minimum}`)": True}
        return {"readyReplicas": replicas}
    if workload.kind == "DaemonSet":
        # Both counts are 0 until the controller has seen the DaemonSet, which
        # sets observedGeneration.
        return {"(observedGeneration > `0` && numberReady == desiredNumberScheduled)": True}
    return {"succeeded": spec.completions}


def generate_chainsaw_asserts(input_params):
    """One Chainsaw StepTemplate per component that asserts its workload is ready.

    A CronJob gets none: it starts no pod before its schedule.
    """
    obj = BaseObj()
    for name, component in get_components():
        if component.get("schedule"):
            continue
        namespace_name = component.get(
            "namespace", inv.parameters.get("namespace", "default")
        )
        workload = Workload(name=name, component=component).root
        resource = {
            "apiVersion": workload.apiVersion,
            "kind": workload.kind,
            "metadata": {
                k: workload.metadata[k] for k in ("name", "namespace") if k in workload.metadata
            },
            "status": _ready_status(workload, component),
        }
        _put(
            obj,
            f"{namespace_name}/{name}-assert",
            {
                "apiVersion": "chainsaw.kyverno.io/v1alpha1",
                "kind": "StepTemplate",
                "metadata": {"name": name},
                "spec": {"try": [{"assert": {"resource": resource}}]},
            },
        )
    return obj


def generate_manifests(input_params):
    """Generate all manifests."""
    all_manifests = BaseObj()

    resource_manifests = generate_resource_manifests(input_params)
    component_manifests = generate_component_manifests(input_params)
    ingress_manifests = generate_ingress(input_params)
    gateway_manifests = generate_gateway(input_params)

    for manifests in (
        component_manifests,
        ingress_manifests,
        gateway_manifests,
        resource_manifests,
    ):
        for key, value in manifests.root.items():
            _put(all_manifests, key, value)

    return all_manifests


def main(input_params):
    """Main entry point for manifest generation."""
    from .utils import generate_docs

    whitelisted_functions = [
        "generate_manifests",
        "generate_docs",
        "generate_chainsaw_asserts",
    ]
    function = input_params.get("function", "generate_manifests")
    if function not in whitelisted_functions:
        raise ValueError(
            f"Unknown function {function!r}; valid values: {whitelisted_functions}"
        )
    if function == "generate_docs":
        return generate_docs(input_params)
    return globals()[function](input_params)
