"""KServe generator for Kapitan.

Generates KServe resources for ML model serving:
- InferenceService: Deploy ML models with predictors, transformers, explainers
- InferenceGraph: Create ML inference pipelines with routing logic
- ServingRuntime: Define namespace-scoped model serving runtimes
- ClusterServingRuntime: Define cluster-wide model serving runtimes
- TrainedModel: Multi-model serving with a single InferenceService
- ClusterStorageContainer: Configure cluster-wide storage containers
- LocalModelCache: Cache models locally on nodes in node groups
- LocalModelNodeGroup: Define node groups for local model storage

Schema reference: serving.kserve.io/v1beta1, v1alpha1, v1alpha2 (LLM kinds)
See: https://kserve.github.io/website/
"""

__version__ = "1.0.0"

import logging
from typing import Any

from kapitan.inputs.kadet import BaseObj, inventory

from . import k8s


inv = inventory()
logger = logging.getLogger(__name__)


_OMEGACONF_TYPES: tuple[type, ...]
try:
    from omegaconf import DictConfig, ListConfig

    _OMEGACONF_TYPES = (DictConfig, ListConfig)
except ImportError:
    _OMEGACONF_TYPES = ()

# =============================================================================
# Valid enum values from schema
# =============================================================================

# Framework blocks of the v1beta1 PredictorSpec. Model format names are free
# strings in the CRD and are not checked.
PREDICTOR_FRAMEWORKS = (
    "sklearn",
    "xgboost",
    "lightgbm",
    "tensorflow",
    "pytorch",
    "triton",
    "onnx",
    "huggingface",
    "pmml",
    "paddle",
)

VALID_SCALE_METRICS = frozenset({"cpu", "memory", "concurrency", "rps"})

VALID_PROTOCOL_VERSIONS = frozenset({"v1", "v2", "grpc-v1", "grpc-v2"})


# ClusterStorageContainer workload types
VALID_STORAGE_WORKLOAD_TYPES = frozenset({"initContainer", "localModelDownloadJob"})

VALID_INFERENCE_GRAPH_TYPES = frozenset(
    {"Sequence", "Splitter", "Ensemble", "Switch"}
)


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_to_dict(obj: Any) -> Any:
    """Recursively convert BaseObj / OmegaConf objects to plain Python dicts."""
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


def _validate_enum(value: str, valid_values: frozenset, field_name: str) -> None:
    """Validate that a value is in a set of valid enum values.

    Args:
        value: Value to validate.
        valid_values: Set of valid values.
        field_name: Name of the field for error message.

    Raises:
        ValueError: If value is not in valid_values.
    """
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            f"Must be one of: {', '.join(sorted(valid_values))}"
        )


def _warn_collisions(config: dict, mapping: dict[str, str], name: str) -> None:
    """Warn when a flat key overrides a value given in the ``spec`` passthrough.

    ``mapping`` maps dotted flat keys (config paths) to dotted CRD paths under spec.
    """
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


def _set_field(target: Any, config: dict, source_key: str, *, target_key: str) -> None:
    """Set ``target[target_key]`` from ``config[source_key]`` when it is not None."""
    value = config.get(source_key)
    if value is not None:
        target[target_key] = _convert_to_dict(value)


# Flat keys shared by predictor/transformer/explainer (_build_component_spec)
_COMPONENT_FLAT_KEY_MAP = {
    "min_replicas": "minReplicas",
    "max_replicas": "maxReplicas",
    "scale_target": "scaleTarget",
    "scale_metric": "scaleMetric",
    "timeout": "timeout",
    "container_concurrency": "containerConcurrency",
    "batcher": "batcher",
    "logger": "logger",
    "service_account_name": "serviceAccountName",
    "node_selector": "nodeSelector",
    "tolerations": "tolerations",
    "affinity": "affinity",
    "image_pull_secrets": "imagePullSecrets",
    "canary_traffic_percent": "canaryTrafficPercent",
}


# =============================================================================
# Base KServe Resource Class
# =============================================================================


def _default_namespace() -> str:
    """Namespace fallback chain: generators.kserve.namespace -> parameters.namespace."""
    generator_ns = (inv.parameters.get("generators", {}).get("kserve", {}) or {}).get(
        "namespace"
    )
    return str(generator_ns or inv.parameters.get("namespace", "default"))


class KserveBase(k8s.Base):
    """Base class for KServe resources with common patterns."""

    # Flat key -> CRD path under spec, for collision warnings
    _FLAT_KEY_MAP: dict[str, str] = {}

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        # Passthrough first so modelled flat keys set by subclasses win
        if config.get("spec"):
            self.root.spec.update(_convert_to_dict(config["spec"]))
            _warn_collisions(config, self._FLAT_KEY_MAP, self.kwargs.name)

    def _resource_namespace(self, config: dict) -> Any:
        return config.get("namespace", _default_namespace())

    def _add_common_metadata(
        self, config: dict, *, include_namespace: bool = True
    ) -> None:
        """Add common metadata fields from config."""
        if include_namespace:
            self.add_namespace(self._resource_namespace(config))
        self.add_annotations(_convert_to_dict(config.get("annotations", {})))
        self.add_labels(_convert_to_dict(config.get("labels", {})))

    def _set_refs(
        self, target: BaseObj, config: dict, source_key: str, *, target_key: str
    ) -> None:
        """Set LocalObjectReference list field with auto-wrapping.

        Supports both string list (auto-wrapped) and pre-wrapped format.
        """
        refs = config.get(source_key)
        if refs:
            if isinstance(refs, list) and refs and isinstance(refs[0], str):
                target[target_key] = [{"name": ref} for ref in refs]
            else:
                target[target_key] = refs

    def _build_component_spec(self, spec_target: BaseObj, config: dict) -> None:
        """Build common component spec fields (predictor/transformer/explainer)."""
        # Scaling fields
        _set_field(spec_target, config, "min_replicas", target_key="minReplicas")
        _set_field(spec_target, config, "max_replicas", target_key="maxReplicas")
        _set_field(spec_target, config, "scale_target", target_key="scaleTarget")
        _set_field(spec_target, config, "scale_metric", target_key="scaleMetric")

        # Validate scale metric if provided
        scale_metric = config.get("scale_metric")
        if scale_metric:
            _validate_enum(scale_metric, VALID_SCALE_METRICS, "scale_metric")

        # Timeout and concurrency
        _set_field(spec_target, config, "timeout", target_key="timeout")
        _set_field(
            spec_target,
            config,
            "container_concurrency",
            target_key="containerConcurrency",
        )

        # Batcher config
        _set_field(spec_target, config, "batcher", target_key="batcher")

        # Logger config
        _set_field(spec_target, config, "logger", target_key="logger")

        # Pod spec fields
        _set_field(
            spec_target,
            config,
            "service_account_name",
            target_key="serviceAccountName",
        )
        _set_field(
            spec_target,
            config,
            "node_selector",
            target_key="nodeSelector",
        )
        _set_field(spec_target, config, "tolerations", target_key="tolerations")
        _set_field(spec_target, config, "affinity", target_key="affinity")

        # Image pull secrets (auto-wrap strings)
        self._set_refs(
            spec_target, config, "image_pull_secrets", target_key="imagePullSecrets"
        )

        # Canary rollout (ComponentExtensionSpec)
        _set_field(
            spec_target,
            config,
            "canary_traffic_percent",
            target_key="canaryTrafficPercent",
        )


# =============================================================================
# InferenceService
# =============================================================================


class InferenceService(KserveBase):
    """KServe InferenceService resource.

    Deploys ML models with optional predictor, transformer, and explainer components.

    Required kwargs:
        name: Resource name.
        config: InferenceService configuration dictionary.

    Smart defaults:
        - namespace: Inherits from parameters.namespace
        - model_format string shorthand

    Example minimal config:
        {
            'predictor': {
                'model': {
                    'model_format': {'name': 'sklearn'},
                    'storage_uri': 'gs://bucket/model',
                }
            }
        }
    """

    _FLAT_KEY_MAP = {
        **{
            f"{component}.{flat}": f"{component}.{crd}"
            for component in ("predictor", "transformer", "explainer")
            for flat, crd in _COMPONENT_FLAT_KEY_MAP.items()
        },
        **{f"predictor.{fw}": f"predictor.{fw}" for fw in PREDICTOR_FRAMEWORKS},
        "explainer.art": "explainer.art",
        "predictor.model.model_format": "predictor.model.modelFormat",
        "predictor.model.storage_uri": "predictor.model.storageUri",
        "predictor.model.protocol_version": "predictor.model.protocolVersion",
        "predictor.model.runtime": "predictor.model.runtime",
        "predictor.model.runtime_version": "predictor.model.runtimeVersion",
        "predictor.model.resources": "predictor.model.resources",
        "predictor.model.args": "predictor.model.args",
        "predictor.model.env": "predictor.model.env",
        "predictor.model.ports": "predictor.model.ports",
        "transformer.containers": "transformer.containers",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1beta1"
        self.kwargs.kind = "InferenceService"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self._add_common_metadata(config)

        # Build predictor (required in practice)
        if config.get("predictor"):
            self._build_predictor(config["predictor"])

        # Build transformer (optional)
        if config.get("transformer"):
            self._build_transformer(config["transformer"])

        # Build explainer (optional)
        if config.get("explainer"):
            self._build_explainer(config["explainer"])

    def _build_predictor(self, predictor_config: dict) -> None:
        """Build predictor spec with model configuration."""
        predictor = self.root.spec.predictor

        # Model spec - the core of predictor
        if predictor_config.get("model"):
            self._build_model_spec(predictor, predictor_config["model"])

        # Framework-specific predictors (sklearn, tensorflow, etc.)
        for framework in PREDICTOR_FRAMEWORKS:
            if predictor_config.get(framework):
                predictor[framework] = _convert_to_dict(predictor_config[framework])

        # Common component fields
        self._build_component_spec(predictor, predictor_config)

    def _build_model_spec(self, predictor: BaseObj, model_config: dict) -> None:
        """Build the model specification within predictor."""
        model = predictor.model

        # Model format; a plain string is shorthand for {name: ...}
        model_format = model_config.get("model_format")
        if model_format:
            if isinstance(model_format, str):
                model_format = {"name": model_format}
            model.modelFormat = model_format

        # Storage URI (required)
        _set_field(model, model_config, "storage_uri", target_key="storageUri")

        # Protocol version
        protocol = model_config.get("protocol_version")
        if protocol:
            _validate_enum(protocol, VALID_PROTOCOL_VERSIONS, "protocol_version")
            model.protocolVersion = protocol

        # Runtime and runtime version
        _set_field(model, model_config, "runtime", target_key="runtime")
        _set_field(
            model,
            model_config,
            "runtime_version",
            target_key="runtimeVersion",
        )

        # Resources
        _set_field(model, model_config, "resources", target_key="resources")

        # Args and env
        _set_field(model, model_config, "args", target_key="args")
        _set_field(model, model_config, "env", target_key="env")

        # Ports
        _set_field(model, model_config, "ports", target_key="ports")

    def _build_transformer(self, transformer_config: dict) -> None:
        """Build transformer spec."""
        transformer = self.root.spec.transformer

        # Containers (custom transformer)
        _set_field(
            transformer, transformer_config, "containers", target_key="containers"
        )

        # Common component fields
        self._build_component_spec(transformer, transformer_config)

    def _build_explainer(self, explainer_config: dict) -> None:
        """Build explainer spec."""
        explainer = self.root.spec.explainer

        # art is the only explainer block in the v1beta1 ExplainerSpec
        if explainer_config.get("art"):
            explainer.art = _convert_to_dict(explainer_config["art"])

        # Common component fields
        self._build_component_spec(explainer, explainer_config)


# =============================================================================
# InferenceGraph
# =============================================================================


class InferenceGraph(KserveBase):
    """KServe InferenceGraph resource.

    Creates ML inference pipelines with routing logic between models.

    Required kwargs:
        name: Resource name.
        config: InferenceGraph configuration dictionary.

    Example config:
        {
            'nodes': {
                'root': {
                    'router_type': 'Sequence',
                    'steps': [
                        {'service_name': 'preprocessor'},
                        {'service_name': 'model-a'},
                    ]
                }
            }
        }
    """

    _FLAT_KEY_MAP = {
        "nodes": "nodes",
        "min_replicas": "minReplicas",
        "max_replicas": "maxReplicas",
        "scale_target": "scaleTarget",
        "scale_metric": "scaleMetric",
        "timeout": "timeout",
        "router_timeouts": "routerTimeouts",
        "resources": "resources",
        "service_account_name": "serviceAccountName",
        "node_selector": "nodeSelector",
        "tolerations": "tolerations",
        "affinity": "affinity",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "InferenceGraph"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self._add_common_metadata(config)

        # Nodes (required) - the graph structure
        if config.get("nodes"):
            self._build_nodes(config["nodes"])

        # Scaling configuration
        _set_field(
            self.root.spec,
            config,
            "min_replicas",
            target_key="minReplicas",
        )
        _set_field(
            self.root.spec,
            config,
            "max_replicas",
            target_key="maxReplicas",
        )
        _set_field(
            self.root.spec,
            config,
            "scale_target",
            target_key="scaleTarget",
        )
        _set_field(
            self.root.spec,
            config,
            "scale_metric",
            target_key="scaleMetric",
        )
        if config.get("scale_metric"):
            _validate_enum(config["scale_metric"], VALID_SCALE_METRICS, "scale_metric")

        # Timeout
        _set_field(self.root.spec, config, "timeout", target_key="timeout")

        # Router timeouts
        _set_field(
            self.root.spec,
            config,
            "router_timeouts",
            target_key="routerTimeouts",
        )

        # Resources
        _set_field(self.root.spec, config, "resources", target_key="resources")

        # Pod spec fields
        _set_field(
            self.root.spec,
            config,
            "service_account_name",
            target_key="serviceAccountName",
        )
        _set_field(
            self.root.spec,
            config,
            "node_selector",
            target_key="nodeSelector",
        )
        _set_field(self.root.spec, config, "tolerations", target_key="tolerations")
        _set_field(self.root.spec, config, "affinity", target_key="affinity")

    def _build_nodes(self, nodes_config: dict) -> None:
        """Build inference graph nodes."""
        nodes = self.root.spec.nodes
        for node_name, node_config in nodes_config.items():
            node = nodes[node_name]

            # Router type with validation
            router_type = node_config.get("router_type")
            if router_type:
                _validate_enum(router_type, VALID_INFERENCE_GRAPH_TYPES, "router_type")
                node.routerType = router_type

            # Steps (sequence of services/nodes)
            if node_config.get("steps"):
                node.steps = self._build_steps(node_config["steps"])

    # snake_case step keys and their CRD names; other keys pass through
    _STEP_KEYS = {
        "service_name": "serviceName",
        "node_name": "nodeName",
        "service_url": "serviceUrl",
        "map_predictions_to_instances": "mapPredictionsToInstances",
    }

    def _build_steps(self, steps_config: list) -> list:
        """Pass each step through, renaming the snake_case keys."""
        return [
            {self._STEP_KEYS.get(k, k): v for k, v in _convert_to_dict(step).items()}
            for step in steps_config
        ]


# =============================================================================
# ServingRuntime / ClusterServingRuntime
# =============================================================================


class ServingRuntimeBase(KserveBase):
    """Base class for ServingRuntime resources."""

    _FLAT_KEY_MAP = {
        "containers": "containers",
        "supported_model_formats": "supportedModelFormats",
        "multi_model": "multiModel",
        "disabled": "disabled",
        "protocol_versions": "protocolVersions",
        "grpc_endpoint": "grpcEndpoint",
        "grpc_data_endpoint": "grpcDataEndpoint",
        "http_data_endpoint": "httpDataEndpoint",
        "storage_helper": "storageHelper",
        "built_in_adapter": "builtInAdapter",
        "replicas": "replicas",
        "volumes": "volumes",
        "node_selector": "nodeSelector",
        "tolerations": "tolerations",
        "affinity": "affinity",
        "image_pull_secrets": "imagePullSecrets",
        "worker_spec": "workerSpec",
    }

    def _build_runtime_spec(self, config: dict) -> None:
        """Build common serving runtime spec fields."""
        spec = self.root.spec

        # Containers (required). The controller merges the InferenceService
        # model into the runtime container named kserve-container
        # (constants.InferenceServiceContainerName), so an unnamed first
        # container gets that name, also in the spec passthrough.
        containers = _convert_to_dict(
            config.get("containers") or self.root.spec.get("containers")
        )
        if containers:
            if isinstance(containers[0], dict) and "name" not in containers[0]:
                containers[0] = {"name": "kserve-container", **containers[0]}
            spec.containers = containers

        # Supported model formats
        if config.get("supported_model_formats"):
            formats = config.get("supported_model_formats")
            spec.supportedModelFormats = _convert_to_dict(formats)

        # Multi-model support
        _set_field(spec, config, "multi_model", target_key="multiModel")

        # Disabled flag
        _set_field(spec, config, "disabled", target_key="disabled")

        # Protocol versions
        protocol_versions = config.get("protocol_versions")
        if protocol_versions:
            for pv in protocol_versions:
                _validate_enum(pv, VALID_PROTOCOL_VERSIONS, "protocol_version")
            spec.protocolVersions = protocol_versions

        # gRPC/HTTP endpoints
        _set_field(spec, config, "grpc_endpoint", target_key="grpcEndpoint")
        _set_field(
            spec,
            config,
            "grpc_data_endpoint",
            target_key="grpcDataEndpoint",
        )
        _set_field(
            spec,
            config,
            "http_data_endpoint",
            target_key="httpDataEndpoint",
        )

        # Storage helper
        _set_field(spec, config, "storage_helper", target_key="storageHelper")

        # Built-in adapter
        _set_field(
            spec,
            config,
            "built_in_adapter",
            target_key="builtInAdapter",
        )

        # Replicas
        _set_field(spec, config, "replicas", target_key="replicas")

        # Volumes
        _set_field(spec, config, "volumes", target_key="volumes")

        # Pod spec fields
        _set_field(spec, config, "node_selector", target_key="nodeSelector")
        _set_field(spec, config, "tolerations", target_key="tolerations")
        _set_field(spec, config, "affinity", target_key="affinity")

        # Image pull secrets
        self._set_refs(
            spec, config, "image_pull_secrets", target_key="imagePullSecrets"
        )

        # Worker spec (for multi-node inference)
        _set_field(spec, config, "worker_spec", target_key="workerSpec")


class ServingRuntime(ServingRuntimeBase):
    """KServe ServingRuntime resource (namespace-scoped).

    Defines a model serving runtime for a specific namespace.

    Required kwargs:
        name: Resource name.
        config: ServingRuntime configuration dictionary.

    Example config:
        {
            'containers': [{
                'name': 'kserve-container',
                'image': 'tensorflow/serving:2.6.0',
                'args': ['--model_name={{.Name}}'],
            }],
            'supported_model_formats': [
                {'name': 'tensorflow', 'version': '2'}
            ],
            'protocol_versions': ['v1', 'v2'],
        }
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "ServingRuntime"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self._add_common_metadata(config)
        self._build_runtime_spec(config)


class ClusterServingRuntime(ServingRuntimeBase):
    """KServe ClusterServingRuntime resource (cluster-scoped).

    Defines a cluster-wide model serving runtime.

    Required kwargs:
        name: Resource name.
        config: ClusterServingRuntime configuration dictionary.
    """

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "ClusterServingRuntime"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # ClusterServingRuntime is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        self._build_runtime_spec(config)


# =============================================================================
# TrainedModel
# =============================================================================


class TrainedModel(KserveBase):
    """KServe TrainedModel resource.

    Enables multi-model serving with a single InferenceService.

    Required kwargs:
        name: Resource name.
        config: TrainedModel configuration dictionary.

    Example config:
        {
            'inference_service': 'my-isvc',
            'model': {
                'framework': 'sklearn',
                'storage_uri': 'gs://bucket/model',
                'memory': '256Mi',
            }
        }
    """

    _FLAT_KEY_MAP = {
        "inference_service": "inferenceService",
        "model.framework": "model.framework",
        "model.storage_uri": "model.storageUri",
        "model.memory": "model.memory",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "TrainedModel"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        self._add_common_metadata(config)

        # InferenceService reference (required)
        isvc = config.get("inference_service")
        if isvc:
            self.root.spec.inferenceService = isvc

        # Model spec (required)
        if config.get("model"):
            self._build_model(config["model"])

    def _build_model(self, model_config: dict) -> None:
        """Build trained model spec."""
        model = self.root.spec.model

        # Framework (free string in the CRD)
        _set_field(model, model_config, "framework", target_key="framework")

        # Storage URI (required)
        _set_field(model, model_config, "storage_uri", target_key="storageUri")

        # Memory (required)
        _set_field(model, model_config, "memory", target_key="memory")


# =============================================================================
# ClusterStorageContainer (legacy support)
# =============================================================================


class ClusterStorageContainer(KserveBase):
    """KServe ClusterStorageContainer resource.

    Configures cluster-wide storage containers for model artifacts.

    Required kwargs:
        name: Resource name.
        config: ClusterStorageContainer configuration dictionary.

    Example config:
        {
            'container': {
                'name': 'storage-initializer',
                'image': 'kserve/storage-initializer:latest',
            },
            'supported_uri_formats': [{'prefix': 's3://'}],
            'multi_model_download': True,
        }
    """

    _FLAT_KEY_MAP = {
        "container": "container",
        "supported_uri_formats": "supportedUriFormats",
        "multi_model_download": "supportsMultiModelDownload",
        "workload_type": "workloadType",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "ClusterStorageContainer"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # ClusterStorageContainer is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Container spec
        _set_field(self.root.spec, config, "container", target_key="container")

        # Supported URI formats
        uri_formats = config.get("supported_uri_formats")
        if uri_formats:
            self.root.spec.supportedUriFormats = uri_formats

        # Multi-model download support
        multi_model = config.get("multi_model_download")
        if multi_model is not None:
            self.root.spec.supportsMultiModelDownload = multi_model

        # Workload type with validation (ClusterStorageContainer uses different values)
        workload_type = config.get("workload_type")
        if workload_type:
            _validate_enum(workload_type, VALID_STORAGE_WORKLOAD_TYPES, "workload_type")
            self.root.spec.workloadType = workload_type

        # disabled is a top-level field, next to spec
        _set_field(self.root, config, "disabled", target_key="disabled")


# =============================================================================
# LocalModelCache
# =============================================================================


class LocalModelCache(KserveBase):
    """KServe LocalModelCache resource.

    Defines a model to be cached locally on nodes in specified node groups.

    Required kwargs:
        name: Resource name.
        config: LocalModelCache configuration dictionary.

    Example config:
        {
            'source_model_uri': 's3://bucket/model',
            'model_size': '10Gi',
            'node_groups': ['gpu-nodes'],
        }
    """

    _FLAT_KEY_MAP = {
        "source_model_uri": "sourceModelUri",
        "model_size": "modelSize",
        "node_groups": "nodeGroups",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "LocalModelCache"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # LocalModelCache is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Source model URI (required)
        source_uri = config.get("source_model_uri")
        if source_uri:
            self.root.spec.sourceModelUri = source_uri

        # Model size (required)
        model_size = config.get("model_size")
        if model_size:
            self.root.spec.modelSize = model_size

        # Node groups (required)
        node_groups = config.get("node_groups")
        if node_groups:
            self.root.spec.nodeGroups = node_groups


# =============================================================================
# LocalModelNodeGroup
# =============================================================================


class LocalModelNodeGroup(KserveBase):
    """KServe LocalModelNodeGroup resource.

    Defines a group of nodes for local model storage with PV/PVC specs.

    Required kwargs:
        name: Resource name.
        config: LocalModelNodeGroup configuration dictionary.

    Smart defaults (reduces boilerplate):
        - PVC accessModes: Inherited from PV spec if not specified
        - PVC storageClassName: Inherited from PV spec if not specified
        - PVC resources.requests.storage: Inherited from PV capacity if not specified

    Example minimal config (with smart defaults):
        {
            'persistent_volume_spec': {
                'accessModes': ['ReadWriteOnce'],
                'capacity': {'storage': '100Gi'},
                'storageClassName': 'local-storage',
            },
            # PVC spec auto-inherits from PV: accessModes, storageClassName, storage
            'storage_limit': '500Gi',
        }

    Example full config (explicit values):
        {
            'persistent_volume_spec': {
                'accessModes': ['ReadWriteOnce'],
                'capacity': {'storage': '100Gi'},
                'storageClassName': 'local-storage',
            },
            'persistent_volume_claim_spec': {
                'accessModes': ['ReadWriteOnce'],
                'storageClassName': 'local-storage',
                'resources': {'requests': {'storage': '100Gi'}},
            },
            'storage_limit': '500Gi',
        }
    """

    _FLAT_KEY_MAP = {
        "persistent_volume_spec": "persistentVolumeSpec",
        "persistent_volume_claim_spec": "persistentVolumeClaimSpec",
        "storage_limit": "storageLimit",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha1"
        self.kwargs.kind = "LocalModelNodeGroup"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config

        # LocalModelNodeGroup is cluster-scoped, no namespace
        self.add_annotations(config.get("annotations", {}))
        self.add_labels(config.get("labels", {}))

        # Persistent volume spec (required)
        pv_spec = config.get("persistent_volume_spec")
        if pv_spec:
            self.root.spec.persistentVolumeSpec = pv_spec

        # Persistent volume claim spec with smart defaults from PV spec
        # Fall back to a PVC spec given via the spec passthrough
        pvc_spec = config.get("persistent_volume_claim_spec") or _convert_to_dict(
            self.root.spec.get("persistentVolumeClaimSpec")
        )
        final_pvc_spec = self._build_pvc_spec_with_defaults(pv_spec, pvc_spec)
        if final_pvc_spec:
            self.root.spec.persistentVolumeClaimSpec = final_pvc_spec

        # Storage limit
        storage_limit = config.get("storage_limit")
        if storage_limit:
            self.root.spec.storageLimit = storage_limit

    def _build_pvc_spec_with_defaults(
        self, pv_spec: dict | None, pvc_spec: dict | None
    ) -> dict | None:
        """Build PVC spec with smart defaults inherited from PV spec.

        Reduces boilerplate by auto-filling:
        - accessModes from PV spec
        - storageClassName from PV spec ("" if the PV has none)
        - resources.requests.storage from PV capacity
        """
        if not pv_spec:
            return pvc_spec

        # Start with user-provided PVC spec or empty dict
        result = dict(pvc_spec) if pvc_spec else {}

        # Inherit accessModes from PV if not specified
        if "accessModes" not in result and pv_spec.get("accessModes"):
            result["accessModes"] = pv_spec["accessModes"]

        # Inherit storageClassName from PV if not specified. The controller
        # binds the PVC to the PV by volumeName; without a class on the PV the
        # PVC gets "" so the default StorageClass is not applied to it.
        if "storageClassName" not in result:
            result["storageClassName"] = pv_spec.get("storageClassName") or ""

        # Inherit storage from PV capacity if not specified
        pv_capacity = pv_spec.get("capacity", {}).get("storage")
        if pv_capacity:
            if "resources" not in result:
                result["resources"] = {}
            if "requests" not in result["resources"]:
                result["resources"]["requests"] = {}
            if "storage" not in result["resources"]["requests"]:
                result["resources"]["requests"]["storage"] = pv_capacity

        return result if result else None


# =============================================================================
# LLM Inference Resources (serving.kserve.io/v1alpha2, the storage version)
# =============================================================================

class LLMInferenceServiceBase(KserveBase):
    """Shared body of LLMInferenceService and LLMInferenceServiceConfig.

    Both are namespaced and share the v1alpha2 spec. template, worker and
    prefill.template are PodSpecs, router holds gateway, ingress, route and
    scheduler; all of them pass through verbatim.
    """

    _FLAT_KEY_MAP = {
        "model.uri": "model.uri",
        "model.name": "model.name",
        "model.lora": "model.lora",
        "replicas": "replicas",
        "parallelism.data": "parallelism.data",
        "parallelism.data_local": "parallelism.dataLocal",
        "parallelism.pipeline": "parallelism.pipeline",
        "parallelism.tensor": "parallelism.tensor",
        "parallelism.data_rpc_port": "parallelism.dataRPCPort",
        "parallelism.expert": "parallelism.expert",
        "prefill.replicas": "prefill.replicas",
        "prefill.parallelism": "prefill.parallelism",
        "prefill.template": "prefill.template",
        "worker": "worker",
        "router": "router",
        "base_refs": "baseRefs",
        "template": "template",
    }

    _PARALLELISM_KEYS = {
        "data": "data",
        "data_local": "dataLocal",
        "data_rpc_port": "dataRPCPort",
        "pipeline": "pipeline",
        "tensor": "tensor",
        "expert": "expert",
    }

    def new(self) -> None:
        self.need("name")
        self.kwargs.apiVersion = "serving.kserve.io/v1alpha2"
        super().new()

    def body(self) -> None:
        super().body()
        config = self.kwargs.config
        spec = self.root.spec

        self._add_common_metadata(config)
        self._build_model_spec(config)
        _set_field(spec, config, "replicas", target_key="replicas")

        parallelism = config.get("parallelism")
        if parallelism:
            for key, crd_key in self._PARALLELISM_KEYS.items():
                _set_field(spec.parallelism, parallelism, key, target_key=crd_key)

        prefill = config.get("prefill")
        if prefill:
            for key in ("replicas", "parallelism", "template"):
                _set_field(spec.prefill, prefill, key, target_key=key)

        _set_field(spec, config, "worker", target_key="worker")
        _set_field(spec, config, "router", target_key="router")

        base_refs = config.get("base_refs")
        if base_refs:
            spec.baseRefs = [
                {"name": ref} if isinstance(ref, str) else ref for ref in base_refs
            ]

        _set_field(spec, config, "template", target_key="template")

    def _build_model_spec(self, config: dict) -> None:
        """Build the model spec; drop the criticality fields v1alpha2 removed."""
        model_config = config.get("model")
        if not model_config:
            return

        model = self.root.spec.model
        _set_field(model, model_config, "uri", target_key="uri")
        _set_field(model, model_config, "name", target_key="name")

        # v1alpha2 has no criticality; v1alpha1 conversion keeps it only in an
        # internal annotation
        if model_config.get("criticality"):
            logger.warning(
                "%s: model.criticality not part of the v1alpha2 CRD, dropped",
                self.kwargs.name,
            )

        lora = _convert_to_dict(model_config.get("lora"))
        if lora:
            adapters = lora.get("adapters")
            if isinstance(adapters, list):
                if any(isinstance(a, dict) and "criticality" in a for a in adapters):
                    logger.warning(
                        "%s: model.lora.adapters[].criticality not part of the "
                        "v1alpha2 CRD, dropped",
                        self.kwargs.name,
                    )
                lora["adapters"] = [
                    {k: v for k, v in a.items() if k != "criticality"}
                    if isinstance(a, dict)
                    else a
                    for a in adapters
                ]
            model.lora = lora


class LLMInferenceService(LLMInferenceServiceBase):
    """KServe LLMInferenceService: one LLM deployment.

    Example config:
        {
            'model': {'uri': 'hf://org/model', 'name': 'org/model'},
            'replicas': 2,
            'parallelism': {'tensor': 4},
        }
    """

    def new(self) -> None:
        self.kwargs.kind = "LLMInferenceService"
        super().new()


class LLMInferenceServiceConfig(LLMInferenceServiceBase):
    """KServe LLMInferenceServiceConfig: shared settings referenced via baseRefs.

    Example config:
        {
            'template': {'nodeSelector': {'gpu-type': 'a100'}},
        }
    """

    def new(self) -> None:
        self.kwargs.kind = "LLMInferenceServiceConfig"
        super().new()


# =============================================================================
# Main Entry Point
# =============================================================================


def main(input_params) -> BaseObj:
    """Generate KServe resources from inventory.

    Reads from parameters.generators.kserve:
    - inference_services: InferenceService configurations
    - inference_graphs: InferenceGraph configurations
    - serving_runtimes: ServingRuntime configurations
    - cluster_serving_runtimes: ClusterServingRuntime configurations
    - trained_models: TrainedModel configurations
    - cluster_storage_containers: ClusterStorageContainer configurations
    - local_model_caches: LocalModelCache configurations
    - local_model_node_groups: LocalModelNodeGroup configurations
    - llm_inference_services: LLMInferenceService configurations
    - llm_inference_service_configs: LLMInferenceServiceConfig configurations
    """
    obj = BaseObj()

    # Get kserve config from generators namespace
    kserve_config = inv.parameters.get("generators", {}).get("kserve", {}) or {}
    default_namespace = _default_namespace()

    # Generate InferenceServices (namespace-scoped)
    for name, config in kserve_config.get("inference_services", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-isvc"] = InferenceService(
            name=name, config=config
        )

    # Generate InferenceGraphs (namespace-scoped)
    for name, config in kserve_config.get("inference_graphs", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-inferencegraph"] = InferenceGraph(
            name=name, config=config
        )

    # Generate ServingRuntimes (namespace-scoped)
    for name, config in kserve_config.get("serving_runtimes", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-servingruntime"] = ServingRuntime(
            name=name, config=config
        )

    # Generate ClusterServingRuntimes (cluster-scoped)
    for name, config in kserve_config.get("cluster_serving_runtimes", {}).items():
        obj.root[f"{name}-clusterservingruntime"] = ClusterServingRuntime(
            name=name, config=_convert_to_dict(config) or {}
        )

    # Generate TrainedModels (namespace-scoped)
    for name, config in kserve_config.get("trained_models", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-trainedmodel"] = TrainedModel(
            name=name, config=config
        )

    # Generate ClusterStorageContainers (cluster-scoped)
    for name, config in kserve_config.get("cluster_storage_containers", {}).items():
        obj.root[f"{name}-clusterstoragecontainer"] = ClusterStorageContainer(
            name=name, config=_convert_to_dict(config) or {}
        )

    # Generate LocalModelCaches (cluster-scoped)
    for name, config in kserve_config.get("local_model_caches", {}).items():
        obj.root[f"{name}-localmodelcache"] = LocalModelCache(
            name=name, config=_convert_to_dict(config) or {}
        )

    # Generate LocalModelNodeGroups (cluster-scoped)
    for name, config in kserve_config.get("local_model_node_groups", {}).items():
        obj.root[f"{name}-localmodelnodegroup"] = LocalModelNodeGroup(
            name=name, config=_convert_to_dict(config) or {}
        )

    # Generate LLMInferenceServices (namespace-scoped)
    for name, config in kserve_config.get("llm_inference_services", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-llminferenceservice"] = LLMInferenceService(
            name=name, config=config
        )

    # Generate LLMInferenceServiceConfigs (namespaced)
    for name, config in kserve_config.get("llm_inference_service_configs", {}).items():
        config = _convert_to_dict(config) or {}
        namespace = config.get("namespace", default_namespace)
        obj.root[f"{namespace}/{name}-llminferenceserviceconfig"] = (
            LLMInferenceServiceConfig(name=name, config=config)
        )

    return obj


__all__ = [
    "InferenceService",
    "InferenceGraph",
    "ServingRuntime",
    "ClusterServingRuntime",
    "TrainedModel",
    "ClusterStorageContainer",
    "LocalModelCache",
    "LocalModelNodeGroup",
    "LLMInferenceService",
    "LLMInferenceServiceConfig",
    "main",
]
