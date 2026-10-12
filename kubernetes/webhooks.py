"""Kubernetes webhook resources: Mutating- and ValidatingWebhookConfiguration."""

from . import k8s
from .rbac import cluster_scoped_name
from .utils import _convert_to_dict, get_namespace

CA_INJECTION = "cert-manager.io/inject-ca-from"


def _webhooks(name, component, key):
    """The component's webhooks, checked for a CA and scoped away from their own namespace.

    The API server verifies a service webhook's serving certificate against
    clientConfig.caBundle; without one every call fails, which blocks the
    matched requests unless failurePolicy is Ignore (the default is Fail).
    """
    annotations = component.get("webhook_annotations") or {}
    webhooks = _convert_to_dict(component.get(key)) or []
    for webhook in webhooks:
        client = webhook.get("clientConfig") or {}
        if (
            webhook.get("failurePolicy", "Fail") == "Fail"
            and "service" in client
            and not client.get("caBundle")
            and CA_INJECTION not in annotations
        ):
            raise ValueError(
                f"{name}: webhook {webhook.get('name')!r} has failurePolicy Fail "
                f"but no clientConfig.caBundle; set it or webhook_annotations "
                f"{CA_INJECTION}"
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
