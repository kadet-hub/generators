# Changelog

## 0.1.0

First release. Writes an OCM component constructor (new CLI generation, multi-component form) for a target. Every `image` in the YAML files `images.scan` matches below the compile root, plus `images.refs`, becomes an `ociImage` resource, deduplicated by parsed reference with a tag-only reference folded into a pinned one of the same tag, named after the repository and versioned by its tag, with an `access` template for mirrors and pull-through caches, an optional label holding the upstream reference, optional required digests and `images.names` for name clashes. Resources that are not images come from the inventory as a map keyed by name. The compile entry needs `output_path: .` and `output_type: plain`.
