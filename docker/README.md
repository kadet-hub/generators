# Docker Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/docker/) page.

Kapitan kadet generator for Dockerfiles and, from the components of the kubernetes generator, a Docker Compose file ([Docker Compose](#docker-compose)). Each entry under `dockerfiles` renders one `Dockerfile`, single-stage or multi-stage. From a short image description it derives the package install command for the base image's distribution (`apk add --no-cache`, `apt-get` with [cache mounts](https://docs.docker.com/build/cache/optimize/#use-cache-mounts) for `/var/cache/apt` and `/var/lib/apt/lists`, so neither ends up in the image, `dnf` with `dnf clean all`, or `pip --no-cache-dir`), creates a non-root user with the matching userland (busybox `adduser` on Alpine, shadow `useradd` elsewhere) and writes the instructions in a fixed order that builds.

Built for BuildKit's Dockerfile frontend 1.20 or later, per the [Dockerfile reference at BuildKit v0.34.0](https://github.com/moby/buildkit/blob/v0.34.0/frontend/dockerfile/docs/reference.md): `RUN --mount` (also used for apt installs) and `COPY --chmod` need Dockerfile 1.2, `RUN --network` 1.3, `RUN --security` 1.20, and `RUN --security=insecure` also needs the `security.insecure` entitlement on the builder and the build. BuildKit is the default builder on Linux since [Docker Engine 23.0.0](https://docs.docker.com/engine/release-notes/23.0/#2300).

## Usage

```yaml
parameters:
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/docker@sha256:<digest>
        output_path: lib/docker
    compile:
      - output_path: docker/
        input_type: kadet
        output_type: plain
        input_paths:
          - lib/docker
  generators:
    docker:
      dockerfiles:
        orders-api:
          stages:
            - stage_name: builder
              base_image: python:3.14.8-slim-trixie
              workdir: /build
              packages: [build-essential]
              copy:
                - src: requirements.txt
                  dst: .
              run:
                - python -m venv /opt/venv
                - command: /opt/venv/bin/pip install -r requirements.txt
                  mount: type=cache,target=/root/.cache/pip
            - stage_name: runtime
              base_image: python:3.14.8-slim-trixie
              labels:
                org.opencontainers.image.source: https://git.example.com/shop/orders-api
              env:
                PATH: /opt/venv/bin:$PATH
              workdir: /app
              create_user: true
              user: app
              uid: 10001
              gid: 10001
              copy:
                - src: /opt/venv
                  dst: /opt/venv
                  from: builder
                - src: src/
                  dst: /app/
                  chown: "10001:10001"
              expose: [8000]
              cmd: ["python", "-m", "orders_api", "--port", "8000"]
```

`output_type: plain` is required: the generator returns the Dockerfile text.

## Inputs

All keys live under `parameters.generators.docker.dockerfiles.<name>`. A Dockerfile has either the stage keys below or `stages`, a list of stages with the same keys. Every stage needs `base_image`.

| Key | Instruction |
|---|---|
| `component` | Output directory instead of `<name>`; may contain `/`. Top level only. |
| `base_image`, `platform`, `stage_name` | `FROM [--platform=…] <image> [AS <stage>]` |
| `labels` | one `LABEL k="v"` per entry |
| `args` | one `ARG k[=v]` per entry; `null` declares without default |
| `env` | one `ENV k="v"` per entry |
| `workdir` | `WORKDIR` |
| `packages`, `package_manager` | one install `RUN`; `package_manager` is `auto` (default, from the image name: `alpine` is apk, `fedora`/`centos`/`rhel`/`rocky`/`alma` is dnf, everything else apt), `apk`, `apt`, `dnf` or `pip` |
| `create_user`, `user`, `uid`, `gid` | with `create_user: true`, a `RUN` that creates group and user (`uid`/`gid` default 1000); `user` alone only emits `USER` |
| `copy` | `COPY`; an item is a string (`"src dst"`) or a dict with `src`, `dst`, `from`, `chown`, `chmod` |
| `run` | `RUN`; an item is a string, a list (joined with `&&`) or a dict with `command`, `mount`, `network` (`default`, `none`, `host`), `security` (`sandbox`, `insecure`) |
| `volumes`, `expose` | one `VOLUME` / `EXPOSE` per item |
| `healthcheck` | `NONE`, or a dict with `cmd` (string or list), `interval`, `timeout`, `start_period`, `retries` |
| `entrypoint`, `cmd` | list for exec form, string for shell form |

Instructions are written in the order of the table, with `packages` before user creation and `USER`, so packages always install as root; the `RUN` steps after it run as `user`, and copied files stay owned by root unless `chown` is set. Without `user` the image's default user applies, which is root for most official images; set `user` for anything that does not need root at runtime. Values that would break a single-line instruction (newlines) are rejected, as are unknown `package_manager`, `network` and `security` values and out-of-range `uid`, `gid` and ports.

Build secrets do not belong in `args` or `env`, where they end up in the image history; use `run` with `mount: type=secret,id=<id>`.

## Docker Compose

`generators.docker.compose` turns on `compose.yml`, written next to the Dockerfiles by the same compile entry. It renders `parameters.components`, the block the [kubernetes generator](https://kadet-hub.org/generators/kubernetes/) reads, so one class feeds a cluster target and a Docker host target. Each component becomes the service of the same name, after the kubernetes generator's defaults (`applications.<app>.component_defaults`, `generators.manifest.default_config`, `generators.manifest.resource_defaults.<type>`). A component with `enabled: false` renders no service.

```yaml
parameters:
  components:                 # usually in a class the cluster target shares
    miniflux:
      image: miniflux/miniflux:2.3.4@sha256:<digest>
      ports:
        http:
          container_port: 8080
      env:
        ADMIN_PASSWORD:
          secretKeyRef:
            key: ADMIN_PASSWORD
      secrets:
        credentials:
          string_data:
            ADMIN_PASSWORD:
              value: ?{base64:miniflux/admin-password||random:str:24}
      healthcheck:
        readiness:
          type: command
          command: [/usr/bin/miniflux, -healthcheck, auto]
  generators:
    docker:
      compose:                # merged over what the components render
        services:
          miniflux:
            ports: [127.0.0.1:8080:8080]
```

| Component key | Compose |
|---|---|
| `image` | `image` |
| `command`; `args` as list or mapping | `entrypoint`; `command` |
| `env`: scalars, and `secretKeyRef` or `configMapKeyRef` with only `key` | `environment`, the value taken from the component's `secrets.<s>.string_data` or `config_maps.<c>.data` entry with `value` |
| `ports` | `expose`: the container port, with `/udp` or `/sctp` for those protocols |
| `volume_claims`; `volume_mounts` of a claim (`mount_path`, `volume`, `read_only`) | a named volume per claim; `<claim>:<mount_path>[:ro]` |
| `healthcheck.readiness` with `type: command` | `healthcheck`: `period_seconds`, `timeout_seconds`, `failure_threshold` and `initial_delay_seconds` as `interval`, `timeout`, `retries` and `start_period`, defaults 10, 5, 3 and 0 as the kubernetes generator renders them |
| `resources`: `cpu`, and `memory` in `Ki`, `Mi` or `Gi` | `deploy.resources`, `requests` as `reservations`; on one Docker host Compose applies no CPU reservation |
| `security_context`: `runAsUser`, `runAsGroup`, `readOnlyRootFilesystem`; `read_only_root_filesystem` | `user`; `read_only` |
| `type`: `deployment`, `statefulset` | `restart: always` |
| `application`, `enabled`, `service`, `enable_service_links: false` | nothing; services reach each other by service name on the container port |

Any other component key, and a value the table does not cover, fails the compile with `components.<name>: no Compose mapping for <key>`. That includes `security_profile`, `workload_security_context`, `replicas`, `init_containers`, `volumes`, labels and annotations, `liveness` and `startup` probes and readiness probes of type `http`, `tcp` or `grpc`: a Compose health check runs inside the container and needs a client the image has. Keep such keys in the cluster target, and put a Compose `healthcheck` under `generators.docker.compose.services.<name>`.

`generators.docker.compose` is merged over the rendered document: mappings key by key, other values replace, `null` removes. It holds what only a Docker host needs, such as published `ports`, `depends_on`, another `restart` or services that are no component, and is written as given, with Compose interpolation. Values taken from components have `$` written as `$$`, so the container gets them as Kubernetes passes them. `env`, `command` and `args` with `$(` or `$$` fail the compile, because Kubernetes expands those and Compose does not.

Compile without `--reveal` and reveal on the host, so no file holds the secrets:

```sh
kapitan compile -t <target>
kapitan refs --reveal -f compiled/<target>/docker/compose.yml | docker compose -p <project> -f - up -d
```

Kapitan writes revealed values into the text unescaped and unquoted, so a `$` in one is interpolated by Compose and a value starting with a YAML indicator such as `*` breaks the file. `random:str` refs contain letters and digits only.

## Output

| File | Content |
|---|---|
| `<output_path>/<name>/Dockerfile` | one Dockerfile per entry, or `<output_path>/<component>/Dockerfile` |
| `<output_path>/compose.yml` | the Compose file, with `generators.docker.compose` set |
