# Gate check

Status: Draft
Code: `check`, `.github/workflows/check.yml`
Verified against: main @ ca05de9

## Problem and decision

The registry gate ([gate spec](https://github.com/kadet-hub/registry/blob/main/docs/specs/gate.md))
judges a generator only once its tag is pinned in an entry pull request, so
every finding there costs a new tag. docker 1.0.0 was tagged and failed SEC-2:
GuardDog flagged the emitted `rm -rf` of the apt lists as
`threat-filesystem-destruction`, and `./check` ran no GuardDog.

`./check <generator>` runs the gate's own scripts from a kadet-hub/registry
checkout at `REGISTRY_REF` (default `main`, what the gate runs), and copies
none of their logic. What it cannot reproduce is what needs gVisor or the
registry entry: the syscall trace (SEC-10) and exceptions (SEC-14). No entry
has an exception today; a finding the maintainers excepted still fails
`./check`.

## Static scan

- CHK-1: `./check` MUST run the registry's `scan/static-scan` on the
  generator tree and fail on any finding.

  `static-scan` covers SEC-1 to SEC-6 and QA-3: the tree and import checks
  in the sandbox image, gitleaks, semgrep, ruff, GuardDog and ClamAV. Its
  `review:` and `warning:` lines are printed and do not fail, as in the gate.

  - Test: manual: plant a GuardDog `threat-*` string and a gitleaks token in
    a throwaway copy of a generator; `./check` fails on each
  - Since: #50

- CHK-2: `./check` MUST install the scanners at the registry's pins under its
  temporary directory, without global installs.

  gitleaks is the release tarball of `GITLEAKS_VERSION`, verified against
  `GITLEAKS_SHA256`, both read from the registry's
  `.github/actions/setup-gate/action.yml`. semgrep, GuardDog and ruff go into
  a uv virtual environment from `scan/requirements.txt` with
  `--require-hashes --no-deps`, for the Python version that file was
  compiled for. The gitleaks pin is the Linux x86-64 build and the pinned
  ClamAV image is amd64 only, so `./check` runs on Linux x86-64, like the
  gate.

  - Test: manual (as CHK-1)
  - Since: #50

ClamAV runs as in the gate, because `static-scan` runs it unconditionally and
skipping it would mean changing or copying that script. The first run pulls
the digest-pinned `clamav/clamav` image (about 390 MB); each run updates the
signatures with `freshclam`, or warns and scans with the shipped database.

## Compile

- CHK-3: `./check` MUST compile the fixture project with the registry's
  `sandbox/gate-compile`, in the sandbox image built from the registry's
  `sandbox/`, with `SANDBOX_TRACE=0`.
  - Test: manual: a fixture target that does not compile fails `./check`
  - Since: #28

## Workflow

- CHK-4: The `check` workflow MUST run `./check` for each generator a pull
  request or a push to `main` changes, and for every generator when `check`
  or `.github/` changes.
  - Test: manual: the job log names the generators it checks (`generators: ...`)
  - Since: #28

- CHK-5: The `check` workflow MUST NOT use workflow caches, as the
  registry's GI-10 requires for its own workflows.
  - Test: manual: review of `.github/workflows/check.yml`
  - Since: #39

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Script | `check`, needs docker, git, curl, uv, yq and python3 |
| Registry | `https://github.com/kadet-hub/registry.git` at `REGISTRY_REF`, default `main` |
| Scanner pins | registry `.github/actions/setup-gate/action.yml` (gitleaks), `scan/requirements.txt` (semgrep, GuardDog, ruff), `scan/static-scan` (ClamAV image digest) |
| Workflow | `.github/workflows/check.yml`, uv via `astral-sh/setup-uv` with `enable-cache: false` |
