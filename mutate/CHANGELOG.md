# Changelog

## 0.2.1

`move` now resolves symbolic links before it checks `to`. A `to` that reaches a compile entry's `output_path` or leaves the target's compile directory through a link fails the compile, as the same path written without the link already did.

## 0.2.0

Adds the `move` action: `move: {to: <path>}` takes the matched documents out of their files and appends them to a file relative to the target's compile directory, such as a sibling directory for a chart's CRDs. Mutations moving to one file append in id order, and a file left without documents becomes the comment line, as after `delete`. A `to` at or below any compile entry's `output_path`, or naming a file that exists, fails the compile. Output of inventories without `move` is unchanged.

## 0.1.1

Ships the Kubernetes 1.37.2 schemas of the fixture kinds instead of 1.37.1. kubernetes-json-schema has the same files for both releases, so validation and output are unchanged.

## 0.1.0

First release. Patches the YAML files an earlier compile entry of the same `output_path` wrote, such as Kapitan's `helm` input, in place: mutations keyed by id, applied in id order with deletes last, match objects exactly on `apiVersion`, `kind`, `name`, `namespace` and `labels`, and `merge` (JSON Merge Patch, with `merge_lists` for keyed list merge), `json6902`, `delete` or `images`. `expects` fails the compile when a mutation matches no object, or not the given count. Only changed files are written; a file whose objects are all deleted becomes a comment line. The compile entry needs `output_type: plain`.
