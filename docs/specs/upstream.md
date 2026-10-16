# Upstream schema updates

Status: Draft
Code: `tools/upstream.py`, `tools/workflow-policy`, `.github/workflows/upstream.yml`, `.github/ruleset-*.json`
Verified against: main @ 313f1ca

## Problem and decision

Each generator ships the JSON Schemas of the software it targets in
`<generator>/schemas/`, and `schemas/sources.yaml` names the software,
version and pinned upstream URL of each schema group. Some also ship the
CRDs of their kinds in `schemas/<group>/crds/` under the same entry (QA-12
of the registry's [gate spec](https://github.com/kadet-hub/registry/blob/main/docs/specs/gate.md)).
The catalog's "Built for" comes from these entries. Nothing notices when
upstream releases a new version, so schemas, CRDs and "Built for" fall
behind until someone checks by hand.
Renovate cannot close the gap: a version bump in `sources.yaml` without
regenerated schema files is wrong, and the hosted Renovate app runs no
post-upgrade commands.

A weekly workflow compares every `sources.yaml` entry with the latest
upstream release. The groups whose schemas regenerate mechanically and pass
`./check` go into a pull request, the rest into an issue; one generator can
have both. The pull request is a proposal: the reviewer still checks the generator's
defaults and code against the new release, and sets the generator version
and CHANGELOG entry before merging.

## Detection

- UPD-1: The workflow MUST run weekly and on manual dispatch, and MUST
  report every `sources.yaml` entry whose upstream has a newer release than
  the entry's `version`.

  Where the newer release comes from depends on the `source`:

  | Source | Newer release |
  |---|---|
  | GitHub `tree` or `blob` URL at a release tag, of CRD YAML or of an OpenAPI v3 JSON document | the repository's highest release that is neither pre-release nor draft |
  | kubernetes-json-schema at a commit | the highest Kubernetes release (`kubernetes/kubernetes`) |
  | Terraform Registry provider URL | the provider's highest version in the Terraform Registry |
  | GitHub URL at a commit (`version: main@<sha>`) | the repository's first release, if one exists by now |

  A repository without releases falls back to its tags, for example
  `keycloak/keycloak-k8s-resources`. Versions are compared as semantic
  versions after stripping the tag prefix the current ref uses (`v`,
  `edge-`, none); a tag with a pre-release suffix does not count.

  The highest version counts, not GitHub's latest flag, because some
  projects publish patch releases of older lines after a newer release
  (`tigera/operator` v1.40.16 after v1.44.0).

  A source of several space-separated URLs, with their versions separated
  by ` / ` in `version`, is checked per URL. A single `version` applies to
  every URL, and the label shows it once while all URLs share it. A source matching none of the
  rows is reported as unchecked in the workflow log.

  - Test: `tools/test_upstream.py`
  - Since: #39, #43, #56

## Regeneration

- UPD-2: The workflow MUST regenerate a schema group only if regenerating
  it at the entry's current ref reproduces the committed schema files and
  CRD files byte for byte.

  The schemas of the existing generators were produced by several hands:
  most carry top-level `$id`, `$schema` and `title` annotations or a
  rewritten `description`, and some are written without indentation to stay
  below the 1 MiB file limit (`installation_v1.json` of calico). Regeneration
  keeps these, and the reproduction check proves the tool reads the same
  upstream files and applies the same transformation before it is trusted
  with a new release. A group that does not reproduce becomes an issue
  (UPD-4).

  Regeneration reads the CRD YAML files under the source path at the new
  tag, takes the `openAPIV3Schema` of each `<kind>_<version>.json` already
  in the group directory, adds `apiVersion`, `kind` and `metadata` where
  missing and closes it like kubeconform strict mode (`additionalProperties:
  false` on every node with `properties`, except preserve-unknown-fields
  nodes and `allOf`/`anyOf`/`oneOf`/`not` branches). It adds no kinds and
  no versions; a kind or version missing at the new tag is an issue.
  CustomResourceDefinition documents without `spec.versions`, such as the
  conversion and CA-injection patches next to KServe's CRDs, are skipped.

  A source ending in `.json` is read as an OpenAPI v3 document instead. An
  aggregated API server such as IronCore's serves its kinds without CRDs
  and publishes one such document per API group version
  (`gen/v3/apis__<group>__<version>_openapi.json`). For each
  `<kind>_<version>.json` regeneration takes the component schema whose
  `x-kubernetes-group-version-kind` names that kind and version, copies
  every component it references, directly or through other components,
  under `definitions` sorted by name with `$ref` rewritten from
  `#/components/schemas/` to `#/definitions/`, and closes the schema and
  each definition as above. A JSON document without components, such as
  k3d's JSON Schema source, yields no schema and does not reproduce.

  Each schema file keeps the committed file's top-level `$id`, `$schema`,
  `title` and `description`, where present, and its layout: the same
  indent, or compact if the committed file is a single line. Keys are
  sorted if the committed file's keys are sorted at every level; otherwise
  they keep the upstream order, with the top level in the committed file's
  order.

  Each committed CRD file, `crds/<plural>.yaml` or `crds/<plural>.json`,
  is regenerated from the CustomResourceDefinition with the group as
  `spec.group` and that `spec.names.plural` in the YAML files under the
  source path, in the form QA-12 decides: the upstream file byte for byte when it holds no other
  document and is at most 1 MiB, otherwise the CRD as compact JSON with
  keys in upstream order, non-ASCII characters escaped and a final newline.
  Empty documents do not count, as in the gate. The form follows the
  upstream file at each tag, so a CRD that grows past 1 MiB or moves into a
  file with other documents replaces `<plural>.yaml` with `<plural>.json`,
  and the other way round. Regeneration adds no CRD files; a CRD missing at
  the new tag is an issue. An OpenAPI v3 source has no CRDs, so a CRD file
  in its group does not reproduce.

  The registry gate compares neither JSON Schemas nor CRD files with
  upstream, so the reproduction is what ties a committed CRD file to its
  source before a new release replaces it. CRDs that upstream keeps only
  in Go code or Helm templates, such as CDI's and Linkerd's, have no file
  to copy; their sources stay not regenerable (UPD-4).

  - Test: `tools/test_upstream.py`
  - Since: #39, #40, #43, #61

## Pull requests and issues

- UPD-3: For the groups of a generator that regenerate, the workflow MUST
  open one pull request, or update its open one, on branch
  `upstream/<generator>`, if `./check` passes with them.

  The pull request changes those groups' schema and CRD files, their
  `version` and `source` in `sources.yaml`, and their versions in the
  README's "Built for" line. It does not bump the generator version or
  edit the CHANGELOG. The body lists each group's version before and after
  and the tail of `./check`. An open pull request that already proposes
  these versions is left alone; a newer release force-pushes the branch,
  replacing commits pushed to it.

  - Test: `tools/test_upstream.py`; manual: dispatch the workflow
  - Since: #39, #61

- UPD-4: For the groups of a generator whose newer release cannot be
  proposed in a pull request, the workflow MUST open one issue, or update
  its open one, titled `[upstream] <generator>: <software> <version>`.

  A generator can have this issue and the pull request of UPD-3 at the same
  time. Several software versions in one title are joined with `, `. The
  causes are: the group does not reproduce (UPD-2), its source is not
  regenerable (Go code, Helm templates, Terraform extracts,
  kubernetes-json-schema), a kind, version or CRD is missing at the new
  tag, or `./check` fails with the regenerated groups. The body names the
  cause per group and, for a failing check, its tail.

  - Test: `tools/test_upstream.py`
  - Since: #39, #61

## Credentials

- UPD-5: The workflow MUST authenticate with a token of the kadet-hub GitHub
  App, scoped to this repository with contents, pull requests and issues
  write, and MUST NOT use workflow caches.

  `GITHUB_TOKEN` cannot open pull requests here: the repository setting that
  allows it also lets Actions approve pull requests, which would satisfy the
  one-approval rule of the `main` ruleset. Pull requests opened with
  `GITHUB_TOKEN` also do not trigger the `check` workflow; App tokens do.
  The App's client ID and private key are the secrets `APP_CLIENT_ID` and
  `APP_PRIVATE_KEY` of the environment `upstream` (UPD-6); the token
  action's `app-id` input is deprecated in favour of `client-id`.

  - Test: manual: dispatch the workflow and confirm the pull request runs `check`
  - Since: #39

- UPD-6: The `upstream` job MUST name the environment `upstream`, whose
  deployment branch policy admits only the branch `main`, and the App's
  client ID and private key MUST be secrets of that environment, not of
  the repository.

  A repository secret reaches a workflow on any branch, and the maintainer
  and Renovate can push workflows. An environment secret reaches only a
  job that names the environment, and GitHub sends such a job to a runner
  only when its ref matches the policy. With the key, anyone holds the
  App's contents, pull request and issue write until the key is rotated.

  `tools/workflow-policy` fails the `check` workflow when a job that reads
  a secret other than `GITHUB_TOKEN`, or holds `contents`, `packages`,
  `id-token`, `attestations` or `pages` write, names no environment, names
  one whose policy admits anything but `main`, or is part of a
  `pull_request_target` workflow, where GitHub evaluates the policy
  against the default branch. Where a secret is stored the check cannot
  see: listing secrets needs a permission `GITHUB_TOKEN` cannot hold.

  - Test: `tools/workflow-policy` in the `check` workflow; manual:
    `gh api repos/kadet-hub/generators/actions/secrets` lists neither secret
  - Since: this change

## Branches and tags

- UPD-7: Rulesets MUST restrict creating, updating and deleting branches
  other than `main` to the admin role, branches under `upstream/` to the
  `kadet-hub-upstream` App and the admin role, and creating tags to the
  admin role.

  Renovate holds `contents` and `workflows` write on every repository of
  the organization but has no configuration here, so no ruleset admits it
  and it can push no branch. The App holds `contents` write without
  `workflows`; without the tag rule its key could create a release tag
  `<generator>-v<semver>` on any commit the repository holds, such as an
  unmerged branch, and the registry's Renovate would propose that tag as
  an entry bump. The maintainer creates the release tags. The `release
  tags` ruleset, which blocks updating and deleting `*-v*` tags with no
  bypass, stays as it is, and so does the `main` ruleset.

  The rulesets do not limit the maintainer, and they do not stop the App
  from pushing what it likes to `upstream/` branches; the `main` ruleset's
  review is the control there.

  - Test: manual: `gh api repos/kadet-hub/generators/rulesets` matches
    `.github/ruleset-branches.json`, `.github/ruleset-upstream.json` and
    `.github/ruleset-tags.json`
  - Since: this change

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Script | `tools/upstream.py`, tests `tools/test_upstream.py`, run by the `check` workflow when `tools/` or `.github/` changes |
| Workflow | `.github/workflows/upstream.yml`, cron weekly Monday 03:00 UTC, `workflow_dispatch` |
| Branch | `upstream/<generator>` |
| Issue title | `[upstream] <generator>: <software> <version>` |
| Secrets | `APP_CLIENT_ID`, `APP_PRIVATE_KEY` (GitHub App) in the environment `upstream`, deployment branch `main` only |
| Rulesets | `.github/ruleset-branches.json`, `.github/ruleset-upstream.json`, `.github/ruleset-tags.json`, applied with `gh api` |
| Workflow policy | `tools/workflow-policy`, run by the `check` workflow |
