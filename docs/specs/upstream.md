# Upstream schema updates

Status: Draft
Code: `tools/upstream.py`, `.github/workflows/upstream.yml`
Verified against: main @ 313f1ca

## Problem and decision

Each generator ships the JSON Schemas of the software it targets in
`<generator>/schemas/`, and `schemas/sources.yaml` names the software,
version and pinned upstream URL of each schema group. The catalog's "Built
for" comes from these entries. Nothing notices when upstream releases a new
version, so schemas and "Built for" fall behind until someone checks by hand.
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
  | GitHub `tree` or `blob` URL at a release tag | the repository's highest release that is neither pre-release nor draft |
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
  by ` / ` in `version`, is checked per URL. A source matching none of the
  rows is reported as unchecked in the workflow log.

  - Test: `tools/test_upstream.py`
  - Since: #39

## Regeneration

- UPD-2: The workflow MUST regenerate a schema group only if regenerating
  it at the entry's current ref reproduces the committed schema files byte
  for byte.

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

  Each file keeps the committed file's top-level `$id`, `$schema`, `title`
  and `description`, where present, and its layout: the same indent, or
  compact if the committed file is a single line. Keys are sorted if the
  committed file's keys are sorted at every level; otherwise they keep the
  upstream order, with the top level in the committed file's order.

  - Test: `tools/test_upstream.py`
  - Since: #39

## Pull requests and issues

- UPD-3: For the groups of a generator that regenerate, the workflow MUST
  open one pull request, or update its open one, on branch
  `upstream/<generator>`, if `./check` passes with them.

  The pull request changes those groups' schema files, their `version` and
  `source` in `sources.yaml`, and their versions in the README's "Built for"
  line. It does not bump the generator version or edit the CHANGELOG. The
  body lists each group's version before and after and the tail of
  `./check`. An open pull request that already proposes these versions is
  left alone; a newer release force-pushes the branch, replacing commits
  pushed to it.

  - Test: `tools/test_upstream.py`; manual: dispatch the workflow
  - Since: #39

- UPD-4: For the groups of a generator whose newer release cannot be
  proposed in a pull request, the workflow MUST open one issue, or update
  its open one, titled `[upstream] <generator>: <software> <version>`.

  A generator can have this issue and the pull request of UPD-3 at the same
  time. Several software versions in one title are joined with `, `. The
  causes are: the group does not reproduce (UPD-2), its source is not
  regenerable (Go code, Helm templates, Terraform extracts,
  kubernetes-json-schema), a kind or version is missing at the new tag, or
  `./check` fails with the regenerated groups. The body names the cause per
  group and, for a failing check, its tail.

  - Test: `tools/test_upstream.py`
  - Since: #39

## Credentials

- UPD-5: The workflow MUST authenticate with a token of the kadet-hub GitHub
  App, scoped to this repository with contents, pull requests and issues
  write, and MUST NOT use workflow caches.

  `GITHUB_TOKEN` cannot open pull requests here: the repository setting that
  allows it also lets Actions approve pull requests, which would satisfy the
  one-approval rule of the `main` ruleset. Pull requests opened with
  `GITHUB_TOKEN` also do not trigger the `check` workflow; App tokens do.
  The App's client ID and private key are the repository secrets
  `APP_CLIENT_ID` and `APP_PRIVATE_KEY`; the token action's `app-id` input
  is deprecated in favour of `client-id`.

  - Test: manual: dispatch the workflow and confirm the pull request runs `check`
  - Since: #39

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Script | `tools/upstream.py`, tests `tools/test_upstream.py`, run by the `check` workflow when `tools/` or `.github/` changes |
| Workflow | `.github/workflows/upstream.yml`, cron weekly Monday 03:00 UTC, `workflow_dispatch` |
| Branch | `upstream/<generator>` |
| Issue title | `[upstream] <generator>: <software> <version>` |
| Secrets | `APP_CLIENT_ID`, `APP_PRIVATE_KEY` (GitHub App, repository-scoped) |
