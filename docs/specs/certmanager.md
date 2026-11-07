# certmanager generator

Status: As-built
Code: `certmanager/`, `conftest.py`
Verified against: main @ fbe8c39

## Problem and decision

The certmanager generator had no spec. Its behaviour is described in
`certmanager/README.md` and the CHANGELOG. This spec starts with resource
metadata. Other behaviour moves in here when a change touches it.

Up to 1.0.4 every resource carried the `name` label and nothing else in
its metadata. `labels` and `annotations` on an entry were ignored without
an error. The external-secrets, kyverno, velero and grafana generators take
both keys on every entry. The `platform-baseline` example in
kadet-hub/examples puts the Argo CD sync wave `-1` on its ExternalSecret
that way, and could not do the same for its Certificate.

## Metadata

- CM-1: An entry of `certs`, `issuers`, `clusterissuers` or `bundles` MUST
  add its `labels` to `metadata.labels` and its `annotations` to
  `metadata.annotations` of the resource it renders.

  The generator's `name` label stays. A `name` key in `labels` replaces
  it, as in external-secrets and velero.

  - Test: `certmanager/tests/test_metadata.py::test_entry_metadata`,
    `::test_no_metadata_keys`; fixture target `complete`
  - Since: #178

- CM-2: A `ca_issuers` entry MUST add its `labels` and `annotations` to
  each of the three resources it renders.

  The self-signed ClusterIssuer, the root Certificate and the CA
  ClusterIssuer are one CA, so a sync wave or an owner label on the entry
  belongs on all three. Different metadata per resource needs the three
  written as `clusterissuers` and `certs` entries.

  - Test: `certmanager/tests/test_metadata.py::test_ca_issuer_metadata`;
    fixture target `complete`
  - Since: #178

The unit tests need a target before the package loads, which `conftest.py`
at the repository root registers (rabbitmq spec, DEC-1).

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Entry metadata | `certmanager/k8s.py` (`Base.body`, CM-1), `certmanager/__init__.py` (`main`, `ca_issuers`, CM-2) |
| Unit tests | `certmanager/tests/test_metadata.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider certmanager/tests` (bytecode in the tree fails SEC-5) |
| Fixture | `certmanager/tests/fixtures`, targets `minimal` and `complete` |
