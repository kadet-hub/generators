"""Kubernetes workload resources: Deployment, StatefulSet, DaemonSet, Job, CronJob.

This module provides classes for generating Kubernetes workload resources.
Each class inherits from k8s.Base and WorkloadCommon to provide consistent
metadata handling and workload-specific functionality.
"""

import logging

from . import k8s
from .base import (
    VALID_RESTART_POLICIES,
    WorkloadCommon,
    _validate_enum,
)


logger = logging.getLogger(__name__)


def _set_common_pod_spec(workload, component, default_restart_policy: str) -> None:
    """Set common pod spec fields shared by all workload types.

    Args:
        workload: The workload object to configure
        component: Component configuration dictionary
        default_restart_policy: Default restart policy for this workload type
    """
    pod_spec = workload.root.spec.template.spec

    # Restart policy with validation
    restart_policy = component.get("restart_policy", default_restart_policy)
    _validate_enum(restart_policy, VALID_RESTART_POLICIES, "restartPolicy")
    pod_spec.restartPolicy = restart_policy

    # Host namespace options
    if "host_ipc" in component:
        pod_spec.hostIPC = component.get("host_ipc")
    if "host_network" in component:
        pod_spec.hostNetwork = component.get("host_network")
    if "host_pid" in component:
        pod_spec.hostPID = component.get("host_pid")


class Deployment(k8s.Base, WorkloadCommon):
    """Kubernetes Deployment resource.

    Generates a Deployment manifest from component configuration.
    Supports rolling update strategies, revision history limits,
    and progress deadline configuration.

    Required kwargs:
        component: Component configuration dictionary.
        name: Deployment name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "apps/v1"
        self.kwargs.kind = "Deployment"
        super().new()

    def body(self) -> None:
        """Build the Deployment spec."""
        default_strategy = {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"},
        }
        super().body()
        component = self.kwargs.component
        self.root.spec.template.metadata.labels = self.root.metadata.labels
        self.root.spec.selector.matchLabels = self.root.metadata.labels
        _set_common_pod_spec(self, component, default_restart_policy="Always")
        self.root.spec.strategy = component.get("update_strategy", default_strategy)
        if component.get("revision_history_limit"):
            self.root.spec.revisionHistoryLimit = component.get(
                "revision_history_limit"
            )
        if component.get("deployment_progress_deadline_seconds"):
            self.root.spec.progressDeadlineSeconds = component.get(
                "deployment_progress_deadline_seconds"
            )
        self.set_replicas(component.get("replicas", 1))


class StatefulSet(k8s.Base, WorkloadCommon):
    """Kubernetes StatefulSet resource.

    Generates a StatefulSet manifest from component configuration.
    Supports headless services, persistent storage, and ordered pod management.

    Required kwargs:
        component: Component configuration dictionary.
        name: StatefulSet name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "apps/v1"
        self.kwargs.kind = "StatefulSet"
        super().new()

    def body(self) -> None:
        """Build the StatefulSet spec."""
        default_update_strategy = {
            "rollingUpdate": {"partition": 0},
            "type": "RollingUpdate",
        }

        super().body()
        name = self.kwargs.name
        component = self.kwargs.component
        self.root.spec.template.metadata.labels = self.root.metadata.labels
        self.root.spec.selector.matchLabels = self.root.metadata.labels
        _set_common_pod_spec(self, component, default_restart_policy="Always")
        if component.get("revision_history_limit"):
            self.root.spec.revisionHistoryLimit = component.get(
                "revision_history_limit"
            )
        # StatefulSet uses updateStrategy, not strategy (that's Deployment-only)
        self.root.spec.updateStrategy = component.get(
            "update_strategy", default_update_strategy
        )
        self.root.spec.serviceName = (component.get("service") or {}).get(
            "service_name", name
        )
        self.set_replicas(component.get("replicas", 1))


class DaemonSet(k8s.Base, WorkloadCommon):
    """Kubernetes DaemonSet resource.

    Generates a DaemonSet manifest from component configuration.
    Ensures a copy of a pod runs on all (or some) nodes in the cluster.

    Required kwargs:
        component: Component configuration dictionary.
        name: DaemonSet name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.kwargs.apiVersion = "apps/v1"
        self.kwargs.kind = "DaemonSet"
        super().new()

    def body(self) -> None:
        """Build the DaemonSet spec."""
        super().body()
        component = self.kwargs.component
        self.root.spec.template.metadata.labels = self.root.metadata.labels
        self.root.spec.selector.matchLabels = self.root.metadata.labels
        _set_common_pod_spec(self, component, default_restart_policy="Always")
        if component.get("revision_history_limit"):
            self.root.spec.revisionHistoryLimit = component.get(
                "revision_history_limit"
            )
        if component.get("deployment_progress_deadline_seconds"):
            # progressDeadlineSeconds exists only on Deployments.
            logger.warning(
                "%s: deployment_progress_deadline_seconds is ignored for a DaemonSet",
                self.name,
            )


class Job(k8s.Base, WorkloadCommon):
    """Kubernetes Job resource.

    Generates a Job manifest from component configuration.
    Supports batch processing with configurable completion and parallelism.

    Required kwargs:
        component: Component configuration dictionary.
        name: Job name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.kwargs.apiVersion = "batch/v1"
        self.kwargs.kind = "Job"
        super().new()
        self.need("component")

    def body(self) -> None:
        """Build the Job spec."""
        super().body()
        component = self.kwargs.component
        self.root.spec.template.metadata.labels = self.root.metadata.labels
        _set_common_pod_spec(self, component, default_restart_policy="Never")
        self.root.spec.backoffLimit = component.get("backoff_limit", 1)
        self.root.spec.completions = component.get("completions", 1)
        self.root.spec.parallelism = component.get("parallelism", 1)
        if component.get("active_deadline_seconds") is not None:
            self.root.spec.activeDeadlineSeconds = component.get(
                "active_deadline_seconds"
            )
        if component.get("ttl_seconds_after_finished") is not None:
            self.root.spec.ttlSecondsAfterFinished = component.get(
                "ttl_seconds_after_finished"
            )


class CronJob(k8s.Base, WorkloadCommon):
    """Kubernetes CronJob resource.

    Generates a CronJob manifest from component configuration.
    Wraps a Job template with cron schedule configuration.

    Required kwargs:
        component: Component configuration dictionary with schedule.
        job: The Job workload to wrap.
        name: CronJob name.
    """

    def new(self) -> None:
        """Initialize required fields."""
        self.need("component")
        self.need("job")
        self.kwargs.apiVersion = "batch/v1"
        self.kwargs.kind = "CronJob"
        super().new()

    def body(self) -> None:
        """Build the CronJob spec."""
        super().body()
        component = self.kwargs.component
        job = self.kwargs.job
        self.root.metadata = job.root.metadata
        self.root.spec.jobTemplate.spec = job.root.spec
        self.root.spec.schedule = component.get("schedule")
        if component.get("suspend") is not None:
            self.root.spec.suspend = component.get("suspend")
        if component.get("concurrency_policy") is not None:
            self.root.spec.concurrencyPolicy = component.get("concurrency_policy")
        if component.get("starting_deadline_seconds") is not None:
            self.root.spec.startingDeadlineSeconds = component.get(
                "starting_deadline_seconds"
            )
