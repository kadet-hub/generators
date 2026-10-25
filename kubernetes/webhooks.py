"""Resources through which the API server calls a component: webhook configurations and APIService."""

from . import k8s
from .networking import Service
from .rbac import cluster_scoped_name
from .utils import _convert_to_dict, get_namespace

# cert-manager's cainjector fills caBundle from any of these annotations.
CA_INJECTION = (
    "cert-manager.io/inject-ca-from",
    "cert-manager.io/inject-ca-from-secret",
    "cert-manager.io/inject-apiserver-ca",
)


def _webhooks(name, component, key):
    """The component's webhooks, checked for a CA and scoped away from their own namespace.

    The API server verifies a service webhook's serving certificate against
    clientConfig.caBundle; without one every call fails, which blocks the
    matched requests unless failurePolicy is Ignore (the default is Fail).
    """
    annotations = component.get("webhook_annotations") or {}
    webhooks = _convert_to_dict(component.get(key)) or []
    namespace = get_namespace(component, default="default")
    service = (component.get("service") or {}).get("service_name", name)
    for webhook in webhooks:
        # The only AdmissionReview version and the side-effect class a webhook
        # written today declares; both fields are required by the API.
        webhook.setdefault("admissionReviewVersions", ["v1"])
        webhook.setdefault("sideEffects", "None")
        client = webhook.setdefault("clientConfig", {})
        # A component's webhook is served by the component's own Service.
        if "url" not in client:
            client["service"] = {"name": service, "namespace": namespace, **(client.get("service") or {})}
        if (
            webhook.get("failurePolicy", "Fail") == "Fail"
            and "service" in client
            and not client.get("caBundle")
            and not any(a in annotations for a in CA_INJECTION)
            # K8S-9: the webhook's server, such as an operator, writes the CA itself.
            and not component.get("webhook_ca_injected")
        ):
            raise ValueError(
                f"{name}: webhook {webhook.get('name')!r} has failurePolicy Fail "
                f"but no clientConfig.caBundle; set it, one of the webhook_annotations "
                f"{', '.join(CA_INJECTION)}, or webhook_ca_injected: true when the "
                f"webhook's server writes the CA itself"
            )
        # The webhook must not intercept the namespace that runs its own server.
        own = (client.get("service") or {}).get("namespace") or get_namespace(
            component, default="default"
        )
        webhook.setdefault(
            "namespaceSelector",
            {
                "matchExpressions": [
                    {
                        "key": "kubernetes.io/metadata.name",
                        "operator": "NotIn",
                        "values": [own],
                    }
                ]
            },
        )
    return annotations, webhooks


class MutatingWebhookConfiguration(k8s.Base):
    """Kubernetes MutatingWebhookConfiguration resource."""

    def new(self):
        self.need("component")
        self.kwargs.apiVersion = "admissionregistration.k8s.io/v1"
        self.kwargs.kind = "MutatingWebhookConfiguration"
        self.kwargs.rendered_name = cluster_scoped_name(self.kwargs.component)
        super().new()

    def body(self):
        super().body()
        annotations, self.root.webhooks = _webhooks(
            self.kwargs.name, self.kwargs.component, "webhooks"
        )
        self.add_annotations(annotations)


class ValidatingWebhookConfiguration(k8s.Base):
    """Kubernetes ValidatingWebhookConfiguration resource."""

    def new(self):
        self.need("component")
        self.kwargs.apiVersion = "admissionregistration.k8s.io/v1"
        self.kwargs.kind = "ValidatingWebhookConfiguration"
        self.kwargs.rendered_name = cluster_scoped_name(self.kwargs.component)
        super().new()

    def body(self):
        super().body()
        annotations, self.root.webhooks = _webhooks(
            self.kwargs.name, self.kwargs.component, "validating_webhooks"
        )
        self.add_annotations(annotations)


class APIService(k8s.Base):
    """Kubernetes APIService that serves an aggregated API from the component's Service."""

    def new(self):
        self.need("component")
        self.need("workload")
        api = self.kwargs.component.get("api_service")
        self.kwargs.apiVersion = "apiregistration.k8s.io/v1"
        self.kwargs.kind = "APIService"
        # The API requires the name <version>.<group>.
        self.kwargs.rendered_name = f"{api.get('version')}.{api.get('group')}"
        super().new()

    def body(self):
        name, component = self.kwargs.name, self.kwargs.component
        api = component.get("api_service")
        if not (api.get("group") and api.get("version") and component.get("service") is not None):
            raise ValueError(
                f"{name}: api_service needs group, version and the component's service"
            )
        super().body()
        annotations = api.get("annotations") or {}
        self.add_annotations(annotations)
        # The API server verifies the Service's certificate against caBundle,
        # and rejects insecureSkipTLSVerify together with a caBundle.
        has_ca = bool(api.get("ca_bundle")) or any(a in annotations for a in CA_INJECTION)
        if has_ca == bool(api.get("insecure_skip_tls_verify")):
            raise ValueError(
                f"{name}: api_service needs either ca_bundle or one of the annotations "
                f"{', '.join(CA_INJECTION)}, or insecure_skip_tls_verify: true, not both"
            )
        service = Service(
            name=name,
            component=component,
            workload=self.kwargs.workload,
            service_spec=component.get("service"),
        ).root
        port = api.get("port")
        if port is None:
            ports = [p for p in service.spec.ports if p["name"] == "https"] or service.spec.ports
            if len(ports) != 1:
                raise ValueError(
                    f"{name}: api_service cannot pick a Service port: none is named https "
                    f"and the Service has {len(ports)}; set api_service.port"
                )
            port = ports[0]["port"]
        spec = self.root.spec
        spec.group = api.get("group")
        spec.version = api.get("version")
        # Required, without an API default; metrics-server, prometheus-adapter
        # and KEDA register with 100 and 100.
        spec.groupPriorityMinimum = api.get("group_priority_minimum", 100)
        spec.versionPriority = api.get("version_priority", 100)
        spec.service = {
            "name": service.metadata.name,
            "namespace": get_namespace(component, default="default"),
            "port": port,
        }
        if api.get("insecure_skip_tls_verify"):
            spec.insecureSkipTLSVerify = True
        if api.get("ca_bundle"):
            spec.caBundle = api.get("ca_bundle")
