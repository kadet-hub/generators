# Changelog

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- `spec.httpTransport` passthrough fields such as `tls` survive `transport_type: http`; before, the flat keys replaced the whole block.
- `spec.transportType` and `spec.deployment.port` from the passthrough now feed the defaults: `http` from `spec` still gets `targetPort`, and the derived `targetPort` follows a `spec` port.
- The collision warning names the overridden field (`deployment.image`, `http_transport.target_path`, ...) and no longer fires when `deployment` and `spec.deployment` set different fields.
- Ships the upstream kmcp v0.4.0 CRD schema under `schemas/` for QA-7.
