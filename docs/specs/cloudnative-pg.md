# cloudnative-pg generator

Status: Draft
Code: `cloudnative-pg/`
Verified against: main @ f9fa4dd

## Problem and decision

The cloudnative-pg generator had no spec. Its behaviour is described in
`cloudnative-pg/README.md` and the CHANGELOG. This spec starts with the
resource names, which a recipe in kadet-hub/recipes could not set. Other
behaviour moves in here when a change touches it.

Every entry renders one resource named after its key. kadet-hub/recipes
lets a recipe write only keys below its own name (RCP-18 there), so its
`postgresql` recipe could only render a Cluster named `postgresql-*`. The
kadet-hub/examples recipe it replaces names the Cluster `app-db`, and
CloudNativePG names the Cluster's claims, Services and Secrets after it
(`app-db-1`, `app-db-rw`, `app-db-app`). A target that moves to the recipe
keeps its data only if the Cluster keeps its name.

## Resource names

- CNPG-1: An entry with `name` MUST render its resource with that name and
  write it to `<namespace>/<name>-<suffix>`. An entry without `name` MUST
  keep the name of its key.

  `name` applies to every section. A reference to the resource, such as a
  Pooler's or a Backup's `cluster`, names the resource, not the key.

  - Test: `cloudnative-pg/tests/test_names.py::test_name_overrides_key`, `::test_key_names_resource`; fixture target `complete`
  - Since: this change

- CNPG-2: Two entries of one section that render the same name in the same
  namespace MUST fail the compile, naming both keys.

  Before, the later one would have replaced the earlier output file.

  - Test: `cloudnative-pg/tests/test_names.py::test_same_name_fails`
  - Since: this change

DEC-1: The name is a key of the entry, as `name` in the standalone sections
of the kubernetes generator. Letting kadet-hub/recipes accept keys that a
chart's names need was considered. RCP-18 there keeps one recipe from
writing into another's keys, and an exception for chart names would have
to tell a chart name from any other key.

## Implementation inventory

| Item | Value |
|---|---|
| Resource names | `cloudnative-pg/__init__.py` (`main`) |
| Unit tests | `cloudnative-pg/tests/test_names.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider cloudnative-pg/tests` |
| Fixture | `cloudnative-pg/tests/fixtures`, targets `minimal` and `complete` |
