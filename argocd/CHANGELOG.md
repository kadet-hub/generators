# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Argo CD 3.5.4. Ships the Application, ApplicationSet and AppProject CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Breaking: Applications no longer default `project` to `default`, because that AppProject permits every repository, cluster and resource kind, and the generator does not grant that without an explicit opt-in. An Application without `project` now fails QA-7; the Kubernetes API rejects it as well, since the CRD requires the field. Fix: `project: default` in the inventory restores the old output.
- New shorthand `destination: <namespace>` for an Application in the local cluster, and a destination without `server` and `name` gets `server: https://kubernetes.default.svc`, since Argo CD rejects it otherwise (sources in README.md).
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires. Target `complete` covers the Kapitan topic path by publishing and consuming the `argocd` topic itself, and the precedence `spec` < flat keys.
