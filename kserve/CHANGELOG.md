# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- LLMInferenceService and LLMInferenceServiceConfig are emitted as `serving.kserve.io/v1alpha2`, the storage version of KServe 0.21.0. `model.criticality` does not exist in `v1alpha2` and is dropped with a warning.
- The first ServingRuntime or ClusterServingRuntime container without a `name` is named `kserve-container`, the container the controller merges the InferenceService model into.
- Model format names and TrainedModel `framework` are no longer checked against a fixed list; the CRD takes any string.
- LocalModelNode is no longer rendered; the LocalModelCache controller manages it.
- InferenceGraph steps pass through with all CRD keys (`name`, `dependency`, `mapPredictionsToInstances`); router type `Router` and node `routes`, which the CRD does not define, are removed.
- `canary_traffic_percent` works on transformer and explainer; ClusterStorageContainer takes `disabled`; scale metric `gpu`, not in the CRD, is rejected.
- A derived LocalModelNodeGroup PVC gets `storageClassName: ""` when the PV has no class; `model.lora.adapters[].criticality` is dropped with a warning like `model.criticality`.
- Explainer blocks `alibi` and `aix360`, which the v0.21.0 ExplainerSpec does not define, are removed; `art` remains.
- Ships the KServe 0.21.0 CRD schemas under `schemas/`; the gate validates the compiled output against them (QA-7).
