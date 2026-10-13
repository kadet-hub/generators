# Crossplane Generator

Published on [kadet-hub](https://kadet-hub.org/generators/crossplane/): pin a released version by digest from its catalog page.

Kapitan kadet generator for [Crossplane](https://www.crossplane.io/) v2 resources. Built for Crossplane 2.4.2 and Crossplane Provider AWS 2.9.0:

- **Provider**, **Function** (`pkg.crossplane.io/v1`): packages, pinned by version or digest
- **CompositeResourceDefinition** (`apiextensions.crossplane.io/v2`): the API of a composite resource (XR)
- **Composition** (`apiextensions.crossplane.io/v1`): a function pipeline for an XRD
- **ProviderConfig**, **ClusterProviderConfig** (the provider's group, for example `aws.m.upbound.io/v1beta1`): provider credentials from a Secret

The generator targets Crossplane v2 only. XRDs use `apiextensions.crossplane.io/v2`, which Crossplane 2.4.2 serves next to the deprecated v1 ("CompositeResourceDefinition v1 is deprecated ... consider migrating to v2"). v1 remains the storage version; the CRD defines no conversion webhook, so the API server stores v2 objects under v1 unchanged apart from `apiVersion`. v2 XRDs are namespaced by default and reject `claimNames` and `connectionSecretKeys` ([CRD at v2.4.2](https://github.com/crossplane/crossplane/blob/v2.4.2/cluster/crds/apiextensions.crossplane.io_compositeresourcedefinitions.yaml)), so the generator renders no claims: namespaced XRs replace them ([What's new in v2](https://docs.crossplane.io/v2.4/whats-new/#namespaced-composite-resources)). Legacy cluster-scoped XRDs with claims need a `copy` input. XR instances, DeploymentRuntimeConfigs and the RBAC a provider may need are not rendered; RBAC and Secrets belong in the `kubernetes` generator.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/crossplane@sha256:<digest>
        output_path: lib/crossplane
    compile:
      - output_path: manifests/crossplane/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/crossplane
```

### Inventory Contract

All keys live under `parameters.generators.crossplane`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace of ProviderConfigs. Falls back to `parameters.namespace`, then `default`. |
| `providers.<name>` | Provider | `<name>-provider` |
| `functions.<name>` | Function | `<name>-function` |
| `composite_resource_definitions.<plural>.<group>` | CompositeResourceDefinition | `<plural>.<group>-xrd` |
| `compositions.<name>` | Composition | `<name>-composition` |
| `provider_configs.<name>` | ProviderConfig | `<namespace>/<name>-providerconfig` |
| `provider_configs.<name>` with `kind: ClusterProviderConfig` | ClusterProviderConfig | `<name>-clusterproviderconfig` |

Every resource accepts `labels`, `annotations` and `spec`. Precedence is generator defaults < `spec` < flat keys and shorthands: `spec` is deep-merged over the defaults, then the flat keys are applied, and a flat key that overrides a `spec` value logs "Flat key '...' overrides spec passthrough '...' for resource '...'".

| Kind | Flat keys (snake_case of the CRD field, value verbatim) | Shorthands |
|---|---|---|
| Provider, Function | `package_pull_policy`, `package_pull_secrets`, `revision_activation_policy`, `revision_history_limit`, `skip_dependency_resolution`, `ignore_crossplane_constraints`, `common_labels`, `common_annotations` | `package` with `version`, `digest` or both; `runtime_config: <name>` |
| CompositeResourceDefinition | `scope`, `versions`, `default_composition_update_policy` | `kind`; `version` with `spec_schema`, `status_schema`; `default_composition`, `enforced_composition` |
| Composition | `composite_type_ref`, `pipeline` | `xrd`; step `function` |
| ProviderConfig | `kind` (`ProviderConfig` or `ClusterProviderConfig`), `namespace` | `api_version` (required); `credentials_secret` |

### Shorthands and derived values

| Input | Result | Source |
|---|---|---|
| `package: <image>`, `version: <tag>` | `spec.package: <image>:<tag>` | |
| `package: <image>`, `digest: sha256:<hex>` (with `version`: `<image>:<tag>@sha256:<hex>`) | `spec.package: <image>@sha256:<hex>` | [Installation options](https://docs.crossplane.io/v2.4/packages/providers/#installation-options) |
| `runtime_config: <name>` | `runtimeConfigRef: {name: <name>}` | |
| key `<plural>.<group>` of an XRD | `metadata.name`, `spec.group`, `spec.names.plural` | [XRD names](https://docs.crossplane.io/v2.4/composition/composite-resource-definitions/#xrd-names): the name must be `<plural>.<group>` |
| `kind: <Kind>` | `spec.names.kind` | |
| `version: <v>`, `spec_schema`, `status_schema` (not together with `versions`) | `versions: [{name: <v>, served: true, referenceable: true, schema: {openAPIV3Schema: {type: object, properties: {spec: ..., status: ...}}}}]` | [Serve and reference a schema](https://docs.crossplane.io/v2.4/composition/composite-resource-definitions/#serve-and-reference-a-schema): one version must be `referenceable` |
| `default_composition: <name>`, `enforced_composition: <name>` | `defaultCompositionRef`, `enforcedCompositionRef: {name: <name>}` | |
| Composition `xrd: <plural>.<group>` | `compositeTypeRef` with `<group>/<referenceable version>` and the kind of that XRD in the same inventory | [Match composite resources](https://docs.crossplane.io/v2.4/composition/compositions/#match-composite-resources) |
| step `function: <name>` | `functionRef: {name: <name>}`, `step: <name>` unless `step` is set; the compile fails without steps or with duplicate step names (`pipeline` is a list map keyed by `step` in the [Composition CRD](https://github.com/crossplane/crossplane/blob/v2.4.2/cluster/crds/apiextensions.crossplane.io_compositions.yaml)) | |
| `credentials_secret: {name, key[, namespace]}` | `credentials: {source: Secret, secretRef: {namespace, name, key}}`; `namespace` is required for a ClusterProviderConfig; a namespaced ProviderConfig uses its own namespace, and another `namespace` fails the compile, because provider-upjet-aws replaces it with the managed resource's namespace ([pc_resolver.go at v2.9.0](https://github.com/crossplane-contrib/provider-upjet-aws/blob/v2.9.0/internal/clients/pc_resolver.go#L48-L64)) | [Provider configuration](https://docs.crossplane.io/v2.4/packages/providers/#provider-configuration) |

The generator emits no `mode` (the Composition CRD defaults it to `Pipeline`, its only value), no XRD `scope` (defaults to `Namespaced`) and no package pull, activation or history defaults ([CRDs at v2.4.2](https://github.com/crossplane/crossplane/tree/v2.4.2/cluster/crds)).

Packages must be fully qualified and pinned: the compile fails when the final `spec.package` does not match the CRD's CEL rule `^[^\.\/]+(\.[^\.\/]+)+(\/[^\/:@]+)+(:[^:@]+(@sha256.+)?|@sha256.+)$` (a registry host with a dot, then a tag, `tag@sha256:...` or `@sha256:...`; [Provider CRD at v2.4.2](https://github.com/crossplane/crossplane/blob/v2.4.2/cluster/crds/pkg.crossplane.io_providers.yaml)), or when the tag is `latest` without a digest. Crossplane v2 has no default registry ([Default registry flag](https://docs.crossplane.io/v2.4/guides/upgrade-to-crossplane-v2/#default-registry-flag)). Tags are allowed but mutable: whoever controls the registry can move a tag and change what runs in the cluster, so prefer `digest`, optionally with `version` for readability.

A ProviderConfig carries only the name of a Secret, never its content. `api_version` has no default because each provider defines its own ProviderConfig and authentication options; anything other than a Secret (IRSA, workload identity) goes in `spec.credentials`. The schemas ship for `aws.m.upbound.io` only; ProviderConfigs of other providers compile, and the gate lists them for review instead of validating them.

### Example

```yaml
parameters:
  generators:
    crossplane:
      namespace: team-a
      providers:
        crossplane-contrib-provider-aws-s3:
          package: xpkg.crossplane.io/crossplane-contrib/provider-aws-s3
          version: v2.9.0
      functions:
        function-patch-and-transform:
          package: xpkg.crossplane.io/crossplane-contrib/function-patch-and-transform
          version: v0.11.0
        function-auto-ready:
          package: xpkg.crossplane.io/crossplane-contrib/function-auto-ready
          version: v0.7.0
      composite_resource_definitions:
        buckets.platform.example.com:
          kind: Bucket
          version: v1alpha1
          spec_schema:
            type: object
            properties:
              region:
                type: string
            required:
              - region
      compositions:
        buckets-aws:
          xrd: buckets.platform.example.com
          pipeline:
            - function: function-patch-and-transform
              input:
                apiVersion: pt.fn.crossplane.io/v1beta1
                kind: Resources
                resources:
                  - name: bucket
                    base:
                      apiVersion: s3.aws.m.upbound.io/v1beta1
                      kind: Bucket
                      spec:
                        providerConfigRef:
                          kind: ProviderConfig
                          name: team-a
                    patches:
                      - type: FromCompositeFieldPath
                        fromFieldPath: spec.region
                        toFieldPath: spec.forProvider.region
            - function: function-auto-ready
      provider_configs:
        team-a:
          api_version: aws.m.upbound.io/v1beta1
          credentials_secret:
            name: aws-credentials
            key: credentials
```

Function `input` is passed through unchanged; its schema belongs to the function, so the gate does not check it.
