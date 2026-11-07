# Default images

Status: Draft
Code: `tools/default_images.py`, `.github/workflows/images.yml`, `renovate.json`
Verified against: main @ 1ea7e4e

## Problem and decision

Some generators write container images into their output when the
inventory names none: kind its node images, kubevirt the CSI driver and
sidecars, talos the Kubernetes components and the installer. Consumers run
these images, so their known vulnerabilities matter. On 2026-10-29 trivy
0.76.1 counted up to 478 advisory IDs, 10 of them critical, across the 18
defaults. These images are upstream's, and the fix is a newer default.

The kadet-hub catalog shows consumers a security report per default image.
This repository gets a weekly scan for the maintainers, which reports and
does not block. A gate on pull requests was considered and rejected,
because it would block unrelated changes on advisories that only upstream
can fix.

## Pinning

- IMG-1: Every default image MUST be pinned by tag and digest, written as
  one Python string literal `<repository>:<tag>@sha256:<digest>` in the
  generator's code outside `tests/`.

  One literal per image lets the scan and an update bot find each image
  without running the generator. Implicit concatenation of adjacent
  literals counts as one literal, because Python's parser joins them.
  The repository part must contain a `/`, which also excludes fragments
  such as a tag joined to a registry prefix at runtime.

  A literal without whitespace whose `@sha256:` is not followed by 64
  lowercase hex digits up to its end fails the extraction, and with it
  the scan (IMG-2). A mistyped digest would otherwise drop the image
  from the scan while the literal still reads as pinned.

  - Test: `tools/test_default_images.py`; the scan's job summary lists
    every default image
  - Since: this change

## Weekly scan

- IMG-2: The `images` workflow MUST scan every default image with trivy
  weekly and on manual dispatch, and MUST list the advisory count per
  severity for each image in the job summary. Findings MUST NOT fail the
  job. An image that cannot be scanned MUST fail it.

  The counts are unique advisory IDs per image, as trivy reports them.
  Aliases between CVE, GHSA and distribution IDs are not merged. trivy is
  installed from its release tarball at a pinned version, verified against
  a pinned SHA-256, and runs without a workflow cache (CHK-5). The version
  is the release tag, because Renovate's `github-release-attachments`
  datasource looks the release up by it and hashes the new tarball
  (IMG-3).

  - Test: manual: dispatch the workflow; the summary lists every image
    `tools/default_images.py` prints, with counts
  - Since: this change

## Updates

- IMG-3: Renovate MUST propose patch and digest updates of every default
  image, in one pull request per generator, and MUST NOT propose their
  minor or major updates.

  A regex manager in `renovate.json` reads the literals of IMG-1 with the
  pattern of `tools/default_images.py`, and `config:recommended` skips
  `tests/`. A minor is the generator's decision: kind keeps one node image
  per Kubernetes minor, and talos pins the Kubernetes components to the
  minor its Talos release supports. Even a patch changes the rendered
  output, so the pull request is a proposal like an upstream pull request
  (UPD): the reviewer sets the generator version and CHANGELOG entry
  before merging. Renovate merges none of its pull requests here.

  The kubevirt CSI driver (KV-2) is kadet-hub's mirror, tagged by commit
  and written as two adjacent literals, so Renovate does not read it.

  `renovate.json` also moves the action pins of the workflows, the uv
  version of `setup-uv` and trivy (IMG-2), each after three days. Registries
  other than Docker Hub report no release date, so their images are not
  held. The schemas in `sources.yaml` stay with the upstream workflow
  (UPD-1).

  - Test: manual: `renovate --platform=local --dry-run=lookup`. On
    2026-11-07 Renovate 44.188.2 proposed argocd v3.5.7 and redis
    8.2.11-alpine on `renovate/patch-argocd-default-images`, trivy v0.76.2,
    setup-uv v10.3.3 and uv 0.13.7. It also listed the minors argocd
    v3.6.1, dex v2.46.1 and kindest/node v1.37.0, which the package rule
    disables when Renovate builds the branches; `--platform=local` stops
    before that step.
  - Since: #185

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Extraction | `tools/default_images.py`, prints `<generator> <image>` per line |
| Workflow | `.github/workflows/images.yml`, cron weekly Monday 04:00 UTC, `workflow_dispatch` |
| Scanner | trivy release tarball, version (release tag) and SHA-256 in the workflow, moved by Renovate |
| Updates | `renovate.json`: default-image and trivy regex managers, minors and majors of default images disabled, one group per generator |
