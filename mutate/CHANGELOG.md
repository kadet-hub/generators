# Changelog

## 0.1.0

First release. Patches the YAML files an earlier compile entry of the same `output_path` wrote, such as Kapitan's `helm` input, in place: mutations keyed by id, applied in id order with deletes last, match objects exactly on `apiVersion`, `kind`, `name`, `namespace` and `labels`, and `merge` (JSON Merge Patch, with `merge_lists` for keyed list merge), `json6902`, `delete` or `images`. `expects` fails the compile when a mutation matches no object, or not the given count. Only changed files are written; a file whose objects are all deleted becomes a comment line. The compile entry needs `output_type: plain`.
