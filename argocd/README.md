# Argo CD Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/argocd/) page.

Kapitan kadet generator for [Argo CD](https://argo-cd.readthedocs.io/) resources (`argoproj.io/v1alpha1`). Built for Argo CD 3.5.5.

- **Application**: one source or several, synced to a destination cluster and namespace
- **ApplicationSet**: Applications templated from generators (clusters, git, list, matrix, ...)
- **AppProject**: allowed source repositories, destinations and resource kinds for a group of Applications
- **Applications from Kapitan topics**: one Application per target that publishes the `argocd` topic

Cluster and repository credentials are Secrets with the `argocd.argoproj.io/secret-type` label; render them with the `kubernetes` generator. The Argo CD installation itself belongs in the `helm` input.

## Usage

### Kapitan Configuration

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/argocd@sha256:<digest>
        output_path: lib/argocd
    compile:
      - output_path: manifests/
        input_type: kadet
        output_type: yml
        input_paths:
          - lib/argocd
```

### Inventory Contract

All keys live under `parameters.generators.argocd`.

| Key | Kind | Output key |
|---|---|---|
| `namespace` | | Default namespace of all resources, `argocd` if unset. |
| `applications.<name>` | Application | `<namespace>/<name>-application` |
| `topics.<topic>` | Application per publishing target | `<namespace>/<target>-application` |
| `application_sets.<name>` | ApplicationSet | `<namespace>/<name>-appset` |
| `projects.<name>` | AppProject | `<namespace>/<name>-appproject` |

Every entry accepts `name` (default: the entry key), `namespace`, `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. Precedence is generator defaults < `spec` < flat keys: a flat key wins over the same field in `spec` and logs `Flat key '<key>' overrides spec passthrough '<field>' for resource '<name>'`.

`parameters.namespace` is not read: Argo CD reconciles these resources only in its control-plane namespace unless [apps in any namespace](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/app-any-namespace.md) is enabled.

Flat keys map to the camelCase CRD field of the same name; values pass through unchanged.

| Kind | Flat keys |
|---|---|
| Application | `project`, `destination`, `source`, `sources`, `sync_policy`, `ignore_differences`, `revision_history_limit`, `cascade_delete` |
| ApplicationSet | `generators`, `template`, `template_patch`, `sync_policy`, `go_template`, `go_template_options`, `ignore_application_differences` |
| AppProject | `source_repos`, `destinations`, `cluster_resource_whitelist`, `namespace_resource_blacklist`, `namespace_resource_whitelist`, `orphaned_resources`, `roles`, `finalizers` |

`cascade_delete: true` adds the `resources-finalizer.argocd.argoproj.io` finalizer to an Application, so deleting it also deletes the resources it deployed ([app deletion](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/user-guide/app_deletion.md)). AppProjects get a finalizer only through `finalizers`.

### Defaults and shorthands

| Input | Result | Reason |
|---|---|---|
| `destination: <namespace>` | `destination: {namespace: <namespace>, server: https://kubernetes.default.svc}` | The common case, an Application in the cluster Argo CD runs in. |
| a `destination` (flat or in `spec`) without `server` and `name` | `server: https://kubernetes.default.svc` | Argo CD rejects a destination without either ([`GetDestinationServer`](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/argo/argo.go#L1089-L1111)). The address is Argo CD's [in-cluster server](https://github.com/argoproj/argo-cd/blob/v3.5.5/pkg/apis/application/v1alpha1/application_defaults.go#L30-L31). |

A destination with `name` keeps it and gets no `server`. The in-cluster address only works while `cluster.inClusterEnabled` in `argocd-cm` is on, which is the [default](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/argocd-cm.yaml#L364-L365).

Deliberately not defaulted:

- `project` has no default and the compile fails QA-7 without it. The `default` AppProject that ships with Argo CD permits every repository, cluster and resource kind ([projects](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/user-guide/projects.md#the-default-project)); write `project: default` to use it.
- `sync_policy` is not set, so Applications sync manually. Automated sync with `prune` or `selfHeal` lets the Git repository delete and overwrite cluster resources; set it per Application.
- AppProjects get no `source_repos` or `destinations`, which denies everything until the inventory lists them.
- ApplicationSets keep Argo CD's template engine unless `go_template` is set; switching changes the placeholder syntax from `{{name}}` to `{{.name}}`.

### Applications from Kapitan topics

A workload target publishes its Application parameters to a topic, and the Argo CD target turns every publisher into one Application. Topic parameters use the keys of an `applications` entry and are deep-merged over `generators.argocd.topics.<topic>`; a string `destination` replaces the default destination as a whole. The Application is named after the publishing target unless the parameters set `name`. Kapitan fails the compile if the Argo CD target does not declare `consume: true`, and the generator fails it if an `applications` entry has the same name and namespace.

Workload target `web`:

<!-- notest: needs the consuming target -->
```yaml
parameters:
  kapitan:
    topics:
      argocd:
        parameters:
          source:
            path: compiled/web/manifests
          destination: web
```

### Example

The Argo CD target, consuming the topic above:

```yaml
parameters:
  kapitan:
    topics:
      argocd:
        consume: true
  generators:
    argocd:
      topics:
        argocd:
          project: platform
          source:
            repoURL: https://git.example.com/platform/deploy.git
            targetRevision: main
      projects:
        platform:
          source_repos:
            - https://git.example.com/platform/deploy.git
            - https://charts.example.com
          destinations:
            - namespace: web
              server: https://kubernetes.default.svc
            - namespace: shop
              server: https://kubernetes.default.svc
          cluster_resource_whitelist:
            - group: ''
              kind: Namespace
          roles:
            - name: developer
              policies:
                - p, proj:platform:developer, applications, sync, platform/*, allow
              groups:
                - platform-developers
        addons:
          source_repos:
            - https://git.example.com/platform/cluster-addons.git
          destinations:
            - namespace: kube-system
              server: '*'
      applications:
        shop:
          project: platform
          destination: shop
          sources:
            - repoURL: https://charts.example.com
              chart: shop
              targetRevision: 2.4.1
              helm:
                valueFiles:
                  - $values/values/shop/production.yaml
            - repoURL: https://git.example.com/platform/deploy.git
              targetRevision: main
              ref: values
          sync_policy:
            automated:
              prune: true
              selfHeal: true
            syncOptions:
              - CreateNamespace=true
      application_sets:
        cluster-addons:
          generators:
            - clusters: {}
          go_template: true
          go_template_options:
            - missingkey=error
          template:
            metadata:
              name: '{{.name}}-addons'
            spec:
              project: addons
              source:
                repoURL: https://git.example.com/platform/cluster-addons.git
                targetRevision: main
                path: 'clusters/{{.name}}'
              destination:
                server: '{{.server}}'
                namespace: kube-system
```

This renders `argocd/platform-appproject`, `argocd/addons-appproject`, `argocd/web-application` (from the topic, in-cluster, namespace `web`), `argocd/shop-application` and `argocd/cluster-addons-appset`.
