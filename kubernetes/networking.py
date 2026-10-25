"""Kubernetes networking resources: Service, Ingress, NetworkPolicy, Gateway API resources.

Gateway API resources include:
- Gateway, GatewayClass: Core gateway infrastructure
- HTTPRoute, GRPCRoute: Layer 7 routing (v1)
- TCPRoute, UDPRoute: Layer 4 routing (v1)
- TLSRoute: TLS passthrough routing (v1)
- ReferenceGrant: Cross-namespace references (v1beta1, the storage version)
- BackendTLSPolicy: Backend TLS configuration (v1)

GKE resources: ManagedCertificate, BackendConfig.
"""

import logging

from . import k8s
from .utils import get_namespace, pod_labels


logger = logging.getLogger(__name__)


class NetworkPolicy(k8s.Base):
    """Kubernetes NetworkPolicy resource."""

    def new(self):
        self.need("config")
        self.need("workload")
        self.kwargs.apiVersion = "networking.k8s.io/v1"
        self.kwargs.kind = "NetworkPolicy"
        super().new()

    def body(self):
        super().body()
        policy = self.kwargs.config
        workload = self.kwargs.workload
        namespace = get_namespace(policy)
        if namespace:
            self.add_namespace(namespace)
        self.root.spec.podSelector.matchLabels = policy.get(
            "pod_selector", pod_labels(workload)
        )
        # Only set ingress/egress if they are non-empty (must be array or null, not empty dict)
        ingress = policy.get("ingress")
        egress = policy.get("egress")
        if ingress:
            self.root.spec.ingress = ingress
        if egress:
            self.root.spec.egress = egress
        self.root.spec.policyTypes = []
        # Check original policy config for policy_types or infer from ingress/egress presence
        if policy.get("policy_types"):
            self.root.spec.policyTypes = policy.get("policy_types")
        else:
            if ingress is not None:  # Explicitly set (even if empty list)
                self.root.spec.policyTypes += ["Ingress"]
            if egress is not None:  # Explicitly set (even if empty list)
                self.root.spec.policyTypes += ["Egress"]


class Service(k8s.Base):
    """Kubernetes Service resource.

    A standalone Service (generators.kubernetes.services) has no workload: its
    entry is both component and service_spec, the selector is given and a
    port's container_port is its targetPort.
    """

    def new(self):
        self.need("component")
        self.need("workload")
        self.need("service_spec")
        self.kwargs.apiVersion = "v1"
        self.kwargs.kind = "Service"
        super().new()

    def body(self):
        component = self.kwargs.component
        workload = self.kwargs.workload
        service_spec = self.kwargs.service_spec

        self.kwargs.name = service_spec.get("service_name", self.kwargs.name)
        super().body()
        namespace = get_namespace(component)
        if namespace:
            self.add_namespace(namespace)

        self.add_labels(component.get("labels", {}))
        self.add_annotations(service_spec.get("annotations", {}))
        name = self.root.metadata.name
        # external_name makes an ExternalName Service; the type follows from it.
        external_name = service_spec.get("external_name")
        if external_name:
            if service_spec.get("type", "ExternalName") != "ExternalName":
                raise ValueError(
                    f"service {name!r}: external_name needs type ExternalName, "
                    f"not {service_spec.get('type')}"
                )
            if service_spec.get("headless"):
                raise ValueError(f"service {name!r}: external_name and headless exclude each other")
            service_spec = {**service_spec, "type": "ExternalName"}
            self.root.spec.externalName = external_name
        elif service_spec.get("type") == "ExternalName":
            raise ValueError(f"service {name!r}: type ExternalName needs external_name")
        if workload is None:
            # Only a headless or ExternalName Service may go without a
            # selector: its endpoints are managed elsewhere or it has none.
            selector = service_spec.get("selector")
            if not selector and not service_spec.get("headless") and not external_name:
                raise ValueError(f"service {name!r}: selector is required unless headless or external_name")
            if selector:
                self.root.spec.selector = dict(selector)
        else:
            self.root.spec.selector = dict(pod_labels(workload))
            self.root.spec.selector.update(service_spec.get("selectors", {}))
        # Only set type when configured; Kubernetes defaults to ClusterIP
        if service_spec.get("type"):
            self.root.spec.type = service_spec.get("type")
        if service_spec.get("publish_not_ready_address", False):
            self.root.spec.publishNotReadyAddresses = True
        if service_spec.get("headless", False):
            # The API rejects clusterIP None on the other types.
            if (service_spec.get("type") or "ClusterIP") != "ClusterIP":
                raise ValueError(
                    f"service {name!r}: headless needs type ClusterIP, "
                    f"not {service_spec.get('type')}"
                )
            self.root.spec.clusterIP = "None"
        self.root.spec.sessionAffinity = service_spec.get("session_affinity", "None")
        self.root.spec.ports = self._build_service_ports(
            self._collect_component_ports(component), service_spec
        )
        # The API requires ports except for ExternalName and headless Services.
        if not self.root.spec.ports:
            if service_spec.get("type") == "ExternalName" or service_spec.get("headless"):
                del self.root.spec["ports"]
            else:
                raise ValueError(
                    f"service {name!r}: no port has a service_port "
                    "(or expose_ports matches none)"
                )

    def _collect_component_ports(self, component):
        """Merge main + additional container ports into a fresh dict.

        A fresh dict so the shared component config is never mutated in place.
        """
        all_ports = {}
        if component.get("ports"):
            all_ports.update(component.get("ports"))
        for container in component.get("additional_containers", {}).values():
            if container.get("ports"):
                all_ports.update(container.get("ports"))
        return all_ports

    def _build_service_ports(self, all_ports, service_spec):
        """Build the spec.ports list from container ports with a service_port."""
        service_ports = []
        for port_name, ports in all_ports.items():
            expose_ports = service_spec.get("expose_ports")
            if expose_ports and port_name not in expose_ports:
                continue
            if "service_port" in ports:
                # A component's container port carries the port name; a
                # standalone Service has no container to name it.
                target_port = port_name
                if self.kwargs.workload is None:
                    target_port = ports.get("container_port", ports.get("service_port"))
                service_port = {
                    "name": port_name,
                    "port": ports.get("service_port"),
                    "targetPort": target_port,
                    "protocol": ports.get("protocol", "TCP"),
                }
                app_protocol = ports.get("app_protocol", APP_PROTOCOLS.get(port_name))
                if app_protocol:
                    service_port["appProtocol"] = app_protocol
                service_ports += [service_port]
        return service_ports


# Port names that say the protocol: IANA service names as they are, the others
# as the Kubernetes-defined appProtocol values.
APP_PROTOCOLS = {
    "http": "http",
    "https": "https",
    "h2c": "kubernetes.io/h2c",
    "ws": "kubernetes.io/ws",
    "wss": "kubernetes.io/wss",
}


class Ingress(k8s.Base):
    """Kubernetes Ingress resource."""

    def new(self):
        self.need("name")
        self.need("ingress")
        self.kwargs.apiVersion = "networking.k8s.io/v1"
        self.kwargs.kind = "Ingress"
        super().new()

    def body(self):
        super().body()
        ingress = self.kwargs.ingress
        namespace = get_namespace(ingress)
        if namespace:
            self.add_namespace(namespace)
        self.add_annotations(ingress.get("annotations", {}))
        self.add_labels(ingress.get("labels", {}))
        if "default_backend" in ingress:
            self._set_default_backend(ingress.get("default_backend"))
        self.root.spec.rules = [
            self._build_rule(host) for host in ingress.get("hosts", [])
        ]
        if ingress.get("tls"):
            self.root.spec.tls = ingress.get("tls")
        if ingress.get("ingress_class"):
            self.root.spec.ingressClassName = ingress.get("ingress_class")

    def _set_default_backend(self, default_backend):
        """Set spec.defaultBackend in the networking.k8s.io/v1 shape.

        v1 shape: defaultBackend.service.port.{number|name}
        """
        self.root.spec.defaultBackend.service.name = default_backend.get("name")
        port = default_backend.get("port", 80)
        if isinstance(port, int):
            self.root.spec.defaultBackend.service.port.number = port
        else:
            self.root.spec.defaultBackend.service.port.name = port

    def _build_rule(self, host):
        """Build one spec.rules entry for a host."""
        paths = [self._build_path(path) for path in host.get("paths", [])]
        return {"host": host.get("name"), "http": {"paths": paths}}

    def _build_path(self, path):
        """Build one HTTP path entry with its backend service port."""
        port_name = path.get("port_name")
        port_number = path.get("port_number")
        # raise error if both or no options are specified (not x-or)
        if (not port_name) == (not port_number):
            raise ValueError("ingress: path needs port_name OR port_number")
        port = {"name": port_name} if port_name else {"number": port_number}
        return {
            "backend": {
                "service": {
                    "name": path.get("backend_name"),
                    "port": port,
                }
            },
            "path": path.get("path"),
            "pathType": path.get("path_type", "ImplementationSpecific"),
        }


class GatewayClass(k8s.Base):
    """Kubernetes Gateway API GatewayClass resource.

    Defines a class of Gateways with shared behavior and configuration.
    Typically created by infrastructure providers (Istio, Envoy, etc.).

    Required kwargs:
        name: GatewayClass name (e.g., 'istio', 'envoy-gateway')
        controller_name: Controller implementation name (e.g., 'istio.io/gateway-controller')

    Optional kwargs:
        description: Human-readable description
        parameters_ref: Reference to implementation-specific parameters
    """

    def new(self):
        self.need("name")
        self.need("controller_name")
        self.kwargs.apiVersion = "gateway.networking.k8s.io/v1"
        self.kwargs.kind = "GatewayClass"
        super().new()

    def body(self):
        super().body()
        # GatewayClass is cluster-scoped, no namespace

        self.add_annotations(self.kwargs.get("annotations", {}))
        self.add_labels(self.kwargs.get("labels", {}))

        self.root.spec.controllerName = self.kwargs.controller_name

        if self.kwargs.get("description"):
            self.root.spec.description = self.kwargs.description

        # ParametersRef for implementation-specific configuration
        if self.kwargs.get("parameters_ref"):
            params = self.kwargs.parameters_ref
            self.root.spec.parametersRef = {
                "group": params.get("group", ""),
                "kind": params.get("kind"),
                "name": params.get("name"),
            }
            if params.get("namespace"):
                self.root.spec.parametersRef["namespace"] = params.get("namespace")


class Gateway(k8s.Base):
    """Kubernetes Gateway API Gateway resource."""

    def new(self):
        self.need("name")
        self.need("gateway")
        self.kwargs.apiVersion = "gateway.networking.k8s.io/v1"
        self.kwargs.kind = "Gateway"
        super().new()

    def body(self):
        super().body()
        gateway = self.kwargs.gateway

        namespace = self.kwargs.get("namespace") or get_namespace(gateway)
        if namespace:
            self.add_namespace(namespace)
        self.add_annotations(gateway.get("annotations", {}))
        self.add_labels(gateway.get("labels", {}))

        # Only set addresses when configured; most gateways get addresses assigned
        # by the controller.
        if gateway.get("address"):
            self.root.spec.addresses = [
                {"type": "IPAddress", "value": gateway.get("address")}
            ]
        self.root.spec.listeners = [
            self._build_listener(name, config)
            for name, config in gateway.get("listeners", {}).items()
        ]

        if gateway.get("gateway_class"):
            self.root.spec.gatewayClassName = gateway.get("gateway_class")
        if gateway.get("infrastructure_labels"):
            self.root.spec.infrastructure.labels = gateway.get("infrastructure_labels")

    def _build_listener(self, name, listener):
        """Build a single listener configuration."""
        allowed_routes = listener.get("allowed_routes") or {}
        namespaces = {"from": allowed_routes.get("namespaces_from", "Same")}
        if allowed_routes.get("selector"):
            namespaces["selector"] = allowed_routes.get("selector")
        config = {
            "name": name,
            "port": listener.get("port_number"),
            "protocol": listener.get("protocol"),
            "allowedRoutes": {"namespaces": namespaces},
        }
        if allowed_routes.get("kinds"):
            config["allowedRoutes"]["kinds"] = allowed_routes.get("kinds")

        if listener.get("hostname"):
            config["hostname"] = listener.get("hostname")

        # Upstream CEL rejects a Terminate listener without certificateRefs.
        if listener.get("tls_mode") == "Terminate" and not listener.get("tls_refs"):
            raise ValueError(
                f"gateway {self.kwargs.name!r} listener {name!r}: "
                "tls_mode Terminate requires tls_refs"
            )
        if listener.get("tls_mode") or listener.get("tls_refs"):
            config["tls"] = {
                "mode": listener.get("tls_mode", "Terminate"),
                "certificateRefs": listener.get("tls_refs", []),
            }

        return config


class GatewayRoute(k8s.Base):
    """Kubernetes Gateway API Route resource.

    Supports HTTPRoute, GRPCRoute, TCPRoute, UDPRoute and TLSRoute (v1).

    Required kwargs:
        name: Route name
        route: Route configuration dict
        route_type: One of 'http', 'grpc', 'tcp', 'tls', 'udp'
        parent_refs: Gateway name to attach to, or a list of parent_refs
            entries (name, namespace, section_name, port) of a routes entry

    Optional kwargs:
        namespace: Route namespace
        parent_namespace: Gateway namespace (for cross-namespace)
        available_listeners: List of listener names for validation
    """

    # Route type to Kind mapping
    ROUTE_KINDS = {
        "http": "HTTPRoute",
        "grpc": "GRPCRoute",
        "tcp": "TCPRoute",
        "tls": "TLSRoute",
        "udp": "UDPRoute",
    }

    def new(self):
        self.need("name")
        self.need("route")
        self.need("route_type")
        self.need("parent_refs")

        # Gateway API v1.6 serves every route kind as v1 (storage version);
        # the v1alpha2/v1alpha3 route versions are deprecated or unserved.
        self.kwargs.apiVersion = "gateway.networking.k8s.io/v1"
        api_version = self.kwargs.route.get("api_version")
        if api_version:
            self.kwargs.apiVersion = f"gateway.networking.k8s.io/{api_version}"
        self.kwargs.kind = self.ROUTE_KINDS.get(self.kwargs.route_type, "HTTPRoute")
        super().new()

    def body(self):
        super().body()
        route = self.kwargs.route

        namespace = self.kwargs.namespace or get_namespace(route)
        if namespace:
            self.add_namespace(namespace)
        self.add_annotations(route.get("annotations", {}))
        self.add_labels(route.get("labels", {}))

        # TCPRoute and UDPRoute have no hostnames upstream.
        if self.kwargs.route_type not in ("tcp", "udp"):
            self.root.spec.hostnames = route.get("hostnames", [])

        if isinstance(self.kwargs.parent_refs, str):
            self.root.spec.parentRefs = [self._gateway_parent_ref(namespace)]
        else:
            self.root.spec.parentRefs = [
                self._explicit_parent_ref(ref) for ref in self.kwargs.parent_refs
            ]

        self.root.spec.rules = [
            self._build_rule(rule) for rule in route.get("rules", {}).values()
        ]

    def _gateway_parent_ref(self, namespace):
        """parentRef to the Gateway this route is rendered with, sectionName from its listener."""
        parent_ref = {"name": self.kwargs.parent_refs}

        # Add namespace to parentRef if gateway is in a different namespace
        parent_namespace = self.kwargs.get("parent_namespace")
        if parent_namespace and parent_namespace != namespace:
            parent_ref["namespace"] = parent_namespace

        listener_name = self._resolve_listener(self.kwargs.route.get("listener"))
        if listener_name:
            parent_ref["sectionName"] = listener_name
        return parent_ref

    def _explicit_parent_ref(self, ref):
        """parentRef from a parent_refs entry of generators.kubernetes.routes (K8S-6)."""
        if not (ref or {}).get("name"):
            raise ValueError(f"route {self.kwargs.name!r}: every parent_refs entry needs a name")
        keys = {"name": "name", "namespace": "namespace", "section_name": "sectionName", "port": "port"}
        return {api: ref[key] for key, api in keys.items() if ref.get(key) is not None}

    def _resolve_listener(self, listener_ref):
        """
        Resolve the listener reference to an actual listener name.

        If the listener_ref matches an available listener key, use it directly.
        This allows routes to reference listeners by their YAML key name,
        automatically binding to the correct Gateway listener.

        Returns None if no listener is specified, otherwise returns the resolved name.
        """
        if not listener_ref:
            return None

        available_listeners = getattr(self.kwargs, "available_listeners", [])

        # Direct match - listener_ref is already a valid listener key
        if listener_ref in available_listeners:
            return listener_ref

        # Warn if listener not found but was specified
        if available_listeners:
            logger.warning(
                "listener '%s' not found in available listeners: %s",
                listener_ref,
                available_listeners,
            )

        # Return the original value (for backwards compatibility)
        return listener_ref

    def _build_rule(self, rule):
        """Build a single route rule configuration."""
        result = {}
        # L4 and TLS route rules have no matches upstream.
        if self.kwargs.route_type in (None, "http", "grpc"):
            result["matches"] = self._build_matches(rule.get("matches", {}))

        # Check if this is a redirect rule (no backendRefs for redirects)
        if rule.get("redirect"):
            result["filters"] = [self._build_redirect_filter(rule.get("redirect"))]
        else:
            result["backendRefs"] = [self._build_backend_ref(rule)]

        return result

    def _build_redirect_filter(self, redirect_config):
        """Build a redirect filter configuration."""
        filter_config = {"type": "RequestRedirect", "requestRedirect": {}}

        if redirect_config.get("scheme"):
            filter_config["requestRedirect"]["scheme"] = redirect_config.get("scheme")
        if redirect_config.get("port"):
            filter_config["requestRedirect"]["port"] = redirect_config.get("port")
        if redirect_config.get("status_code"):
            filter_config["requestRedirect"]["statusCode"] = redirect_config.get(
                "status_code"
            )

        # K8S-8: the path part of the redirect, Extended support (HTTPRoutePathRedirect).
        full = redirect_config.get("replace_full_path")
        prefix = redirect_config.get("replace_prefix_match")
        if full is not None and prefix is not None:
            raise ValueError(
                f"route {self.kwargs.name!r}: a redirect takes replace_full_path "
                "or replace_prefix_match, not both"
            )
        if full is not None:
            filter_config["requestRedirect"]["path"] = {
                "type": "ReplaceFullPath",
                "replaceFullPath": full,
            }
        elif prefix is not None:
            filter_config["requestRedirect"]["path"] = {
                "type": "ReplacePrefixMatch",
                "replacePrefixMatch": prefix,
            }

        return filter_config

    def _build_matches(self, matches):
        """Build match configurations for a rule."""
        if self.kwargs.route_type == "grpc":
            # GRPCRoute matches on gRPC service and method, not on a path.
            return [
                {
                    "method": {
                        key: match[key]
                        for key in ("type", "service", "method")
                        if key in match
                    }
                }
                for match in matches.values()
            ]
        return [
            {
                "path": {
                    "type": match.get("type", "PathPrefix"),
                    "value": match.get("value", "/"),
                }
            }
            for match in matches.values()
        ]

    def _build_backend_ref(self, rule):
        """Build a backend reference from rule configuration."""
        ref = {
            "group": rule.get("group", ""),
            "kind": rule.get("kind", "Service"),
            "name": rule.get("name"),
            "port": rule.get("port"),
            "weight": rule.get("weight", 1),
        }
        # Add namespace for cross-namespace backend references
        if rule.get("namespace"):
            ref["namespace"] = rule.get("namespace")
        return ref


class ManagedCertificate(k8s.Base):
    """GKE ManagedCertificate resource."""

    def new(self):
        self.need("name")
        self.need("domains")
        # v1 has been GA since 2020; v1beta1/v1beta2 were removed from GKE
        self.kwargs.apiVersion = "networking.gke.io/v1"
        self.kwargs.kind = "ManagedCertificate"
        super().new()

    def body(self):
        super().body()
        _name = self.kwargs.name
        domains = self.kwargs.domains
        # Same namespace as the Ingress: the annotation does not cross namespaces.
        namespace = self.kwargs.get("namespace") or get_namespace()
        if namespace:
            self.add_namespace(namespace)
        self.root.spec.domains = domains


class ReferenceGrant(k8s.Base):
    """
    Kubernetes Gateway API ReferenceGrant resource.

    Allows cross-namespace references for Gateway API resources.
    Used to permit Gateways to reference Secrets in other namespaces for TLS,
    or HTTPRoutes to reference Services in other namespaces.
    """

    def new(self):
        self.need("name")
        self.need("from_namespace")
        self.need("from_kind")
        self.need("to_kind")
        self.kwargs.apiVersion = "gateway.networking.k8s.io/v1beta1"
        self.kwargs.kind = "ReferenceGrant"
        super().new()

    def body(self):
        super().body()

        # ReferenceGrant is created in the target namespace (where the secret/service lives)
        target_namespace = self.kwargs.get("target_namespace") or get_namespace()
        if target_namespace:
            self.add_namespace(target_namespace)

        # Build the 'from' reference (who is allowed to reference)
        from_ref = {
            "group": self.kwargs.get("from_group", "gateway.networking.k8s.io"),
            "kind": self.kwargs.from_kind,
            "namespace": self.kwargs.from_namespace,
        }

        # Build the 'to' reference (what can be referenced)
        to_ref = {
            "group": self.kwargs.get("to_group", ""),
            "kind": self.kwargs.to_kind,
        }

        self.root.spec["from"] = [from_ref]
        # Optionally restrict to specific resource names: upstream `to` entries
        # carry a single `name`, so emit one entry per name.
        to_names = self.kwargs.get("to_names")
        if to_names:
            self.root.spec.to = [{**to_ref, "name": name} for name in to_names]
        else:
            self.root.spec.to = [to_ref]


class BackendTLSPolicy(k8s.Base):
    """Kubernetes Gateway API BackendTLSPolicy resource.

    Configures TLS settings for connections from gateways to backend services.
    Used for mTLS, custom CA certificates, and TLS verification settings.

    Required kwargs:
        name: Policy name
        target_refs: List of backend references (Services) to apply policy to

    Optional kwargs:
        namespace: Policy namespace
        hostname: Server name indication (SNI) for TLS handshake
        ca_cert_refs: List of references to CA certificate Secrets/ConfigMaps
        well_known_ca_certs: Use system CA certs ('System' to enable)
        annotations: Additional annotations
        labels: Additional labels

    Example config:
        {
            'target_refs': [
                {'kind': 'Service', 'name': 'backend-svc', 'namespace': 'default'}
            ],
            'hostname': 'backend.example.com',
            'ca_cert_refs': [
                {'kind': 'ConfigMap', 'name': 'backend-ca', 'group': ''}
            ],
        }
    """

    def new(self):
        self.need("name")
        self.need("target_refs")
        self.kwargs.apiVersion = "gateway.networking.k8s.io/v1"
        self.kwargs.kind = "BackendTLSPolicy"
        super().new()

    def body(self):
        super().body()

        namespace = self.kwargs.get("namespace") or get_namespace()
        if namespace:
            self.add_namespace(namespace)

        self.add_annotations(self.kwargs.get("annotations", {}))
        self.add_labels(self.kwargs.get("labels", {}))

        # Build targetRefs - which backends this policy applies to
        target_refs = []
        for ref in self.kwargs.target_refs:
            target_ref = {
                "group": ref.get("group", ""),
                "kind": ref.get("kind", "Service"),
                "name": ref.get("name"),
            }
            if ref.get("namespace"):
                target_ref["namespace"] = ref.get("namespace")
            if ref.get("sectionName"):
                target_ref["sectionName"] = ref.get("sectionName")
            target_refs.append(target_ref)

        self.root.spec.targetRefs = target_refs

        # Build validation spec
        validation = {}

        # Hostname for SNI
        if self.kwargs.get("hostname"):
            validation["hostname"] = self.kwargs.hostname

        # CA certificate references
        if self.kwargs.get("ca_cert_refs"):
            ca_refs = []
            for ref in self.kwargs.ca_cert_refs:
                ca_ref = {
                    "group": ref.get("group", ""),
                    "kind": ref.get("kind", "ConfigMap"),
                    "name": ref.get("name"),
                }
                if ref.get("namespace"):
                    ca_ref["namespace"] = ref.get("namespace")
                ca_refs.append(ca_ref)
            validation["caCertificateRefs"] = ca_refs

        # Well-known CA certs (system trust store)
        if self.kwargs.get("well_known_ca_certs"):
            validation["wellKnownCACertificates"] = self.kwargs.well_known_ca_certs

        if validation:
            self.root.spec.validation = validation


class BackendConfig(k8s.Base):
    """GKE BackendConfig resource."""

    def new(self):
        self.need("component")
        self.kwargs.apiVersion = "cloud.google.com/v1"
        self.kwargs.kind = "BackendConfig"
        super().new()

    def body(self):
        component_name = self.kwargs.name
        self.kwargs.name = f"{component_name}-backend-config"
        super().body()
        component = self.kwargs.component
        self.add_namespace(get_namespace(component, default="default"))
        self.root.spec = component.get("backend_config")
