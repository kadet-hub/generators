# Default images

Status: Draft
Code: `tools/default_images.py`, `.github/workflows/images.yml`
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
  a pinned SHA-256, and runs without a workflow cache (CHK-5).

  - Test: manual: dispatch the workflow; the summary lists every image
    `tools/default_images.py` prints, with counts
  - Since: this change

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Extraction | `tools/default_images.py`, prints `<generator> <image>` per line |
| Workflow | `.github/workflows/images.yml`, cron weekly Monday 04:00 UTC, `workflow_dispatch` |
| Scanner | trivy release tarball, version and SHA-256 in the workflow |
