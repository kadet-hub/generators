# tetragon generator

Status: Draft
Code: `tetragon/`
Verified against: main @ 1ea7e4e

## Problem and decision

Tetragon observes and enforces process, file and network behaviour in the
kernel through eBPF. What it hooks is configured by policies, the custom
resources TracingPolicy (cluster-scoped) and TracingPolicyNamespaced, in
API group `cilium.io/v1alpha1`. kadet-hub has no generator for them, so a
project writes the policies as raw YAML next to its Kapitan inventory.

`tetragon` renders both kinds from `parameters.generators.tetragon`. The
Tetragon install itself (DaemonSet, operator, RBAC) comes from the upstream
Helm chart through the `helm` input. PodInfo, the third CRD of the release,
is written by the Tetragon operator and is not rendered.

DEC-1: A policy is mostly a list of hooks (`kprobes`, `tracepoints`,
`lsmhooks` and others) whose selectors are deeply nested CRD structures.
The generator passes them through as written in CRD camelCase. It offers
snake_case flat keys only for the top-level fields of `spec`, as the velero
and cilium generators do, and does not translate keys below them.
Translating selectors was rejected: the CRD has more than a dozen selector
kinds, a mapping would trail every Tetragon release, and the upstream
policy examples could no longer be copied.

## Resources

- TET-1: An entry of `tracing_policies` MUST render one TracingPolicy
  without a namespace, written to `<name>-tracingpolicy`.

  - Test: `tetragon/tests/test_tetragon.py::test_tracing_policy`; fixture
    targets `minimal` and `complete`
  - Since: this change

- TET-2: An entry of `tracing_policies_namespaced` MUST render one
  TracingPolicyNamespaced, written to
  `<namespace>/<name>-tracingpolicynamespaced`.

  The namespace is `namespace` on the entry, then
  `generators.tetragon.namespace`, then `parameters.namespace`, then
  `default`. A namespaced policy applies to the pods of its own namespace,
  which is usually the target's workload namespace, so
  `parameters.namespace` is read.

  - Test: `tetragon/tests/test_tetragon.py::test_namespace_fallback`;
    fixture target `complete`
  - Since: this change

- TET-3: An entry with `name` MUST render its resource with that name. An
  entry without `name` MUST take the name of its key.

  - Test: `tetragon/tests/test_tetragon.py::test_name_names_the_resource`
  - Since: this change

- TET-4: Two entries of one section that render the same name, in the same
  namespace for TracingPolicyNamespaced, MUST fail the compile, naming both
  keys.

  Otherwise the later entry would replace the earlier output file.

  - Test: `tetragon/tests/test_tetragon.py::test_same_name_fails`
  - Since: this change

## Spec fields

- TET-5: Every entry MUST accept `labels`, `annotations` and a `spec` dict
  that is copied into the resource `spec` unchanged.

  - Test: `tetragon/tests/test_tetragon.py::test_spec_and_flat_keys`;
    fixture target `complete`
  - Since: this change

- TET-6: The flat keys `kprobes`, `tracepoints`, `uprobes`, `usdts`,
  `lsmhooks`, `fentries`, `enforcers`, `lists`, `options`, `loader`,
  `pod_selector`, `container_selector`, `host_selector` and
  `selectors_macros` MUST set the top-level `spec` field of the same name
  in camelCase, with the value unchanged. A flat key MUST win over the same
  field in `spec` and log a warning.

  - Test: `tetragon/tests/test_tetragon.py::test_spec_and_flat_keys`
  - Since: this change

- TET-7: Compiled output MUST validate against the closed JSON schemas of
  the TracingPolicy and TracingPolicyNamespaced CRDs of Tetragon 1.7.1.

  - Test: the kadet-hub gate (registry QA-7, QA-11) through `./check
    tetragon`, fixture targets `minimal` and `complete`
  - Since: this change

## Implementation inventory

| Item | Value |
|---|---|
| Generator | `tetragon/__init__.py` (`main`, `SECTIONS`, `FLAT_KEY_MAP`) |
| Unit tests | `tetragon/tests/test_tetragon.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider tetragon/tests` |
| Fixtures | `tetragon/tests/fixtures`, targets `minimal` and `complete` |
| Schemas | `tetragon/schemas/cilium.io/`, source in `tetragon/schemas/sources.yaml` (Tetragon 1.7.1, `pkg/k8s/apis/cilium.io/client/crds/v1alpha1`) |
