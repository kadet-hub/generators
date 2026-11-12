# Argo CD Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/argocd/) page.

Kapitan kadet generator for [Argo CD](https://argo-cd.readthedocs.io/) resources (`argoproj.io/v1alpha1`). Built for Argo CD 3.6.1.

- **Application**: one source or several, synced to a destination cluster and namespace
- **ApplicationSet**: Applications templated from generators (clusters, git, list, matrix, ...)
- **AppProject**: allowed source repositories, destinations and resource kinds for a group of Applications
- **Applications from Kapitan topics**: one Application per target that publishes the `argocd` topic
- **Argo CD itself** (opt-in): the release manifest, optionally with a Kapitan config management plugin in the repo server

Cluster and repository credentials are Secrets with the `argocd.argoproj.io/secret-type` label; render them with the `kubernetes` generator. Spec: [docs/specs/argocd.md](../docs/specs/argocd.md).

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
| `install` | Argo CD's release manifest, see [Installing Argo CD](#installing-argo-cd) | `install/<name>-<kind>` |
| `install.cmp` | the Kapitan plugin, see [Kapitan config management plugin](#kapitan-config-management-plugin) | `install/kapitan-plugin-configmap` |

Every entry accepts `name` (default: the entry key), `namespace`, `labels`, `annotations` and a `spec` dict that passes through to the resource `spec`. Precedence is generator defaults < `spec` < flat keys: a flat key wins over the same field in `spec` and logs `Flat key '<key>' overrides spec passthrough '<field>' for resource '<name>'`.

`parameters.namespace` is not read: Argo CD reconciles these resources only in its control-plane namespace unless [apps in any namespace](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/operator-manual/app-any-namespace.md) is enabled.

Flat keys map to the camelCase CRD field of the same name; values pass through unchanged.

| Kind | Flat keys |
|---|---|
| Application | `project`, `destination`, `source`, `sources`, `sync_policy`, `ignore_differences`, `revision_history_limit`, `cascade_delete` |
| ApplicationSet | `generators`, `template`, `template_patch`, `sync_policy`, `go_template`, `go_template_options`, `ignore_application_differences` |
| AppProject | `source_repos`, `destinations`, `cluster_resource_whitelist`, `namespace_resource_blacklist`, `namespace_resource_whitelist`, `orphaned_resources`, `roles`, `finalizers` |

`cascade_delete: true` adds the `resources-finalizer.argocd.argoproj.io` finalizer to an Application, so deleting it also deletes the resources it deployed ([app deletion](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/user-guide/app_deletion.md)). AppProjects get a finalizer only through `finalizers`.

### Defaults and shorthands

| Input | Result | Reason |
|---|---|---|
| `destination: <namespace>` | `destination: {namespace: <namespace>, server: https://kubernetes.default.svc}` | The common case, an Application in the cluster Argo CD runs in. |
| a `destination` (flat or in `spec`) without `server` and `name` | `server: https://kubernetes.default.svc` | Argo CD rejects a destination without either ([`GetDestinationServer`](https://github.com/argoproj/argo-cd/blob/v3.6.1/util/argo/argo.go#L1152-L1174)). The address is Argo CD's [in-cluster server](https://github.com/argoproj/argo-cd/blob/v3.6.1/pkg/apis/application/v1alpha1/application_defaults.go#L30-L31). |

A destination with `name` keeps it and gets no `server`. The in-cluster address only works while `cluster.inClusterEnabled` in `argocd-cm` is on, which is the [default](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/operator-manual/argocd-cm.yaml#L417-L418).

Deliberately not defaulted:

- `project` has no default and the compile fails QA-7 without it. The `default` AppProject that ships with Argo CD permits every repository, cluster and resource kind ([projects](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/user-guide/projects.md#the-default-project)); write `project: default` to use it.
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

### Installing Argo CD

`install: {}` renders Argo CD 3.6.1 from its release manifest [`manifests/install.yaml`](https://github.com/argoproj/argo-cd/blob/v3.6.1/manifests/install.yaml), one file per object under `install/`. The objects are upstream's with three changes: namespaced objects get the generator's `namespace` (`argocd` if unset), the ServiceAccount subjects of the ClusterRoleBindings move to that namespace, and every image is pinned by digest. A target drops an installation that a class sets with `install: null`.

The generator renders no Namespace, as the manifest has none. The ApplicationSet CRD is too large for the annotation of a client-side apply, so apply server-side:

```sh
kubectl create namespace argocd
kubectl apply --server-side -f compiled/<target>/manifests/install/
```

The manifest grants the application controller and the server every verb on every resource through ClusterRoles, so the generator declares the `rbac-admin` output capability. Settings such as `argocd-cm` data, replicas or a mirror registry for the images go in with the [mutate](../mutate/) generator on the compile entry's output; the generator has no keys for them. The pinned source, its checksums and how to vendor a newer release are in the spec.

### Kapitan config management plugin

`install.cmp` lets Argo CD compile a Kapitan project itself. It adds the container `kapitan` to the `argocd-repo-server` Deployment and renders the ConfigMap `kapitan-plugin` with the plugin's `plugin.yaml`. Container, volumes and plugin are those of the [argocd-cmp](https://github.com/kadet-hub/examples/tree/main/argocd-cmp) example in kadet-hub/examples.

| Key | Default |
|---|---|
| `install.cmp.image` | `docker.io/kapicorp/kapitan:0.36.3@sha256:04b9ca04f5041851631fb1041fbafe37b1ca6c3ad99a81d6ccd40f5ebd20f857`; another image must be pinned by digest, or the compile fails |
| `install.cmp.resources` | none; the container's `resources` as written |

The sidecar runs as user 999 with a read-only root filesystem, no privilege escalation and every capability dropped. The repo server's pod mounts no service account token, and the compile fails if the manifest turns it on, so the plugin has no identity in the cluster. The manifest's NetworkPolicies limit ingress only, so the sidecar reaches the internet and every Service until an egress policy for the repo server's pod limits it, as `repo-server-egress.yaml` of the example does.

The plugin runs code from every repository it renders: kadet generators are Python, and Jinja2 templates render outside a sandbox. Everyone who can push to a branch an Application tracks runs code in the sidecar, so protect those branches as you would a CI job.

An Application selects the plugin and the Kapitan target in its `source`. `path` is the directory that holds `.kapitan`. The plugin compiles `-t <TARGET>` without `--fetch`, so the repository holds `lib/` and anything else the target fetches. It prints every YAML file below `compiled/<TARGET>` and fails when there is none, so an Application with automated prune never syncs an empty desired state.

```yaml
parameters:
  generators:
    argocd:
      install:
        cmp: {}
      applications:
        blackbox-exporter:
          project: apps
          destination: blackbox-exporter
          source:
            repoURL: https://git.example.com/platform/apps.git
            targetRevision: main
            path: .
            plugin:
              name: kapitan
              env:
                - name: TARGET
                  value: blackbox-exporter
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
