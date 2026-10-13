# Flux Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/flux/) page.

Kapitan kadet generator for [Flux](https://fluxcd.io/flux/components/) sources and the objects that consume them. Built for Flux 2.9.6, which pins source-controller 1.9.6, kustomize-controller 1.9.6 and helm-controller 1.6.5 ([manifests/bases](https://github.com/fluxcd/flux2/tree/v2.9.6/manifests/bases)).

- **GitRepository**, **OCIRepository**, **HelmRepository** (`source.toolkit.fluxcd.io/v1`)
- **Kustomization** (`kustomize.toolkit.fluxcd.io/v1`): applies a directory of a Git or OCI source
- **HelmRelease** (`helm.toolkit.fluxcd.io/v2`): installs a chart from a HelmRepository, GitRepository or OCIRepository

Each consumer names its source with `source: <name>`; the generator looks the name up among the sources of the same inventory and writes the matching `sourceRef`, `chart.spec` or `chartRef`. Flux itself is installed with `flux bootstrap` or the `helm` input; Secrets for `secret_ref` belong in the `kubernetes` generator; pass secret chart values through `values_from` with a Secret rather than inline `values`, which land in the compiled output.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/flux@sha256:<digest>
        output_path: lib/flux
    compile:
      - output_path: manifests/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/flux
```

### Inventory Contract

All keys live under `parameters.generators.flux`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace of all resources, `flux-system` if unset, as in the [Flux CLI](https://github.com/fluxcd/flux2/blob/v2.9.6/pkg/manifestgen/install/options.go#L45). |
| `git_repositories.<name>` | GitRepository | `<namespace>/<name>-gitrepository` |
| `oci_repositories.<name>` | OCIRepository | `<namespace>/<name>-ocirepository` |
| `helm_repositories.<name>` | HelmRepository | `<namespace>/<name>-helmrepository` |
| `kustomizations.<name>` | Kustomization | `<namespace>/<name>-kustomization` |
| `helm_releases.<name>` | HelmRelease | `<namespace>/<name>-helmrelease` |

Every entry accepts `namespace`, `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. Precedence is generator defaults < `spec` < flat keys: a flat key wins over the same field in `spec` and logs `Flat key '<key>' overrides spec passthrough '<field>' for resource '<name>'`.

Flat keys map to the camelCase spec field of the same name; values pass through unless a shorthand below applies.

| Kind | Flat keys |
|---|---|
| GitRepository | `url`, `ref`, `interval`, `timeout`, `secret_ref`, `ignore` |
| OCIRepository | `url`, `ref`, `interval`, `timeout`, `secret_ref`, `provider`, `layer_selector` |
| HelmRepository | `url`, `type`, `interval`, `timeout`, `secret_ref`, `provider` |
| Kustomization | `source`, `path`, `prune`, `interval`, `retry_interval`, `timeout`, `wait`, `target_namespace`, `depends_on`, `service_account_name`, `post_build`, `patches`, `components` |
| HelmRelease | `source`, `chart`, `version`, `release_name`, `target_namespace`, `interval`, `timeout`, `depends_on`, `service_account_name`, `values`, `values_from`, `install`, `upgrade` |

### Shorthands

| Input | Result |
|---|---|
| `source: <name>` on a Kustomization | `sourceRef: {kind, name}` of the GitRepository or OCIRepository `<name>`, plus `namespace` if it lives in another namespace |
| `source: <name>` on a HelmRelease, HelmRepository or GitRepository source | `chart.spec: {chart, version, sourceRef}`; `chart` defaults to the HelmRelease name for a HelmRepository and is required for a GitRepository, where it is the chart's path |
| `source: <name>` on a HelmRelease, OCIRepository source | `chartRef: {kind: OCIRepository, name}`; the OCIRepository gets the Helm chart `layerSelector` below, and its `ref` selects the chart version |
| `source: {kind, name, namespace}` | used verbatim, for sources defined outside this inventory; a Kustomization accepts GitRepository, OCIRepository, Bucket and ExternalArtifact, a HelmRelease takes OCIRepository, HelmChart or ExternalArtifact as `chartRef` and HelmRepository, GitRepository or Bucket as `chart.spec` |
| `ref: <branch>` on a GitRepository | `ref: {branch: <branch>}` |
| `ref: <tag>` on an OCIRepository | `ref: {tag: <tag>}` |
| `secret_ref: <name>` | `secretRef: {name: <name>}` |
| `depends_on: [<name>, ...]` | `dependsOn: [{name: <name>}, ...]`; dicts pass through |

The compile fails, with a message naming the resource, when:

- a `source` name matches no source or sources of two kinds (use the dict form then), or a dict `source` lacks `kind` or `name`;
- a Kustomization's source is not a GitRepository, OCIRepository, Bucket or ExternalArtifact;
- a HelmRelease ends up with neither or both of `chart` and `chartRef`, sets `chart` or `version` with an OCIRepository source (set its `ref` instead), lacks `chart` with a GitRepository or Bucket source, or has an unquoted numeric `version` such as `1.10`, which YAML reads as `1.1`;
- one OCIRepository serves both a HelmRelease and a Kustomization, since the chart `layerSelector` would hand the Kustomization a chart tarball.

These rules exist because QA-7 and QA-10 do not evaluate the CRDs' CEL rules, such as "either chart or chartRef must be set".

With `--no-cross-namespace-refs=true` on the controllers, a source must live in the namespace of its consumer ([Kustomization](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md?plain=1#L145-L146), [HelmRelease](https://github.com/fluxcd/helm-controller/blob/v1.6.5/docs/spec/v2/helmreleases.md?plain=1#L202-L205)).

### Defaults

| Kind | Field | Default | Source |
|---|---|---|---|
| GitRepository | `interval` | `1m0s` | Kustomization [recommended settings](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md#recommended-settings) |
| OCIRepository | `interval` | `5m` | HelmRelease [recommended settings](https://github.com/fluxcd/helm-controller/blob/v1.6.5/docs/spec/v2/helmreleases.md#recommended-settings) |
| OCIRepository used as a HelmRelease chart | `layerSelector` | `{mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip, operation: copy}` | HelmRelease [recommended settings](https://github.com/fluxcd/helm-controller/blob/v1.6.5/docs/spec/v2/helmreleases.md#recommended-settings); without it the controller extracts the first layer ([layer selector](https://github.com/fluxcd/source-controller/blob/v1.9.6/docs/spec/v1/ocirepositories.md#layer-selector)) |
| HelmRepository with an `oci://` URL | `type` | `oci` | [type](https://github.com/fluxcd/source-controller/blob/v1.9.6/docs/spec/v1/helmrepositories.md#type); the default type only reads HTTP/S repositories |
| Kustomization | `interval`, `retryInterval`, `timeout`, `wait` | `60m0s`, `2m0s`, `3m0s`, `true` | Kustomization [recommended settings](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md#recommended-settings) |
| Kustomization | `prune` | `false` | the CRD requires the field; `false` as in [`flux create kustomization`](https://github.com/fluxcd/flux2/blob/v2.9.6/cmd/flux/create_kustomization.go#L107) |
| HelmRelease | `interval` | `30m` | HelmRelease [recommended settings](https://github.com/fluxcd/helm-controller/blob/v1.6.5/docs/spec/v2/helmreleases.md#recommended-settings) |

The `oci` HelmRepository type is in maintenance mode upstream ([type](https://github.com/fluxcd/source-controller/blob/v1.9.6/docs/spec/v1/helmrepositories.md?plain=1#L156-L158)); prefer an `oci_repositories` entry as the HelmRelease source.

The `interval` defaults matter because the CRDs require the field for every kind except HelmRepository. Controller defaults (HelmRepository `interval` 1m, source `timeout` 60s, HelmRelease `timeout` 5m) are not emitted.

Deliberately not defaulted:

- `prune: true`. With pruning, a Kustomization deletes every object it applied once the object disappears from the source, and deleting the Kustomization deletes them all ([prune](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md#prune)). Set it per Kustomization together with a `path`; without `path` Flux applies the root of the source.
- `ref`. Without it a GitRepository tracks `master` and an OCIRepository the `latest` tag ([Git reference](https://github.com/fluxcd/source-controller/blob/v1.9.6/docs/spec/v1/gitrepositories.md#reference), [OCI reference](https://github.com/fluxcd/source-controller/blob/v1.9.6/docs/spec/v1/ocirepositories.md#reference)).
- `service_account_name`. Without it a Kustomization or HelmRelease applies as cluster admin ([role-based access control](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md#role-based-access-control)) unless the controllers run with `--default-service-account` ([enforcing impersonation](https://github.com/fluxcd/kustomize-controller/blob/v1.9.6/docs/spec/v1/kustomizations.md#enforcing-impersonation)). The account and its RBAC are cluster specific; set it for tenant objects.
- HelmRelease `driftDetection`, `install`/`upgrade` strategies and `upgrade.crds`. The recommended `RetryOnFailure` suits stateful workloads, `RemediateOnFailure` stateless ones, and `CreateReplace` lets a chart replace cluster-wide CRDs; choose per release.

### Example

```yaml
parameters:
  generators:
    flux:
      git_repositories:
        fleet:
          url: https://git.example.com/platform/fleet.git
          ref: main
          secret_ref: fleet-git-token
      oci_repositories:
        podinfo-chart:
          namespace: apps
          url: oci://ghcr.io/stefanprodan/charts/podinfo
          ref:
            semver: ">=6.0.0"
      helm_repositories:
        jetstack:
          url: https://charts.jetstack.io
      kustomizations:
        infrastructure:
          source: fleet
          path: ./clusters/production/infrastructure
          prune: true
        apps:
          source: fleet
          path: ./apps/production
          prune: true
          depends_on:
            - infrastructure
          service_account_name: flux-apps
      helm_releases:
        podinfo:
          namespace: apps
          source: podinfo-chart
          values:
            replicaCount: 2
        cert-manager:
          namespace: cert-manager
          source: jetstack
          version: v1.21.2
          values:
            crds:
              enabled: true
```

This renders `flux-system/fleet-gitrepository`, `apps/podinfo-chart-ocirepository` with the Helm chart layer selector, `flux-system/jetstack-helmrepository`, the Kustomizations `flux-system/infrastructure-kustomization` and `flux-system/apps-kustomization` with `sourceRef: {kind: GitRepository, name: fleet}`, `apps/podinfo-helmrelease` with `chartRef: {kind: OCIRepository, name: podinfo-chart}` and `cert-manager/cert-manager-helmrelease` with `chart.spec: {chart: cert-manager, version: v1.21.2, sourceRef: {kind: HelmRepository, name: jetstack, namespace: flux-system}}`.
