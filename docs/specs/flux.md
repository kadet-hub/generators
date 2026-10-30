# flux generator

Status: Draft
Code: `flux/`, `conftest.py`
Verified against: main @ 3dbbb6b

## Problem and decision

The flux generator had no spec. Its behaviour is described in
`flux/README.md` and the CHANGELOG. This spec starts with the defaults that
Flux 2.10 moved out of its CRDs. Other behaviour moves in here when a change
touches it.

Up to source-controller 1.9 and helm-controller 1.6, the CRDs defaulted
OCIRepository `spec.provider` to `generic` and `spec.timeout` to `60s`.
They also defaulted a HelmRelease chart template's `chart.spec.version` to
`*` and `chart.spec.reconcileStrategy` to `ChartVersion`. The API server
wrote these values into every stored object. Flux 2.10.0 pins
source-controller 1.10.1 and helm-controller 1.7.1. Their CRDs drop these
defaults, and a chart template can now also be of kind `OCIRepository`.
The field descriptions say the controllers use the same values when a
field is unset.

DEC-1: The generator writes these values where the inventory sets none.
The rendered object then states them on Flux 2.9 and 2.10 alike, as the
stored object did before. Relying on the controller defaults was
considered. It would keep behaviour the same but drop the values from the
rendered and the stored object.

## Defaults

- FLX-1: An OCIRepository MUST render `provider: generic` and
  `timeout: 60s` unless the inventory sets them, as a flat key or in
  `spec`.

  - Test: `flux/tests/test_defaults.py::test_oci_repository_defaults`;
    `./check flux` (fixtures `minimal`, `complete`)
  - Since: #120

- FLX-2: A HelmRelease whose `chart` is a HelmChart template MUST render
  `chart.spec.version: "*"` and `chart.spec.reconcileStrategy:
  ChartVersion` unless the inventory sets them. A chart template of kind
  `OCIRepository` MUST pass through unchanged.

  A HelmChart template has no `chart.kind` or `chart.kind: HelmChart`. It
  comes from `source` with a HelmRepository, GitRepository or Bucket, or
  from `spec.chart`. The CRD's CEL rules reject a `version` other than `*`
  and a `reconcileStrategy` other than `ChartVersion` on the
  `OCIRepository` kind, so the generator adds neither there. A `chart` or
  `chart.spec` that is not a mapping is no template and gets no defaults;
  the gate's schema check rejects it as before.

  - Test: `flux/tests/test_defaults.py::test_helm_chart_template_defaults`,
    `::test_oci_chart_template_passes_through`,
    `::test_non_mapping_chart_passes_through`; `./check flux` (fixture
    `complete`)
  - Since: #120

## Implementation inventory

| Item | Value |
|---|---|
| Defaults | `flux/__init__.py` (`SECTIONS`, `_resource`) |
| Unit tests | `flux/tests/test_defaults.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider flux/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `flux/tests/fixtures`, targets `minimal` and `complete` |
