# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the OpenTelemetry Operator 0.160.0 CRD schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7). Fixtures set `parameters.kapitan.vars.target`.

New shorthand and defaults, overridable from the inventory and documented with sources in the README:

- Collector `target_allocator: <name>` sets the label `opentelemetry.io/target-allocator: <name>` that links a standalone TargetAllocator. A dict still passes through as the embedded `targetAllocator`.
- A collector that uses a target allocator and sets no `mode` gets `mode: statefulset`. Previously the operator defaulted it to `deployment`, which the target allocator does not support. Set `mode` explicitly to keep a different mode.
