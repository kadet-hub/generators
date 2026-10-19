# mutate Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/mutate/) page.

Kapitan kadet generator that patches the YAML an earlier compile entry wrote, typically a Helm chart rendered with Kapitan's `helm` input, in place. It covers what the chart's values do not expose: a field to set or remove, a container or environment variable to add, an image to pin by digest, an object to drop. Every mutation states which objects it expects to change, so a chart upgrade that renames an object fails the compile instead of dropping the patch silently.

It replaces the copy-paste patch step of the kadet-hub [authors guide](https://github.com/kadet-hub/registry/blob/main/docs/authors.md#patching-a-helm-chart-instead-of-wrapping-it). Spec: [docs/specs/mutate.md](../docs/specs/mutate.md).

## Usage

Two compile entries on the same `output_path`: the chart first, then `mutate`. Kapitan runs a target's entries in order and gives the kadet entry that directory as `compile_path`; `mutate` reads every `.yaml` and `.yml` file in it and returns the files it changed under the same relative path, which Kapitan writes over the originals. `output_type: plain` is required (see [Failure modes](#failure-modes)).

```yaml
# inventory/classes/podinfo.yml
parameters:
  podinfo:
    mutations:
      replicas:
        match:
          kind: Deployment
          name: podinfo
        merge:
          spec:
            replicas: 2
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/mutate@sha256:<digest>
        output_path: lib/mutate
      - type: helm
        source: https://stefanprodan.github.io/podinfo
        chart_name: podinfo
        version: 6.15.0
        output_path: charts/podinfo
    compile:
      - input_type: helm
        input_paths:
          - charts/podinfo
        output_path: podinfo
        helm_params:
          name: podinfo
          namespace: apps
      - input_type: kadet
        input_paths:
          - lib/mutate
        output_path: podinfo
        output_type: plain
        input_params:
          mutations: ${podinfo:mutations}
```

`mutations` is a map keyed by mutation id, so a target or an environment class adds its own and overrides a class's by id:

```yaml
# inventory/targets/prod.yml
classes:
  - podinfo

parameters:
  podinfo:
    mutations:
      replicas:
        merge:
          spec:
            replicas: 4
      podinfo-sidecar:
        match:
          kind: Deployment
          name: podinfo
        merge_lists:
          containers: name
          env: name
        merge:
          spec:
            template:
              spec:
                containers:
                  - name: podinfo
                    env:
                      - name: PODINFO_UI_MESSAGE
                        value: prod
                  - name: proxy
                    image: docker.io/envoyproxy/envoy:<tag>
      pin-podinfo:
        match:
          kind: Deployment
        images:
          ghcr.io/stefanprodan/podinfo:
            digest: sha256:ec73780a8425f59ea49f5bc8cdff0d598805a224fbaa1f86c67a244f250fa9da
      no-hpa:
        match:
          kind: HorizontalPodAutoscaler
          name: podinfo
        delete: true
```

The fixture target [`complete`](tests/fixtures/inventory/targets/complete.yml) uses every action on a vendored podinfo render.

## Mutation schema

| Key | Value |
|---|---|
| `match` | Required, at least one of `apiVersion`, `kind`, `name`, `namespace` (strings) and `labels` (map of strings) |
| `merge` | Map, applied as JSON Merge Patch |
| `merge_lists` | With `merge` only: map of list field name to key field, for example `{containers: name, env: name, ports: containerPort}` |
| `json6902` | List of JSON Patch operations `{op, path, value}` or `{op, from, path}` |
| `delete` | `true` |
| `images` | Map of image name to `{name, tag, digest}`, at least one of the three |
| `expects` | `"1+"` (default), `"0+"` or an integer |

A mutation has exactly one of `merge`, `json6902`, `delete` and `images`. Unknown keys fail the compile. `input_params` takes `mutations` only.

## Semantics

| Topic | Behaviour |
|---|---|
| Files | Every `.yaml` and `.yml` file below the entry's `output_path`, sorted by path. Other files stay as they are. Empty documents are dropped. |
| Order | Mutations in sorted id order, every delete after every other mutation. Each sees the result of the ones before. |
| Matching | Every key of `match` must equal the document's value, AND'ed. `name` and `namespace` are `metadata.name` and `metadata.namespace`; `labels` entries must all be in `metadata.labels`. `kind: "*"` matches any kind and keeps the other keys in force. A document without `metadata.namespace` does not match `namespace`. A `List` is matched as one document. |
| `expects` | Count of matched documents across all files. `"1+"` fails on zero, an integer on any other count, `"0+"` never. |
| `merge` | RFC 7386: maps merge recursively, `null` removes a key, lists and scalars replace. |
| `merge_lists` | Where a patch list under a listed field name meets a list in the document, at any depth, items merge by the key field: a known key merges into that item (with the same rules, so `env` inside a matched container merges too), a new key is appended. A patch item without the key, or duplicate keys, fails. Items cannot be removed this way; use `json6902` `remove`. |
| `json6902` | RFC 6902 `add`, `remove`, `replace`, `move`, `copy`, `test`, in order. Paths are RFC 6901 pointers (`~1` for `/`, `~0` for `~`, `-` appends). A failing `test` or a missing path fails. `test` compares as JSON: `1` equals `1.0`, `true` does not equal `1`. |
| `delete` | Removes the matched documents. A file left without documents becomes `# all objects removed by mutation <ids>`. |
| `images` | Kustomize `images` semantics on `containers` and `initContainers` of a Pod and of the Pod template of a Deployment, StatefulSet, DaemonSet, Job or CronJob. The key is the image as written without `@digest` and without the `:tag` after the last `/`: `docker.io/redis:8.8.0` has the name `docker.io/redis`, and `redis` does not match it. `name` replaces the name and keeps tag and digest; `tag` sets the tag and drops the digest; `digest` sets the digest and drops the tag; `tag` with `digest` gives `name:tag@digest`. |
| Output | Only files with a changed or deleted document are written; the others keep the chart's bytes. Written files keep document and key order, use literal blocks for multi-line strings and lose comments such as Helm's `# Source:` lines. |

## Failure modes

Every error starts with `mutate: mutation <id>:` and names the file when one document is concerned. Kapitan prints it in the traceback above `Could not load Kadet module: mutate`.

| Error | Cause |
|---|---|
| `expects 1+, matched 0` | No document matches: the chart renamed or stopped rendering the object, or `match` has a typo. Set `expects: "0+"` for a mutation that may legitimately match nothing. |
| `expects <n>, matched <m>` | An exact count did not hold. |
| `images [...] match no container` | The documents matched, but no container image has that name; compare with the image as rendered, registry prefix included. |
| `json6902 test of '<path>' failed`, `json6902 path '<path>' does not exist` | The rendered document differs from what the patch assumes. |
| `result lost apiVersion, kind or metadata.name` | A `merge` or `json6902` removed the object's identity. |
| `needs exactly one of ...`, `unknown keys ...`, `match must be a non-empty map` | The mutation is malformed. |
| `the compile entry for <path> needs output_type: plain` | The kadet entry passing `mutations` has another `output_type`. With the default `yaml` Kapitan would write `deployment.yaml.yaml` next to the unmutated original; with `auto` the comment line of an emptied file would become a quoted string. |
| `<file>: not YAML` | A `.yaml` or `.yml` file below `output_path` does not parse. |

With Kapitan's `--cache`, a kadet result is cached by the inventory, the input parameters and the target's `helm` dependencies, not by the files `mutate` reads. A chart vendored without a `helm` dependency, or a `copy` source, can change without changing the cache key; the cached result then overwrites the new render with old content. Compile without `--cache`, or with a `helm` dependency, in that case.

## Migrating

From the authors guide's `components/patch` step: each `patches` entry `<kind>/<name>: <patch>` becomes a mutation `{match: {kind: <kind>, name: <name>}, merge: <patch>}` under an id of your choice; merge semantics are the same (maps recurse, lists replace), and a patch that matches nothing still fails. Set `output_type: plain` instead of `auto`, delete the component and depend on `lib/mutate`. Untouched files are no longer rewritten.

From kgenlib's `mutations` (kapicorp/generators):

| kgenlib | mutate |
|---|---|
| `patch: [{conditions, patch}]`, a list | `merge` under an id in a map, so classes and targets merge instead of appending |
| conditions on any dotted path, a list of allowed values per path | `match` on `apiVersion`, `kind`, `name`, `namespace`, `labels` with one value each; several values are several mutations |
| `"*"` in any condition matches everything, ignoring the other conditions | `kind: "*"` only, and the other keys still apply |
| lists in a patch are appended (`box_merge_lists="extend"`), so containers get duplicated | lists replace; `merge_lists` merges them by key |
| `delete` removes objects while iterating and can skip the next one | `delete` removes every match, after all other mutations |
| a mutation that matches nothing passes | `expects`, `"1+"` by default |
| `regex_patch`, `bundle`, `prune` | not supported: no text patching, files keep their names |

## Not supported

Templating, regular expressions on the rendered text, Python hooks, rendering charts, moving objects between files or renaming files, and strategic merge patch.

## Output

The files of the earlier entry, the changed ones rewritten. The manifest carries the `kubernetes` tag; `schemas/` holds the Kubernetes 1.37.1 schemas of the kinds in the fixture output (Deployment, Service, ConfigMap, Pod, HorizontalPodAutoscaler).
