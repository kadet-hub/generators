# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Kyverno 1.19.1. Ships the CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7).
- Emits the storage versions `kyverno.io/v1` and `kyverno.io/v2`, which Kyverno 1.19.1 marks deprecated in favour of the `policies.kyverno.io` CEL kinds; the API server prints a deprecation warning, and the CEL kinds are planned as a follow-up.
- `match_kinds: [<kind>, ...]`, so far only accepted on rules, now also works on PolicyException, ClusterCleanupPolicy and CleanupPolicy and expands to `match.any[].resources.kinds`. It overrides `spec.match` and logs a warning.
- No defaults are added; `validationFailureAction` stays at Kyverno's default `Audit` unless set.
- The README documents that the reclass-rs backend strips the `=` of Kyverno equality anchors such as `=(field)`.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
