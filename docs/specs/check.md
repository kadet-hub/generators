# Gate check

Status: As-built
Code: `check`, `.github/workflows/check.yml`, `.github/workflows/request-review.yml`
Verified against: main @ fbe8c39

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
  `.github/actions/setup-gate/action.yml`. `GITLEAKS_VERSION` is the release tag
  with its leading `v`, as the registry pins it since registry #292; the
  tarball name carries the version without it. semgrep, GuardDog and ruff go into
  a uv virtual environment from `scan/requirements.txt` with
  `--require-hashes --no-deps`, for the Python version that file was
  compiled for. The gitleaks pin is the Linux x86-64 build and the pinned
  ClamAV image is amd64 only, so `./check` runs on Linux x86-64, like the
  gate.

  - Test: manual (as CHK-1)
  - Since: #50, #92

- CHK-9: With `GH_TOKEN` in its environment, `./check` MUST download from
  GitHub with that token. The `check` workflow MUST give it the job's
  read-only `GITHUB_TOKEN`.

  gitleaks then comes through the REST API with `gh release download`,
  because github.com ignores a token on a release download URL, and the
  sandbox image build gets the token as the secret `GH_TOKEN` for its own
  downloads from GitHub (registry GI-6). Without `GH_TOKEN`, as in a local
  run and in the `upstream` job (UPD-8), both stay anonymous and `gh` is
  not needed. GitHub rate-limits anonymous requests more tightly, and on
  2026-11-08, during its timeouts for unauthenticated users, the same
  anonymous downloads failed registry and recipes CI with HTTP 504. The
  clone of the registry stays anonymous: git sends credentials only when
  the server asks for them, which GitHub does not for a public
  repository.

  - Test: the `check` workflow on a pull request that changes `check`
    (every generator is checked, CHK-4)
  - Since: #188

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

  What a pull request changes is the diff between the merge commit that
  `actions/checkout` checks out and its first parent, the `main` commit
  GitHub merged the pull request into. `pull_request.base.sha` is the
  `main` commit the pull request was last synchronised with. On a pull
  request behind `main` it is older, and the diff against it also holds
  everything `main` changed since, up to every generator when that
  touches `check` or `.github/` (#142). A push to `main` diffs against
  `github.event.before`. The tests of `tools/upstream.py` use the same
  base.

  - Test: manual: the job log names the generators it checks
    (`generators: ...`); on a pull request behind `main` only those the
    pull request changes
  - Since: #28, #159

- CHK-10: The `check` workflow MUST run the unit tests of each generator
  it checks (CHK-4) that has `tests/test_*.py`, before `./check`, and fail
  when a test fails.

  Each suite runs with the command of its spec's implementation inventory,
  with pytest, kapitan and omegaconf pinned. ocm and mutate import their
  modules by top-level name, so their suites run from the generator's
  directory, and ocm's also needs jsonschema. opentelemetry-operator runs
  with `--import-mode=importlib`, because its directory name is no Python
  identifier. `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` keep
  bytecode and the pytest cache out of the tree, which the scan of the
  following `./check` would fail (SEC-5).

  - Test: manual: the job log names each suite it runs
    (`unit tests: <generator>`); a broken assert fails the step; a pull
    request that changes only generators without tests runs none
  - Since: this change

- CHK-5: The `check` workflow MUST NOT use workflow caches, as the
  registry's GI-10 requires for its own workflows.
  - Test: manual: review of `.github/workflows/check.yml`
  - Since: #39

- CHK-8: The `check` workflow MUST run `docker compose config` on
  `docker/tests/golden/compose.yml` and fail when Compose rejects it.

  The golden is the Compose file the docker generator writes for its
  fixture ([docker.md](docker.md)). The gate validates no Compose file,
  because QA-7 covers documents with `apiVersion` and `kind` only. The
  step uses the Docker Compose that the `ubuntu-24.04` runner image ships,
  so its version follows the image and is not pinned. It takes about a
  second and runs on every pull request and push.

  - Test: manual: the step's log; a golden with an unknown service key
    fails it
  - Since: #183

- CHK-6: Every pull request MUST request a review from `neat-bot`. That
  review MUST NOT be a condition for merging.

  The `request review` workflow requests `neat-bot` with the repository's
  own token when a pull request is opened, reopened or marked ready. It
  skips drafts, pull requests opened by bots, and pull requests from forks,
  whose token is read-only; on a fork the reviewer is requested by hand after
  a look at it. `neat-bot` has read access only (terraform-homezone GHO-6a),
  so CODEOWNERS, which requests a code owner only with write access, cannot
  do it, and an approval by `neat-bot` does not count toward the one approval
  the `main` ruleset requires. That approval comes from a person; UPD-5 keeps
  `GITHUB_TOKEN` from giving it.

  - Test: manual: on a new pull request the `request review` run succeeds and
    `gh pr view <n> --json reviewRequests` lists `neat-bot`;
    `gh api repos/kadet-hub/generators/collaborators/neat-bot/permission`
    reports `read`
  - Since: #105 (CODEOWNERS), #108 (workflow)

## Schema licences

- CHK-7: `./check` MUST fail when an entry of the generator's
  `sources.yaml` names no `license`, or one that is not an identifier in
  the registry's `policy/licenses.txt`.

  This is the licence gate for the vendored schemas (TP-1 of
  [third-party.md](third-party.md)). The registry's list is the one the
  gate applies to the generator's own licence (QA-2), read from the same
  checkout at `REGISTRY_REF`. A copyleft licence on that list, such as
  GPL-3.0-only, passes here as it passes there. The check runs before the
  sandbox image is built, so a missing licence fails within seconds.

  - Test: manual: in a throwaway copy of a generator, `./check` fails with
    `license` removed from an entry and with `license: WTFPL`, and passes
    with `license: GPL-3.0-only`
  - Since: #133

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| Script | `check`, needs docker, git, curl, uv, yq and python3, and gh with `GH_TOKEN` (CHK-9) |
| Registry | `https://github.com/kadet-hub/registry.git` at `REGISTRY_REF`, default `main` |
| Scanner pins | registry `.github/actions/setup-gate/action.yml` (gitleaks), `scan/requirements.txt` (semgrep, GuardDog, ruff), `scan/static-scan` (ClamAV image digest) |
| Workflow | `.github/workflows/check.yml`, uv via `astral-sh/setup-uv` with `enable-cache: false` |
| Review request | `.github/workflows/request-review.yml`, `pull_request` (CHK-6) |
| Licence allow list | registry `policy/licenses.txt`, first column (CHK-7) |
| Compose validation | `.github/workflows/check.yml`, `docker compose config --quiet` on `docker/tests/golden/compose.yml` (CHK-8) |
| Unit tests | `.github/workflows/check.yml`, step for CHK-10: pytest 9.2.0, kapitan 0.36.3, omegaconf 2.4.0.dev4, and jsonschema 4.26.0 for ocm |
