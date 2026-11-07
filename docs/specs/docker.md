# docker generator

Status: Draft
Code: `docker/`
Verified against: main @ 177cbc0

## Problem and decision

The docker generator had no spec. Up to 1.0.2 it renders Dockerfiles,
described in `docker/README.md`; that behaviour is unchanged and moves in
here when a change touches it.

The compose-kubernetes example in kadet-hub/examples (EX-30 there) runs one
inventory on Kubernetes and on a Docker host. Its Kubernetes target
compiles the components with the kubernetes generator. Its Compose target
compiles them with a 77-line kadet component of the example's own, which
maps the component keys the miniflux recipe uses and fails the compile on
any other key. A project that wants the same has to copy that component.

DEC-1: The docker generator writes a Compose file from
`parameters.components`, the block the kubernetes generator reads, so one
class feeds both outputs. The switch and the settings only a Docker host
needs live in `generators.docker.compose`. A component key without a
Compose counterpart fails the compile, as in EX-30, so nothing the cluster
gets is dropped without a message. The rejected options are in
[Alternatives](#alternatives).

## Switch and output

- DKR-1: With `generators.docker.compose` set to a mapping, `{}`
  included, the generator MUST write `compose.yml` next to the Dockerfiles
  of the same compile entry. Without it, or with `null`, it MUST write no
  `compose.yml`, and the Dockerfile output MUST stay byte-identical to
  1.0.2. Any other value MUST fail the compile.

  The compile entry is the one Dockerfiles already need, with
  `output_type: plain`, and the generator writes the Compose file as YAML
  text. Kapitan handles refs in plain output as in YAML output: without
  `--reveal` a `?{...}` token becomes its hashed tag. A target that
  compiles Dockerfiles and Kubernetes manifests from the same inventory
  keeps its output, because its components render nothing here without
  the switch.

  - Test: `docker/tests/test_compose.py::test_without_switch`; `manual:`
    Kapitan 0.36.3 compiles fixture targets `minimal` and `complete` on
    reclass-rs and omegaconf to the same files as 1.0.2
  - Since: this change

## Components

- DKR-2: Each component of `parameters.components` MUST become the Compose
  service of the same name, after the defaults the kubernetes generator
  merges into it: `applications.<application>.component_defaults`, then
  `generators.manifest.default_config`, then
  `generators.manifest.resource_defaults.<type>`, each filling only keys
  the component leaves unset or `null`. A component whose `enabled` is
  false MUST render no service.

  Order and fill rule are those of `get_components` in the kubernetes
  generator 1.15.0. A key from a default counts like a key of the
  component, so a `security_profile` in `default_config` fails the Compose
  compile as well. The miniflux recipe sets `enable_service_links: false`
  through its application defaults.

  - Test: `docker/tests/test_compose.py::test_defaults`, `::test_disabled`
  - Since: this change

- DKR-3: A component key MUST render as the table below states. Any other
  key, and a value the table does not allow, MUST fail the compile with
  an error that names the component and the key.

  | Key | Compose | Accepted |
  |---|---|---|
  | `image` | `image` | required |
  | `command` | `entrypoint` | list |
  | `args` | `command` | list, or mapping as in K8S-4 of [kubernetes.md](kubernetes.md) |
  | `env` | `environment` | scalars as strings, refs as in DKR-5 |
  | `secrets`, `config_maps` | none | the sources of DKR-5 only |
  | `ports` | `expose` | `container_port`, else `service_port`, with `/udp` or `/sctp` for those protocols |
  | `volume_mounts`, `volume_claims` | `volumes` | DKR-8 |
  | `healthcheck` | `healthcheck` | DKR-6 |
  | `resources` | `deploy.resources` | DKR-7 |
  | `security_context` | `user`, `read_only` | `runAsUser`, `runAsGroup` (with `runAsUser`), `readOnlyRootFilesystem` |
  | `read_only_root_filesystem` | `read_only` | applies when `security_context` leaves `readOnlyRootFilesystem` unset |
  | `type` | `restart: always` | `deployment` (default), `statefulset` |
  | `application`, `enabled` | none | read by DKR-2 |
  | `service` | none | any |
  | `enable_service_links` | none | `false` |

  Kubernetes `command` replaces the image's ENTRYPOINT and `args` its CMD,
  which is what Compose's `entrypoint` and `command` do. A Deployment or
  StatefulSet restarts its container whatever the exit code, as `restart:
  always` does. Compose's default network resolves each service name, the
  part of `service` a container sees; the Service port is not carried
  over, so clients reach a service on its container port. A port's
  other fields only shape that Service. Compose sets no service link
  variables, which is what `enable_service_links: false` asks for.

  - Test: `docker/tests/test_compose.py::test_golden` against
    `docker/tests/golden/compose.yml` (fixture target `compose`),
    `::test_command_and_args`, `::test_user_and_read_only`,
    `::test_refusals`
  - Since: this change

- DKR-4: A `$` in a value the generator takes from a component MUST be
  written as `$$`. A value of `env`, `command` or `args` that contains
  `$(` or `$$` MUST fail the compile.

  Compose interpolates `$VAR` and `${VAR}` in every value from the host's
  environment and reads `$$` as one `$`. Kubernetes passes `$` through,
  except in `env`, `command` and `args`, where it expands `$(VAR)` with the
  container's variables and reads `$$` as one `$`
  ([dependent environment variables](https://kubernetes.io/docs/tasks/inject-data-application/define-interdependent-environment-variables/)).
  Compose has no such expansion. Such a value fails instead of reaching
  the container in another form. Values from `generators.docker.compose`
  (DKR-9) are written as given, with Compose interpolation.

  - Test: `docker/tests/test_compose.py::test_dollar`
  - Since: this change

## Environment and refs

- DKR-5: An `env` value `secretKeyRef` with `key` only MUST render the
  `value` of that key from the first of the component's `secrets` whose
  `string_data` holds it, and `configMapKeyRef` with `key` only from the
  first of its `config_maps` whose `data` holds it. Any other `env`
  mapping, such as `fieldRef` or a ref with `name`, a `secrets` entry with
  a key other than `string_data`, a `config_maps` entry with a key other
  than `data`, and an item with a key other than `value` MUST fail the
  compile. A Kapitan ref in a value MUST pass through as written.

  Compose has no reference from a variable to a secret, so the value goes
  into `environment`, as in EX-30. Kapitan turns the ref into its hashed
  tag on compile, and into its value only with `--reveal` or `kapitan refs
  --reveal -f`, so the compiled file holds no secret. Kapitan writes a
  revealed value into the text after the generator, so DKR-4 cannot escape
  it and YAML reads it unquoted: a `$` in it is interpolated by Compose,
  and a value YAML reads as something else, such as one that starts with
  `*`, breaks the file. Kapitan's `random:str` makes letters and digits
  only. Lookup by first match is the kubernetes generator's
  (`find_key_in_config`). Secret `data` is left out because the
  kubernetes generator base64-encodes it, except a ref, which must already
  hold base64.

  - Test: `docker/tests/test_compose.py::test_golden`, `::test_refusals`;
    `manual:` the compiled fixture target `compose` holds hashed ref tags
  - Since: this change

## Health check

- DKR-6: `healthcheck.readiness` with `type: command` MUST render as
  `healthcheck` with `test` `[CMD, <command>...]`, `interval` from
  `period_seconds` (default 10), `timeout` from `timeout_seconds` (5),
  `retries` from `failure_threshold` (3), and `start_period` from
  `initial_delay_seconds` when that is set and not 0, in seconds. A
  readiness probe of another type, a `startup` or `liveness` probe with a
  `type`, and a probe key other than these MUST fail the compile. Probes
  without `type` MUST render nothing.

  The defaults are the ones the kubernetes generator writes. A Docker
  health check runs inside the container, so an `http`, `tcp` or `grpc`
  probe needs a client in the image, which the generator cannot see.
  Docker runs one health check and restarts no unhealthy container, so
  `liveness` and `startup` have no counterpart. Such a probe goes into the
  Kubernetes target, and a Compose `healthcheck` that uses a tool the
  image has into `generators.docker.compose.services.<name>`. The
  kubernetes generator renders no probe for an entry without `type`.

  - Test: `docker/tests/test_compose.py::test_golden`, `::test_refusals`,
    `::test_probe_without_type_renders_nothing`
  - Since: this change

## Resources

- DKR-7: `resources.limits` MUST render as `deploy.resources.limits` and
  `resources.requests` as `deploy.resources.reservations`, `cpu` as
  `cpus` in cores (`100m` as `"0.1"`) and `memory` in `Ki`, `Mi` or `Gi`
  as `k`, `m` or `g`. Another resource name, another memory form and
  another key under `resources` MUST fail the compile.

  Docker reads `k`, `m` and `g` as powers of 1024: Compose 5.6.1 turns
  `256m` into 268435456 bytes. On one Docker host Compose 5.6.1 applies
  the memory reservation as a soft limit (`MemoryReservation`) and no CPU
  reservation; Swarm uses both for placement. Decimal memory suffixes and
  plain byte counts appear in no recipe of kadet-hub/recipes and are left
  out.

  - Test: `docker/tests/test_compose.py::test_resources`, `::test_refusals`
  - Since: this change

## Volumes

- DKR-8: Each `volume_claims` entry MUST render as a top-level named
  volume of the same name. A `volume_mounts` entry whose volume (`volume`,
  else its key) is a claim of the component MUST render as
  `<claim>:<mount_path>`, with `:ro` when `read_only` is true. A mount of
  any other volume, a mount key other than `mount_path`, `volume` and
  `read_only`, and a claim name used by two components MUST fail the
  compile.

  A StatefulSet gets one PersistentVolumeClaim per pod from each template;
  a Compose service on one host gets one named volume. Size, access modes
  and storage class have no Compose counterpart and are not read. Two
  components with a claim of the same name would share one volume under
  Compose.

  - Test: `docker/tests/test_compose.py::test_golden`, `::test_volumes`,
    `::test_refusals`
  - Since: this change

## Docker host settings

- DKR-9: `generators.docker.compose` MUST be merged over the document the
  components render: mappings key by key, any other value replacing the
  rendered one, `null` removing it.

  This is where a Docker host's own settings go: published `ports`,
  `depends_on`, another `restart`, a `healthcheck` in place of a probe
  DKR-6 refuses, services that are no component, the project `name`. They
  are Compose as written. The generator does not check them;
  `docker compose config` does.

  - Test: `docker/tests/test_compose.py::test_golden`, `::test_overrides`
  - Since: this change

## Verification

`./check docker` compiles fixture target `compose` in the gate's sandbox
on both inventory backends and runs SEC-12 on `compose.yml`, which the
gate parses as YAML. The gate validates no Compose file: QA-7 covers
documents with `apiVersion` and `kind`. The golden
`docker/tests/golden/compose.yml` is what the generator writes for that
target before Kapitan turns refs into tags; `test_golden` compares it,
and the `check` workflow runs `docker compose config` on it (CHK-8 of
[check.md](check.md)). That the fixture starts under Docker, with
Miniflux healthy behind its published port, was shown once by hand
(implementation inventory) and is not repeated in CI.

## Alternatives

| Option | Not taken because |
|---|---|
| A Compose section of its own, such as `parameters.compose.<project>`, in Compose keys | One class could not feed Kubernetes and Compose, which is what EX-30 shows |
| Dropping keys without a counterpart with a warning | A setting the cluster gets, such as a security context, would be lost on the Docker host without the compile failing |
| An `http` probe as `curl` or `wget` | The generator cannot tell which client the image has; the target sets the Compose `healthcheck` (DKR-9) |
| Expanding `$(VAR)` at compile time | Would reimplement Kubernetes' expansion for two recipes that use it; DKR-4 refuses instead |
| `compose.yml` from a second compile entry with `output_type: yml` | Dockerfiles need `plain`, and `main` would need a switch per compile entry |
| `restart: unless-stopped` | Kubernetes' `Always` restarts regardless of how the container stopped, as Docker's `always` does; a target can set another (DKR-9) |
| A JSON Schema for the inventory input | The gate reads none: QA-7 validates output documents with `apiVersion` and `kind`, which a Compose file does not have, and `policy/manifest.schema.json` has no field for an input schema. It would be a second copy of DKR-3 that nothing runs |

## Open questions

- OQ-1: Should more keys map? `grace_period` (`stop_grace_period`),
  `working_dir`, `tty`, `stdin`, `pull_policy` and the security fields
  `allowPrivilegeEscalation` (`no-new-privileges`) and `capabilities`
  (`cap_drop`, `cap_add`) have Compose counterparts. They fail the compile
  today (DKR-3).

## Implementation inventory

| Item | Value |
|---|---|
| Compose rendering | `docker/compose.py` (`render`, DKR-2 to DKR-9), called from `main` in `docker/__init__.py` (DKR-1) |
| Fixture | `docker/tests/fixtures`, target `compose` (Miniflux and PostgreSQL), with the refs it reads in `refs/fixture/` |
| Golden | `docker/tests/golden/compose.yml` |
| Unit tests | `docker/tests/test_compose.py` with `conftest.py`, run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest --with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider docker/tests` (bytecode in the tree fails SEC-5) |
| CI | `.github/workflows/check.yml`, step for CHK-8 |
| Smoke run | 2026-11-05, Docker Engine 29.9.2, Compose 5.6.1: the compiled fixture target `compose`, revealed with `kapitan refs --reveal -f` into `docker compose up -d --wait`. Both services healthy after 22 s; Miniflux answers `/healthcheck` with `OK` and `/v1/version` with 2.3.4 for `admin` with the revealed password. `docker inspect` shows user `65534:65534`, a read-only root filesystem, restart policy `always`, `Memory` 268435456, `NanoCpus` 500000000, `MemoryReservation` 67108864 and no CPU reservation. The script is not part of this repository |
