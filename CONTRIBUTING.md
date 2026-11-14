# Contributing

You can report a problem with a generator, change one, or take over an
upstream update that the automation could not finish. All of it ends in a
pull request, described at the end.

To publish a generator of your own, start from
[generator-template](https://github.com/kadet-hub/generator-template) in
your own repository and list it as the registry's
[CONTRIBUTING.md](https://github.com/kadet-hub/registry/blob/main/CONTRIBUTING.md)
describes. A generator you would like someone else to write is requested
with the registry's
[generator request form](https://github.com/kadet-hub/registry/issues/new?template=generator-request.yml).

## Reporting a problem

Problems, questions and requests for a key go into an issue here. The
inventory block you compiled and the output you expected help most. A
vulnerability goes through private reporting, as [SECURITY.md](SECURITY.md)
describes.

## Changing a generator

Where [docs/specs/README.md](docs/specs/README.md) lists a spec for the
generator, the change starts there. The first commit of the pull request
adds or edits the requirement with its `Test:` line, and a last commit
sets `Since:` to the pull request's number. Requirement IDs are never
renumbered. [#184](https://github.com/kadet-hub/generators/pull/184) is a
recent example.

A change to the code or the rendered output also

- adds a heading for the new version at the top of the generator's
  `CHANGELOG.md`, which the registry gate requires for every release. The
  entries say whether output changes for inventories that do not use the
  change.
- documents a new key in the generator's `README.md`.
- sets the key in a fixture target under `tests/fixtures`, usually
  `complete`, so that `./check` compiles it and validates the output
  against the generator's schemas.
- extends the unit tests where the generator has `tests/test_*.py`.

A change to a README alone needs no new version. The catalog on
kadet-hub.org shows the README of the latest release, so it appears there
with the next one.

The gate scans the code and compiles the fixture project in a sandbox
without network. What it allows, such as the imports, is in the
[generator contract](https://kadet-hub.org/guides/writing-a-kapitan-generator/#generator-contract).

## Running the checks

`./check <generator>` runs the gate's static scan and the sandbox compile
of the fixture project with the registry's own scripts. It needs Linux
x86-64 with docker, git, curl, uv, yq and python3, and pulls a ClamAV
image of about 390 MB on the first run. The syscall trace needs gVisor and
runs only in the gate ([docs/specs/check.md](docs/specs/check.md)).

The `check` workflow runs the unit tests of every generator a pull request
changes, before `./check` (CHK-10 in [docs/specs/check.md](docs/specs/check.md)).
To run them yourself for the generator you change, from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' \
  --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider <generator>/tests
```

Bytecode in the tree fails the gate's scan, hence `PYTHONDONTWRITEBYTECODE`.
The tests of `ocm` and `mutate` run from their own directory, and those of
`opentelemetry-operator` need `--import-mode=importlib`, as their spec or
test file says.

A change to `tools/` or `.github/` also runs the tests of the upstream
tool, as CI does:

```sh
uv run --with pyyaml==6.0.3 python3 -m unittest discover -s tools
```

## Upstream updates

Every Monday the `upstream` workflow compares each generator's schemas
with the latest upstream release. When the new schemas pass `./check`, it
opens a pull request. When they do not, it opens an issue
`[upstream] <generator>: <software> <version>`, and the generator has to
be adapted by hand. Those issues are open for anyone to pick up. The
README's [Upstream updates](README.md#upstream-updates) shows how to run
the tool without writing anything.

## Pull requests

Open the pull request from a fork. Only maintainers and the upstream
automation push branches to this repository. Titles and commits follow
Conventional Commits with the generator as scope and the new version at
the end, as in
`feat(kubernetes): StatefulSet pod management policy and pod topology spread (1.16.0)`.
Commits here carry a `Signed-off-by` line (`git commit -s`). Please add
one, although no check enforces it.

The first workflow run of a new contributor waits until a maintainer
approves it. The `check` workflow then runs `./check` for every generator
the pull request changes, and for all of them when `check` or `.github/`
changes (CHK-4). `check` is the required status check, and the branch has
to be up to date with `main` before the merge.

`neat-bot`, a review bot with read access, reviews every pull request. On
a fork a maintainer requests it after a first look (CHK-6). Its approval
does not count toward the merge. A pull request merges once `check` passed
and a maintainer approved it, and a push after the approval dismisses it.

After the merge the maintainer tags the release `<generator>-v<version>`
and proposes it in kadet-hub/registry, whose gate checks the generator
again before the release is published.
