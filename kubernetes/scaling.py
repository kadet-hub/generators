"""Kubernetes autoscaling resources: HorizontalPodAutoscaler, VerticalPodAutoscaler, PodDisruptionBudget.

This module provides classes for generating Kubernetes autoscaling and disruption
budget resources. These resources control pod scaling behavior and availability
during voluntary disruptions.
"""

from . import k8s
from .utils import get_namespace, pod_labels


class PodDisruptionBudget(k8s.Base):
    """Kubernetes PodDisruptionBudget resource.

    Generates a PodDisruptionBudget manifest to limit voluntary pod disruptions.
    Supports either minAvailable or maxUnavailable policies.

    Required kwargs:
        component: Component configuration dictionary.
        workload: Workload reference for label matching.
        name: PDB name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.need("workload")
        self.kwargs.apiVersion = "policy/v1"
        self.kwargs.kind = "PodDisruptionBudget"
        super().new()

    def body(self) -> None:
        """Build the PodDisruptionBudget."""
        super().body()
        component = self.kwargs.component
        workload = self.kwargs.workload
        namespace = get_namespace(component)
        if namespace:
            self.add_namespace(namespace)
        if component.get("auto_pdb"):
            self.root.spec.maxUnavailable = 1
        else:
            self.root.spec.minAvailable = component.get("pdb_min_available")
        self.root.spec.selector.matchLabels = pod_labels(workload)


class VerticalPodAutoscaler(k8s.Base):
    """Kubernetes VerticalPodAutoscaler resource.

    Generates a VPA manifest for automatic vertical pod scaling.
    Adjusts container resource requests and limits based on usage.

    Required kwargs:
        component: Component configuration dictionary.
        workload: Workload reference for targeting.
        name: VPA name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.need("workload")
        self.kwargs.apiVersion = "autoscaling.k8s.io/v1"
        self.kwargs.kind = "VerticalPodAutoscaler"
        super().new()

    def body(self) -> None:
        """Build the VerticalPodAutoscaler."""
        super().body()
        component = self.kwargs.component
        workload = self.kwargs.workload
        namespace = get_namespace(component)
        if namespace:
            self.add_namespace(namespace)
        self.add_labels(workload.metadata.labels)
        self.root.spec.targetRef.apiVersion = workload.apiVersion
        self.root.spec.targetRef.kind = workload.kind
        self.root.spec.targetRef.name = workload.metadata.name
        self.root.spec.updatePolicy.updateMode = component.get("vpa")


class HorizontalPodAutoscaler(k8s.Base):
    """Kubernetes HorizontalPodAutoscaler resource.

    Generates an HPA manifest for automatic horizontal pod scaling.
    Scales the number of pod replicas based on observed metrics.

    Required kwargs:
        component: Component configuration dictionary with hpa settings.
        workload: Workload reference for targeting.
        name: HPA name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.need("workload")
        self.kwargs.apiVersion = "autoscaling/v2"
        self.kwargs.kind = "HorizontalPodAutoscaler"
        super().new()

    def body(self) -> None:
        """Build the HorizontalPodAutoscaler."""
        super().body()
        component = self.kwargs.component
        workload = self.kwargs.workload
        namespace = get_namespace(component)
        if namespace:
            self.add_namespace(namespace)
        self.add_labels(workload.metadata.labels)
        self.root.spec.scaleTargetRef.apiVersion = workload.apiVersion
        self.root.spec.scaleTargetRef.kind = workload.kind
        self.root.spec.scaleTargetRef.name = workload.metadata.name
        if component.get("hpa", {}).get("min_replicas") is not None:
            self.root.spec.minReplicas = component.get("hpa", {}).get("min_replicas")
        if component.get("hpa", {}).get("max_replicas") is None:
            raise ValueError(
                f"hpa.max_replicas is required for component '{self.kwargs.name}' "
                "(maxReplicas is mandatory in the HPA spec)"
            )
        self.root.spec.maxReplicas = component.get("hpa", {}).get("max_replicas")
        # Only set metrics if explicitly configured (must be array or null, not empty dict)
        metrics = component.get("hpa", {}).get("metrics")
        if metrics:
            self.root.spec.metrics = metrics
