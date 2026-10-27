# ocm generator

Status: Draft
Code: `ocm/`
Verified against: main @ 5e4335d

## Problem and decision

A project that ships its Kapitan output into another environment, for
example an air-gapped one, describes what it ships as an Open Component
Model (OCM) component version. The `ocm` CLI builds that from a component
constructor file. Writing the constructor by hand means listing every
container image of the compiled manifests again, with its tag and digest,
and keeping that list in step with every chart and generator upgrade. A
missed image surfaces only when the target environment cannot pull it.

`ocm` writes the constructor during the compile. It reads the manifests
that earlier compile entries of the same target wrote, collects every
image and turns each one into an `ociImage` resource. Resources that are
not images, such as the manifests themselves as an OCI artifact or a
directory input, come from the inventory as they are.

```yaml
- input_type: helm
  input_paths: [charts/podinfo]
  output_path: k8s/podinfo
- input_type: kadet
  input_paths: [lib/ocm]
  output_path: .
  output_type: plain
  input_params:
    components: ${ocm:components}
```

Kapitan 0.36.3 runs a target's compile entries in order and passes a kadet
entry its own output directory as `input_params.compile_path`. With
`output_path: .` that is the target's compile root, so `ocm` sees every
file the earlier entries wrote. The `mutate` generator relies on the same
behaviour.

The constructor follows the schema of the new OCM CLI generation
(`open-component-model/open-component-model`,
`bindings/go/constructor/spec/v1/resources/schema-2020-12.json`), in its
multi-component form. Values only known when the component version is
built, such as its version, stay `${NAME}` placeholders that the `ocm` CLI
substitutes. The generator does not interpret them.

Getting `${NAME}` through the inventory depends on the backend. reclass-rs
takes `\${NAME}`. Kapitan's OmegaConf backend resolves an escaped value a
second time, so `\${NAME}` fails there and `${escape:NAME}` is the form
that survives. One inventory cannot serve both, which is why the fixture
uses literal values and the README shows both forms.

Not in scope: running the `ocm` CLI, signing, transfer, localization
rules, and reading images from anything other than YAML.

## Input

- OCM-1: `input_params` MUST hold `components` and MAY hold `file`. Any
  other key, and any key of `images` other than those of OCM-5 to OCM-10,
  MUST fail the compile, naming the key.

  `file` is the output path relative to the compile root, default
  `component-constructor.yaml`. The compile entry needs `output_type:
  plain`, as `ocm` returns the file's text.

  - Test: `ocm/tests/test_constructor.py::test_unknown_keys`
  - Since: this change

- OCM-2: `components` maps an id to a component. Every key of a component
  except `images` and `resources` MUST be copied to the constructor as
  written, and a component without `name`, `version` or `provider` MUST
  fail the compile, naming the id.

  The id only orders the components and names them in errors; the OCM
  name is `name`. A map lets classes add components and resources to a
  target, which a list cannot, as both inventory backends replace lists.
  `labels`, `sources` and `componentReferences` pass through unchanged.

  - Test: `ocm/tests/test_constructor.py::test_component_passthrough`,
    `::test_component_required`
  - Since: this change

- OCM-3: `resources` maps a resource name to a resource. Each MUST be
  copied as written with `name` set to its key, in the order of the map,
  before the image resources.

  A resource that sets `name` itself keeps it. This is where a component
  gets everything that is not an image: the compiled manifests as an OCI
  artifact, a Git bundle, a directory of operations files.

  - Test: `ocm/tests/test_constructor.py::test_resources`
  - Since: this change

- OCM-4: Two resources of one component with the same name MUST fail the
  compile, naming both.

  `ocm add component-version` rejects the constructor later anyway; the
  compile names the image refs behind the clash, which the CLI does not.

  - Test: `ocm/tests/test_constructor.py::test_name_collision`
  - Since: this change

## Images

- OCM-5: `images.scan` is a list of glob patterns relative to the compile
  root. `ocm` MUST read every matched file as YAML with a safe loader and
  collect the string value of every `image` key at any depth.

  Any depth covers Pod templates, CronJobs and custom resources that name
  an image, such as operator CRs. A plain `=` reads as a string, as in
  `mutate`, since charts with Prometheus Operator CRDs contain one. Images
  inside string values, such as a manifest in a ConfigMap, are not seen.

  - Test: `ocm/tests/test_constructor.py::test_scan`
  - Since: this change

- OCM-5a: A pattern that matches no file, or a match outside the compile
  root, MUST fail the compile, naming the pattern. A file that does not
  parse MUST fail the compile, naming the file.

  A pattern matching nothing is almost always a wrong path, and an empty
  image list would ship a component that cannot run.

  - Test: `ocm/tests/test_constructor.py::test_scan_errors`
  - Since: this change

- OCM-6: `images.refs` is a list of image references added to the scanned
  ones. Duplicates MUST collapse to one resource, and image resources MUST
  be ordered by reference.

  For images that run but appear in no manifest, such as an installer
  image named in a machine config.

  - Test: `ocm/tests/test_constructor.py::test_refs_dedup_order`
  - Since: this change

- OCM-6a: Duplicates MUST be detected on the parsed reference, with the
  registry in lower case: `redis:8` and `docker.io/library/redis:8` are one
  image. A reference with a tag and no digest MUST collapse into a
  reference with the same registry, repository and tag and a digest.

  The second rule covers an image that one manifest pins by digest and
  another names by tag only. Both are the same resource; kept apart, they
  would clash on name and version and `images.names` could not separate
  them. Two different digests of one tag stay two images and clash.
  `%ref%` and the label carry the first reference in sort order.

  - Test: `ocm/tests/test_constructor.py::test_dedup_parsed`
  - Since: this change

- OCM-7: Each image MUST become a resource of type `ociImage` whose
  `access` is `{type: ociArtifact, imageReference: <images.access>}`, its
  name the last path segment of the repository and its version the tag.

  A reference without a registry is a Docker Hub one: `redis:8` is
  registry `docker.io`, path `library/redis:8`. A reference without tag and
  digest has version `latest`. A reference with a digest and no tag MUST
  fail the compile, naming it: there is no version to derive, and `latest`
  would be wrong.

  - Test: `ocm/tests/test_constructor.py::test_image_resource`,
    `::test_untagged_digest`
  - Since: this change

- OCM-8: `images.access` is a template for `imageReference`, default
  `%ref%`. `ocm` MUST replace `%ref%` with the reference as written,
  `%registry%` with its registry, `%registry_id%` with the registry with
  every character outside `A-Za-z0-9` replaced by `_`, and `%path%` with
  the rest after the registry, tag and digest included.

  The default keeps the upstream reference. A static mirror is
  `mirror.example.org/%registry%/%path%`. A mirror known only when the
  component is built is one CLI variable per registry,
  `${PROXY_%registry_id%}/%path%`. Only these four tokens are replaced, so
  `${...}` placeholders pass through.

  The tokens use `%` because OmegaConf's grammar rejects `{` and `<` inside
  a resolver argument such as `${escape:PROXY_...}`, and `%` is one of the
  few characters it accepts there.

  - Test: `ocm/tests/test_constructor.py::test_access_template`; `./check ocm`
    (fixture `complete`, both backends)
  - Since: this change

- OCM-9: `images.label` MAY name a label. When set, each image resource
  MUST carry it with the reference as written as its value.

  Once `access` points at a mirror, the label is the only record of where
  an image came from.

  - Test: `ocm/tests/test_constructor.py::test_label_digest`
  - Since: this change

- OCM-10: With `images.require_digest: true`, an image without a digest
  MUST fail the compile, naming it. `images.names` maps a repository
  (registry and path without tag and digest, `docker.io/library/redis`)
  to a resource name; it MUST replace the derived name of that
  repository's images.

  `names` resolves OCM-4 clashes, such as `bitnami/redis` and
  `library/redis`, without changing either image. A `names` key that
  matches no image MUST fail the compile, so a removed image does not
  leave a dead entry behind.

  - Test: `ocm/tests/test_constructor.py::test_label_digest`,
    `::test_names`
  - Since: this change

## Output

- OCM-11: `ocm` MUST write one file, `file`, holding `components:` with
  the components in id order, and the output MUST validate against the
  OCM constructor schema whenever the inventory values do.

  - Test: `ocm/tests/test_constructor.py::test_schema`; `./check ocm`
  - Since: this change

## Manifest and gate

- OCM-12: The manifest MUST declare no dependencies, binaries, charts or
  schemas, and the fixture project MUST compile vendored manifests with a
  `copy` entry followed by `ocm`.

  The constructor carries no `apiVersion` and `kind`, so the gate's schema
  check (QA-7) does not apply to it. The OCM schema is pinned in the unit
  tests instead.

  - Test: `./check ocm`
  - Since: this change

## Open questions

- OQ-1: With Kapitan's `--cache`, a kadet result is keyed on the
  inventory and input parameters, not on the files `ocm` reads. A chart
  bump that changes an image but no inventory value can hit the cache and
  write the old constructor. Same limit as `mutate` OQ-1.

## Implementation inventory

| Item | Value |
|---|---|
| Code | `ocm/__init__.py` (Kapitan entry), `ocm/constructor.py` (no Kapitan import) |
| Unit tests | `ocm/tests/test_constructor.py`, run with `cd ocm && PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with jsonschema --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider tests` |
| OCM schema | `ocm/tests/constructor.schema.json`, `open-component-model/open-component-model` v0.21.0 (`b51f193`), `bindings/go/constructor/spec/v1/resources/schema-2020-12.json` |
| Fixture | `ocm/tests/fixtures`, targets `minimal` and `complete`, manifests in `manifests/` |
| Input | `input_params.components`, `input_params.file`, compile entry `output_path: .` and `output_type: plain` |
