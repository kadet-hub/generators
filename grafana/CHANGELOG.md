# Changelog

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Grafana Operator 5.25.0 (`grafana.integreatly.org/v1beta1`). Ships the CRD schemas of that release under `schemas/`, Apache-2.0; the kadet-hub gate validates the compiled output against them (QA-7).
- Every entry accepts `spec`, passed through unchanged. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
- New defaults and shorthands, documented with their sources in the README:
  - generator-wide `instance_selector`, used by every entry without its own;
  - `instance_selector` as a plain label map expands to `{matchLabels: ...}`;
  - MuteTiming and NotificationTemplate get `spec.name` from the entry key; the CRD requires it.
- Every kind with an `instanceSelector` now fails the compile without one; before, LibraryPanel, MuteTiming and NotificationTemplate rendered resources the CRD rejects.
- Grafana instance fixes. Inventories still compile; the output of every instance changes:
  - Persistence mounted a claim `<name>-grafana-pvc` on `/var/lib/grafana` that the operator never creates, so the pod stayed Pending while the operator's claim `<name>-pvc` went unused. It now replaces the operator's `grafana-data` volume with its claim `<name>-pvc`, sets `strategy: Recreate` for the ReadWriteOnce volume, and leaves `storageClassName` out unless `persistence.storageclass` is set; `""` disabled dynamic provisioning.
  - The Ingress pointed at a Service `<name>-grafana-service` that does not exist. It now uses the operator's `<name>-service` on `server.http_port` (default 3000), and `ingress.hostname` is required.
  - Breaking: no default image `grafana/grafana` (the `latest` tag) any more. It overrode both the operator's pinned default and `spec.version`. Fix: `image: grafana/grafana` restores the old output.
  - Breaking: the `grafana` container no longer gets `securityContext` (`runAsUser: 1001`, `runAsGroup: 0`, ...) or `readinessProbe.failureThreshold: 3`; the operator's defaults apply (user and group 10001, read-only root filesystem, `failureThreshold: 1`). Persistence sets `fsGroup: 10001` instead of `1001`. Fix: set the old values under `spec.deployment.spec.template.spec.containers` for the container `grafana`, and `fsGroup` under `spec.deployment.spec.template.spec.securityContext`. On OpenShift the operator already leaves `runAsUser` and `runAsGroup` unset so the namespace UID range applies; `spec.disableDefaultSecurityContext: Container` removes its container defaults entirely.
- Breaking: ContactPoint `type`, `settings`, `uid`, `values_from` and `disable_resolve_message` now produce one `spec.receivers` entry instead of the top-level fields that Grafana Operator 5.25.0 marks deprecated. Inventories need no change; flat `receivers` wins over these keys and logs a warning.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
