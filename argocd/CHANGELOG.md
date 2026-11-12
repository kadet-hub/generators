# Changelog

## 1.2.0

Built for Argo CD 3.6.1.

- `install` renders the release manifest of Argo CD 3.6.1 instead of 3.5.6. Against 3.5.6 it adds the headless Service `argocd-application-controller`, optional environment variables read from `argocd-cmd-params-cm`, `update` on `*/finalizers` for the server's ClusterRole and the `argocd-tls-certs-cm` mount of the application controller. The images move to `quay.io/argoproj/argocd:v3.6.1`, `ghcr.io/dexidp/dex:v2.46.0` and `public.ecr.aws/docker/library/redis:8.10.1-alpine`, pinned by digest. An installation that comes from 3.5 follows Argo CD's [3.5 to 3.6 upgrade notes](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/operator-manual/upgrading/3.5-3.6.md). A mutate patch that sets `ARGOCD_REPO_OTLP_HEADERS` on the repo server, for example, has to use `ARGOCD_REPO_SERVER_OTLP_HEADERS` now.
- The schemas and CRDs gain `directory.disableExtensionFilter` on Application sources and the `oci` generator of ApplicationSets, and remove no field. `source`, `sources` and `generators` pass through, so inventories can set them.
- The sidecar of `install.cmp` is unchanged, and the repo server's pod still mounts no service account token.
- The upstream files the README cites have the same content at v3.6.1, and their links move to that tag. `argocd-cm.yaml` and `GetDestinationServer` moved to other lines.

Output of inventories without `install` is unchanged.

## 1.1.0

New `install` key: renders Argo CD 3.5.6 from its release manifest `manifests/install.yaml`, one file per object under `install/`, with the namespace set and every image pinned by digest. `install.cmp` adds a Kapitan config management plugin to the repo server: a sidecar running Kapitan 0.36.3 by digest, without a service account token, and the ConfigMap `kapitan-plugin` with its `plugin.yaml`. The manifest grants Argo CD cluster-wide `*` rules, so the generator now declares the `rbac-admin` output capability. Output of inventories without `install` is unchanged. Spec: `docs/specs/argocd.md`.

## 1.0.4

Built for Argo CD 3.5.6. The Application, ApplicationSet and AppProject CRDs are unchanged from 3.5.5, so the shipped schemas and rendered output are unchanged. The upstream files the README cites are identical at v3.5.6, and their links move to that tag.

## 1.0.3

Built for Argo CD 3.5.5, a bug fix release whose Application, ApplicationSet and AppProject CRDs are unchanged from 3.5.4. Rendered output is unchanged.

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Argo CD 3.5.4. Ships the Application, ApplicationSet and AppProject CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Breaking: Applications no longer default `project` to `default`, because that AppProject permits every repository, cluster and resource kind, and the generator does not grant that without an explicit opt-in. An Application without `project` now fails QA-7; the Kubernetes API rejects it as well, since the CRD requires the field. Fix: `project: default` in the inventory restores the old output.
- New shorthand `destination: <namespace>` for an Application in the local cluster, and a destination without `server` and `name` gets `server: https://kubernetes.default.svc`, since Argo CD rejects it otherwise (sources in README.md).
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. Target `complete` covers the Kapitan topic path by publishing and consuming the `argocd` topic itself, and the precedence `spec` < flat keys.
