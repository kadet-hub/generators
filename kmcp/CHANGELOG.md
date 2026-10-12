# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- `spec.httpTransport` passthrough fields such as `tls` survive `transport_type: http`; before, the flat keys replaced the whole block.
- `spec.transportType` and `spec.deployment.port` from the passthrough now feed the defaults: `http` from `spec` still gets `targetPort`, and the derived `targetPort` follows a `spec` port.
- The collision warning names the overridden field (`deployment.image`, `http_transport.target_path`, ...) and no longer fires when `deployment` and `spec.deployment` set different fields.
- Ships the upstream kmcp v0.4.0 CRD schema under `schemas/` for QA-7.
