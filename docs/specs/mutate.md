# mutate generator

Status: Draft
Code: `mutate/`
Verified against: main @ 7cd44eb

## Problem and decision

The marketplace lists no generator that renders a chart named in the
consumer's inventory (registry DEC-15). The registry's `docs/authors.md`
shows instead how to render a pinned chart with Kapitan's `helm` input and
patch the output in a kadet step of the consumer's own project. Every
project that follows it copies that step: about 40 lines that merge maps,
replace lists, cannot delete an object, change an image or merge a list of
containers by name, and match only on `<kind>/<name>`.

`mutate` is that step as a listed generator. A consumer target has two
compile entries on the same `output_path`: the `helm` input (or any earlier
entry that writes YAML, such as `copy`) and then `mutate`:

```yaml
- input_type: helm
  input_paths: [charts/podinfo]
  output_path: podinfo
- input_type: kadet
  input_paths: [lib/mutate]
  output_path: podinfo
  output_type: plain
  input_params:
    mutations: ${podinfo:mutations}
```

Kapitan 0.36.3 runs the compile entries of a target in order and passes the
kadet entry its own output directory as `input_params.compile_path`, where
the earlier entry already wrote its files. `mutate` reads them, applies the
mutations and returns each changed file under its path relative to that
directory, so Kapitan writes it over the original.

kgenlib's `mutate` (kapicorp/generators) and kapitan-reference's `kstmz`
were the models. `mutate` keeps their idea of matching objects and applying
actions, and differs where they lose changes silently: a wildcard there
short-circuits the other conditions, lists are appended, deleting while
iterating skips objects, and zero matches pass.

Not in scope: templating, regular expressions on text, Python hooks,
rendering charts, moving objects between files or renaming files, and
strategic merge patch. A Kustomize post-render stage was considered; the
sandbox image carries no `kustomize` binary, and a binary would need
`binaries` in the manifest.

## Files

- MUT-1: `mutate` MUST read every file below `compile_path` whose name ends
  in `.yaml` or `.yml`, in sorted path order, as YAML documents with a safe
  loader, and leave every other file untouched.

  The loader reads a plain `=` as a string, as the registry gate's CRD
  loader does; charts that ship Prometheus Operator CRDs list `=` among
  matcher types. Empty documents are dropped. A file that does not parse
  fails the compile, naming the file.

  - Test: `mutate/tests/test_mutations.py::test_reads_yaml_files_only`, `::test_equals_sign_is_a_string`
  - Since: #91

- MUT-2: `mutate` MUST return a file under its relative path, and only when
  a mutation changed or deleted a document in it; the documents keep their
  order and are written with `---` between them.

  Other files are not returned, so Kapitan leaves the earlier entry's bytes
  in place, also for documents a mutation matched without changing them,
  such as a `json6902` `test` or `images` on a ConfigMap. Returned files are serialized again with
  `yaml.safe_dump_all`, keys in their original order and multi-line strings
  as literal blocks, so a returned file changes its formatting, not its
  content, and loses the comments Helm writes (`# Source: ...`).

  - Test: `mutate/tests/test_mutations.py::test_untouched_files_are_not_returned`, `::test_matched_but_unchanged_files_are_not_returned`; fixture targets `minimal`, `complete`
  - Since: #91

- MUT-3: A file whose documents are all deleted MUST be returned as the
  single line `# all objects removed by mutation <ids>`, with the ids of the
  delete mutations that removed them, sorted and separated by `, `.

  An empty file would not do: Kapitan's YAML writer skips empty output, so
  the earlier entry's file would stay. `kubectl apply -f <dir>` accepts a
  file that holds only a comment.

  - Test: `mutate/tests/test_mutations.py::test_file_emptied_by_delete_is_a_comment`; fixture target `complete` (`podinfo/templates/hpa.yaml`)
  - Since: #91

- MUT-4: The compile entry that runs `mutate` MUST have
  `output_type: plain`; `mutate` MUST fail the compile when an entry of the
  target that passes `mutations` has another output type.

  With `plain` Kapitan writes each returned string to exactly the returned
  path. With the default `yaml` it appends `.yaml`, so the original file
  stays unmutated next to a broken copy. With `auto` the comment of MUT-3
  would be written as a quoted YAML string. `mutate` cannot see its own
  output type, so it checks the target's `kapitan.compile` entries in the
  inventory.

  - Test: `mutate/tests/test_mutations.py::test_output_type_must_be_plain`
  - Since: #91

## Mutations

`input_params.mutations` is a map of mutation id to mutation, so classes
and targets add and override mutations by id; the inventory would append
lists. `input_params` takes no other key besides Kapitan's `compile_path`.

- MUT-5: Mutations MUST be applied in sorted id order, every non-delete
  mutation before every delete mutation.

  Each mutation sees the result of the ones before it, so a merge that
  changes labels changes what later matches select. Deletes run last, so
  no mutation's match count depends on an object a delete removed before.

  - Test: `mutate/tests/test_mutations.py::test_order_sorted_deletes_last`
  - Since: #91

- MUT-6: A mutation MUST have a non-empty `match` and exactly one action
  of `merge`, `json6902`, `delete` and `images`, and MAY have `expects`
  and, with `merge` only, `merge_lists`. Any other key, here or inside
  `match`, `images` entries and `json6902` operations, MUST fail the
  compile, naming the mutation id.
  - Test: `mutate/tests/test_mutations.py::test_invalid_mutations_fail`
  - Since: #91

- MUT-7: Every document a mutation changed MUST still have string
  `apiVersion`, `kind` and `metadata.name`; otherwise the compile fails,
  naming the mutation id and the file.
  - Test: `mutate/tests/test_mutations.py::test_result_keeps_identity`
  - Since: #91

Every error message starts with `mutate: mutation <id>:` and names the file
where one document is concerned. Kapitan reports it as the cause of `Could
not load Kadet module: mutate`.

## Matching

- MUT-8: A document MUST match when every key of `match` equals the
  document's value: `apiVersion`, `kind`, `name` (`metadata.name`),
  `namespace` (`metadata.namespace`), and `labels`, a map of which every
  entry must be in `metadata.labels`. `kind: "*"` matches any kind and
  leaves the other keys in force.

  Matching is exact. A document without `metadata.namespace` does not
  match a `namespace` key; charts that leave the namespace to `helm
  --namespace` render none. A `List` matches as a document, its items are
  not searched.

  - Test: `mutate/tests/test_mutations.py::test_match_is_exact_and_anded`
  - Since: #91

- MUT-9: The number of documents a mutation matched MUST satisfy
  `expects`, else the compile fails with the mutation id, `expects` and the
  matched count. `expects` is `"1+"` (the default), `"0+"` or a
  non-negative integer for an exact count.

  The default catches the chart upgrade that renames an object and would
  otherwise drop the mutation silently. `"0+"` is for mutations shared
  across targets whose charts do not all render the object.

  - Test: `mutate/tests/test_mutations.py::test_expects`
  - Since: #91

## Actions

- MUT-10: `merge` MUST be applied as a JSON Merge Patch (RFC 7386): maps
  merge recursively, `null` removes a key, lists and other values replace.
  - Test: `mutate/tests/test_mutations.py::test_merge_rfc7386`
  - Since: #91

- MUT-11: `merge_lists` maps a list field name to its key field, for
  example `containers: name`; where a patch list under that name meets a
  list in the document, at any depth, items MUST merge by key: an item with
  a key the document has merges into that item, one with a new key is
  appended.

  Merged items are merged with the same rules, so `env: name` merges the
  environment of a container that `containers: name` matched. A patch item
  without the key field, and duplicate keys in the patch or in the
  document list, fail the compile. Document items without the key field
  are kept as they are. Removing an item takes a `json6902` `remove`.

  - Test: `mutate/tests/test_mutations.py::test_merge_lists_by_key`
  - Since: #91

- MUT-12: `json6902` MUST apply its list of JSON Patch (RFC 6902)
  operations in order: `add`, `remove`, `replace`, `move`, `copy` and
  `test`. A `test` that does not hold, or an operation on a path that does
  not exist, MUST fail the compile.

  Paths are JSON Pointers (RFC 6901) with `~0` and `~1` escapes and `-`
  for the end of a list; `test` compares as JSON does, so `1` equals `1.0`
  and `true` does not equal `1`.

  - Test: `mutate/tests/test_mutations.py::test_json6902`
  - Since: #91

- MUT-13: `delete: true` MUST remove every matched document from its file.
  - Test: `mutate/tests/test_mutations.py::test_order_sorted_deletes_last`
  - Since: #91

- MUT-14: `images` maps an image name to `name`, `tag` and `digest`, at
  least one of them; it MUST set the `image` of every container and init
  container of a matched Pod, or of the Pod template of a matched
  Deployment, StatefulSet, DaemonSet, Job or CronJob, whose image name
  equals the key.

  This follows Kustomize's `images` field. The image name is the image
  without `@<digest>` and without the `:<tag>` after its last `/`, compared
  as written: `redis` does not match `docker.io/redis`. `name` replaces the
  name and keeps tag and digest. `tag` sets the tag and drops a digest,
  `digest` sets the digest and drops a tag, both give `name:tag@digest`.
  A key that changes no container of the matched documents fails the
  compile, as a match of zero documents does.

  - Test: `mutate/tests/test_mutations.py::test_images`
  - Since: #91

## Manifest and gate

- MUT-15: The manifest MUST declare no dependencies, binaries or charts,
  the tag `kubernetes` only, and the fixture project MUST compile vendored
  chart output with a `copy` entry followed by `mutate`.

  The fixture vendors `helm template` output of podinfo 6.15.0, so the gate
  compiles a real chart without `charts` and without `helm` in the sandbox.
  `kubernetes` has its evidence there (QA-6); `helm` would need a chart or
  `helm template` in `binaries`.

  - Test: `./check mutate`
  - Since: #91

## Open questions

- OQ-1: With Kapitan's `--cache`, a kadet result is keyed on the
  inventory, the input parameters and the target's helm dependencies, not
  on the files `mutate` reads. A chart vendored without a `helm`
  dependency, or a `copy` source, can change without changing the key, and
  a cache hit then writes the old mutated files over the new render. The
  README states the limit; whether Kapitan should hash the earlier entries'
  output is open.

## Implementation inventory

| Item | Value |
|---|---|
| Code | `mutate/__init__.py` (files, inventory check), `mutate/mutations.py` (matching and actions, no Kapitan import) |
| Unit tests | `mutate/tests/test_mutations.py`, run with `cd mutate && PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider tests` (bytecode in the tree fails SEC-5) |
| Fixture | `mutate/tests/fixtures`, targets `minimal` and `complete`, vendored render in `rendered/podinfo/` |
| Schemas | `mutate/schemas/`, kubernetes-json-schema v1.37.1-standalone-strict, as in `kubernetes/schemas/` |
| Input | `input_params.mutations`, compile entry `output_type: plain` |
