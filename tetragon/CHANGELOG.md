# Changelog

## 0.2.0

Built for Tetragon 1.8.0. New flat keys `node_selector` and `state` set `nodeSelector` and `state`, the top-level `spec` fields Tetragon 1.8.0 adds. `nodeSelector` selects by label the nodes whose agents load a policy. A `hostSelector` with `matchLabels` or `matchExpressions` now fails the compile and points to `node_selector`. Tetragon supports only null and `{}` there. Its agent refuses to load such a policy, and with the 1.8.0 CRDs the API server rejects it. The schemas and CRDs gain the 1.8.0 selectors and actions, such as `matchCmdArgs`, `matchWorkloads` and `UpdateState`, and validation rules the API server checks. They no longer accept the actions `FollowFD`, `UnfollowFD` and `CopyFD`, which Tetragon 1.8.0 removed. Rendered output of other inventories is unchanged.

## 0.1.0

First release. Renders TracingPolicy and TracingPolicyNamespaced from `parameters.generators.tetragon`, with the Tetragon 1.7.1 CRD schemas under `schemas/`.
