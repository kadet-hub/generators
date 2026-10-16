# Changelog

## 1.1.0

Built for OpenTelemetry Operator 0.161.0. The OpenTelemetryCollector and TargetAllocator schemas and CRDs gain `imagePullSecrets` and `revisionHistoryLimit`, also in the collector's embedded `targetAllocator`. New flat keys `image_pull_secrets` and `revision_history_limit` on collectors and TargetAllocators set them. Rendered output of existing inventories is unchanged.

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

Ships the OpenTelemetry Operator 0.160.0 CRD schemas under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7). Fixtures set `parameters.kapitan.vars.target`.

New shorthand and defaults, overridable from the inventory and documented with sources in the README:

- Collector `target_allocator: <name>` sets the label `opentelemetry.io/target-allocator: <name>` that links a standalone TargetAllocator. A dict still passes through as the embedded `targetAllocator`.
- A collector that uses a target allocator and sets no `mode` gets `mode: statefulset`. Previously the operator defaulted it to `deployment`, which the target allocator does not support. Set `mode` explicitly to keep a different mode.
