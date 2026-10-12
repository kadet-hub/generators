# Changelog

## 1.0.1

apt package lists use a cache mount instead of rm -rf; 1.0.0 was tagged but never listed.

- `apt-get` installs run with `--mount=type=cache,target=/var/cache/apt,sharing=locked` and `--mount=type=cache,target=/var/lib/apt/lists,sharing=locked` (pattern from https://docs.docker.com/build/cache/optimize/#use-cache-mounts) and no longer delete `/var/lib/apt/lists`. Builds with apt packages now need BuildKit.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Package installation now comes before user creation and `USER`. Before, a Dockerfile with `create_user` and `packages` ran `apk add` or `apt-get install` as the non-root user and failed to build.
- The unused `alpine:latest` fallback for `base_image` is removed; `base_image` stays required.
- No schemas ship: Dockerfiles have no `apiVersion`/`kind`, so the kadet-hub gate does not validate the output (QA-7). The hand-written inventory schema of kapitan-generators is not carried over.
