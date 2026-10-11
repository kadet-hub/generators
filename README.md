# kadet-hub generators

Kapitan kadet generators published on [kadet-hub](https://kadet-hub.org).

| Generator | Renders |
|---|---|
| [external-secrets](external-secrets/) | External Secrets Operator SecretStores, ClusterSecretStores and ExternalSecrets |
| [keda](keda/) | KEDA ScaledObjects, ScaledJobs and TriggerAuthentications |

Each directory is one generator with its own manifest (`kapitan-generator.yaml`),
changelog and fixture project under `tests/fixtures`. Releases are tagged
`<generator>-v<semver>`. To use one, pin it by digest as described in
[Using marketplace generators](https://github.com/kadet-hub/registry/blob/main/docs/consumers.md).
