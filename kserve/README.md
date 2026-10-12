# KServe Generator

Published on [kadet-hub](https://kadet-hub.org/generators/kserve/): pin a released version by digest from its [catalog](https://kadet-hub.org/generators/kserve/) page.

Kapitan kadet generator for [KServe](https://kserve.github.io/website/) model serving resources (`serving.kserve.io`). Built for KServe 0.21.0.

- **InferenceService** (`v1beta1`): predictor, transformer and explainer of one model
- **InferenceGraph** (`v1alpha1`): routing between InferenceServices (Sequence, Splitter, Ensemble, Switch)
- **ServingRuntime**, **ClusterServingRuntime** (`v1alpha1`): model server templates
- **TrainedModel** (`v1alpha1`): a model loaded into a multi-model InferenceService
- **ClusterStorageContainer** (`v1alpha1`): storage initializer per URI scheme
- **LocalModelCache**, **LocalModelNodeGroup** (`v1alpha1`): models cached on node-local volumes
- **LLMInferenceService**, **LLMInferenceServiceConfig** (`v1alpha2`): LLM serving with llm-d

Every kind is emitted in the storage version of KServe 0.21.0. `v1alpha1` of the two LLM kinds is still served, but the CRDs store `v1alpha2`. LocalModelNode is not rendered: the LocalModelCache controller creates and updates it. Model artifacts, Secrets and the Gateway belong elsewhere.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/kserve@sha256:<digest>
        output_path: lib/kserve
    compile:
      - output_path: manifests/kserve/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/kserve
```

### Inventory Contract

All keys live under `parameters.generators.kserve`.

| Key | Kind | Output file |
|---|---|---|
| `namespace` | | Default namespace. Falls back to `parameters.namespace`, then `default`. |
| `inference_services.<name>` | InferenceService | `<namespace>/<name>-isvc` |
| `inference_graphs.<name>` | InferenceGraph | `<namespace>/<name>-inferencegraph` |
| `serving_runtimes.<name>` | ServingRuntime | `<namespace>/<name>-servingruntime` |
| `cluster_serving_runtimes.<name>` | ClusterServingRuntime | `<name>-clusterservingruntime` |
| `trained_models.<name>` | TrainedModel | `<namespace>/<name>-trainedmodel` |
| `cluster_storage_containers.<name>` | ClusterStorageContainer | `<name>-clusterstoragecontainer` |
| `local_model_caches.<name>` | LocalModelCache | `<name>-localmodelcache` |
| `local_model_node_groups.<name>` | LocalModelNodeGroup | `<name>-localmodelnodegroup` |
| `llm_inference_services.<name>` | LLMInferenceService | `<namespace>/<name>-llminferenceservice` |
| `llm_inference_service_configs.<name>` | LLMInferenceServiceConfig | `<namespace>/<name>-llminferenceserviceconfig` |

Every resource accepts `labels`, `annotations` and `spec`; namespaced kinds also accept `namespace`. `spec` is merged into the resource spec first, then the flat keys below are applied; a flat key that overrides a `spec` value logs a warning.

Flat keys are the snake_case spelling of the CRD `spec` fields:

| Kind | Flat keys |
|---|---|
| InferenceService | `predictor`, `transformer`, `explainer`, each with `min_replicas`, `max_replicas`, `scale_target`, `scale_metric`, `timeout`, `container_concurrency`, `batcher`, `logger`, `service_account_name`, `node_selector`, `tolerations`, `affinity`, `image_pull_secrets`, `canary_traffic_percent`. `predictor` also takes `model` (`model_format`, `storage_uri`, `protocol_version`, `runtime`, `runtime_version`, `resources`, `args`, `env`, `ports`) and the framework blocks (`sklearn`, `xgboost`, `lightgbm`, `tensorflow`, `pytorch`, `triton`, `onnx`, `huggingface`, `pmml`, `paddle`); `transformer` takes `containers`; `explainer` takes `art`. |
| InferenceGraph | `nodes.<node>` (`router_type`, `steps`), `min_replicas`, `max_replicas`, `scale_target`, `scale_metric`, `timeout`, `router_timeouts`, `resources`, `service_account_name`, `node_selector`, `tolerations`, `affinity` |
| ServingRuntime, ClusterServingRuntime | `containers`, `supported_model_formats`, `multi_model`, `disabled`, `protocol_versions`, `grpc_endpoint`, `grpc_data_endpoint`, `http_data_endpoint`, `storage_helper`, `built_in_adapter`, `replicas`, `volumes`, `node_selector`, `tolerations`, `affinity`, `image_pull_secrets`, `worker_spec` |
| TrainedModel | `inference_service`, `model` (`framework`, `storage_uri`, `memory`) |
| ClusterStorageContainer | `container`, `supported_uri_formats`, `multi_model_download` (`supportsMultiModelDownload`), `workload_type`; `disabled` sets the top-level `disabled` field |
| LocalModelCache | `source_model_uri`, `model_size`, `node_groups` |
| LocalModelNodeGroup | `persistent_volume_spec`, `persistent_volume_claim_spec`, `storage_limit` |
| LLMInferenceService, LLMInferenceServiceConfig | `model` (`uri`, `name`, `lora`), `replicas`, `parallelism` (`data`, `data_local`, `data_rpc_port`, `pipeline`, `tensor`, `expert`), `prefill` (`replicas`, `parallelism`, `template`), `worker`, `router`, `base_refs`, `template`. `template`, `worker` and `prefill.template` are PodSpecs. |

Values under these keys pass through unchanged, except:

| Input | Result |
|---|---|
| `model_format: <name>` | `modelFormat: {name: <name>}` |
| InferenceGraph step keys `service_name`, `node_name`, `service_url`, `map_predictions_to_instances` | `serviceName`, `nodeName`, `serviceUrl`, `mapPredictionsToInstances`; other step keys (`name`, `dependency`, `weight`, `condition`, `data`) pass through |
| `image_pull_secrets: [<name>]`, `base_refs: [<name>]` | `[{name: <name>}]` |
| runtime `containers` whose first entry has no `name` | that container is named `kserve-container` |
| `persistent_volume_spec` without a matching PVC field | `persistentVolumeClaimSpec` gets `accessModes`, `storageClassName` and `resources.requests.storage` (from `capacity.storage`) of the PV spec; `storageClassName: ""` if the PV has none |

The controller merges an InferenceService's `predictor.model` into the runtime container named `kserve-container` ([`InferenceServiceContainerName`](https://github.com/kserve/kserve/blob/v0.21.0/pkg/constants/constants.go#L507), [predictor.go](https://github.com/kserve/kserve/blob/v0.21.0/pkg/controller/v1beta1/inferenceservice/components/predictor.go#L452)), and a container without a name fails the CRD schema, so the default only fills a gap the API server would reject. It applies to `spec.containers` too. The controller binds the node group's PVC to its PV by `volumeName` ([utils.go](https://github.com/kserve/kserve/blob/v0.21.0/pkg/controller/v1alpha1/localmodel/reconcilers/utils.go#L623)); the empty class keeps the cluster's default StorageClass off a PVC whose PV has none, which would otherwise never bind.

`protocol_version(s)`, `scale_metric`, `router_type` and `workload_type` are checked against the CRD enums at compile time. Model format names and the TrainedModel `framework` are free strings in the CRD and pass unchecked; the installed runtimes decide what is served. `model.criticality` and `model.lora.adapters[].criticality` of the LLM kinds no longer exist in `v1alpha2` and are dropped with a warning, so inventories written for `v1alpha1` still compile.

Exposure: InferenceServices are externally visible through the cluster's ingress unless labelled `networking.kserve.io/visibility: cluster-local`. The generator sets no `router` on LLM kinds; `router: {route: {}}` creates an HTTPRoute on the Gateway configured in the KServe operator, which is often an external one.

### Example

```yaml
parameters:
  generators:
    kserve:
      namespace: ml-serving
      serving_runtimes:
        sklearn-runtime:
          containers:
            - image: kserve/sklearnserver:v0.21.0
              args:
                - --model_name={{.Name}}
                - --model_dir=/mnt/models
                - --http_port=8080
          supported_model_formats:
            - name: sklearn
              version: "1"
              autoSelect: true
          protocol_versions: [v1, v2]
      inference_services:
        sklearn-iris:
          predictor:
            min_replicas: 1
            max_replicas: 3
            model:
              model_format: sklearn
              runtime: sklearn-runtime
              protocol_version: v2
              storage_uri: s3://models/sklearn/iris/v1
        sklearn-iris-v2:
          predictor:
            min_replicas: 1
            model:
              model_format: sklearn
              runtime: sklearn-runtime
              protocol_version: v2
              storage_uri: s3://models/sklearn/iris/v2
      inference_graphs:
        iris-split:
          nodes:
            root:
              router_type: Splitter
              steps:
                - service_name: sklearn-iris
                  weight: 80
                - service_name: sklearn-iris-v2
                  weight: 20
      llm_inference_service_configs:
        vllm-gpu:
          template:
            containers:
              - name: main
                resources:
                  limits:
                    nvidia.com/gpu: "1"
      llm_inference_services:
        llama-chat:
          base_refs: [vllm-gpu]
          model:
            uri: hf://meta-llama/Llama-3.1-8B-Instruct
            name: meta-llama/Llama-3.1-8B-Instruct
          replicas: 2
```

`tests/fixtures/inventory/targets/complete.yml` covers every kind, including multi-model serving with a TrainedModel and a local model cache.

## Schemas

`schemas/serving.kserve.io` holds the JSON Schemas of the KServe 0.21.0 CRDs (Apache-2.0), closed against unknown fields; `schemas/sources.yaml` names the CRD files.
