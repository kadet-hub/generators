# Docker Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/docker/) page.

Kapitan kadet generator for Dockerfiles. Each entry under `dockerfiles` renders one `Dockerfile`, single-stage or multi-stage. From a short image description it derives the package install command for the base image's distribution (`apk add --no-cache`, `apt-get` with [cache mounts](https://docs.docker.com/build/cache/optimize/#use-cache-mounts) for `/var/cache/apt` and `/var/lib/apt/lists`, so neither ends up in the image, `dnf` with `dnf clean all`, or `pip --no-cache-dir`), creates a non-root user with the matching userland (busybox `adduser` on Alpine, shadow `useradd` elsewhere) and writes the instructions in a fixed order that builds.

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

## Output

| File | Content |
|---|---|
| `<output_path>/<name>/Dockerfile` | one Dockerfile per entry, or `<output_path>/<component>/Dockerfile` |
