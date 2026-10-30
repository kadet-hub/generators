# ocm Generator

Published on kadet-hub: pin a released version by digest from its [catalog](https://kadet-hub.org/generators/ocm/) page.

Kapitan kadet generator that writes an [Open Component Model](https://ocm.software) component constructor for a target. It collects every container image from the manifests earlier compile entries wrote and turns each into an `ociImage` resource, so the component that ships a target into another environment, an air-gapped one for example, lists exactly the images the target runs. A chart upgrade that adds an image changes the constructor in the same compile. Spec: [docs/specs/ocm.md](../docs/specs/ocm.md).

The output is the input of `ocm add component-version` of the new OCM CLI generation ([open-component-model/open-component-model](https://github.com/open-component-model/open-component-model)). Building, signing and transferring the component stay with the CLI.

## Usage

The `ocm` entry comes last and has `output_path: .`. Kapitan runs a target's entries in order and gives a kadet entry its output directory as `compile_path`, which is then the target's compile root; `images.scan` globs are relative to it. `output_type: plain` is required.

```yaml
# inventory/classes/ocm.yml
parameters:
  ocm:
    components:
      app:
        name: example.org/acme/app
        version: \${VERSION}
        provider:
          name: acme
        resources:
          manifests:
            type: ociArtifact
            version: \${VERSION}
            access:
              type: ociArtifact
              imageReference: \${REGISTRY}/acme/app-manifests:v\${VERSION}
        images:
          scan:
            - k8s/**/*.yml
            - k8s/**/*.yaml
          access: \${PROXY_%registry_id%}/%path%
          label: upstream
          require_digest: true
  kapitan:
    dependencies:
      - type: oci
        source: ghcr.io/kadet-hub/ocm@sha256:<digest>
        output_path: lib/ocm
    compile:
      # ... the entries that write k8s/ ...
      - input_type: kadet
        input_paths:
          - lib/ocm
        output_path: .
        output_type: plain
        input_params:
          file: ocm/component-constructor.yaml
          components: ${ocm:components}
```

The example is for reclass-rs, where `\${VERSION}` escapes the reference so the constructor keeps `${VERSION}` for the CLI to fill in (`ocm add cv ... VERSION=1.2.3`). Kapitan's OmegaConf backend resolves an escaped value twice, so there write `${escape:VERSION}`, `${escape:PROXY_%registry_id%}/%path%` and `${ocm.components}`. The template tokens use `%` because OmegaConf rejects `{` and `<` inside `${escape:...}`.

With these parameters, `ghcr.io/stefanprodan/podinfo:6.15.0@sha256:<d>` in a Deployment becomes:

```yaml
- name: podinfo
  type: ociImage
  version: 6.15.0
  labels:
  - name: upstream
    value: ghcr.io/stefanprodan/podinfo:6.15.0@sha256:<d>
  access:
    type: ociArtifact
    imageReference: ${PROXY_ghcr_io}/stefanprodan/podinfo:6.15.0@sha256:<d>
```

## Parameters

`input_params`:

| Key | Meaning |
|---|---|
| `components` | Map of id to component. The id orders components and names them in errors. Required. |
| `file` | Output path relative to the compile root, default `component-constructor.yaml`. |

A component needs `name`, `version` and `provider`. `labels`, `sources`, `componentReferences` and any other key are copied as written. Two keys are read by the generator:

| Key | Meaning |
|---|---|
| `resources` | Map of resource name to resource, copied as written with `name` set to the key, before the image resources. A map lets classes add resources per target. |
| `images.scan` | Glob patterns relative to the compile root. Every string value of an `image` key, at any depth, in the matched YAML files is an image. A pattern matching no file fails the compile. |
| `images.refs` | Extra image references, for images no manifest names. |
| `images.access` | Template for `imageReference`, default `%ref%` (the reference as written). Tokens: `%ref%`, `%registry%`, `%registry_id%` (registry with non-alphanumerics as `_`), `%path%` (after the registry, tag and digest included). Nothing else is replaced. A static mirror is `mirror.example.org/%registry%/%path%`. |
| `images.label` | Label name; each image resource gets it with the upstream reference as value. |
| `images.require_digest` | `true` fails the compile on an image without digest. |
| `images.names` | Map of repository (`ghcr.io/org/app`, `docker.io/library/redis`) to resource name, for two images whose derived names clash. |

An image resource is named after the last path segment of its repository and versioned by its tag; a reference without registry is a Docker Hub one (`redis:8` is `docker.io/library/redis:8`), a reference without tag and digest is `latest`.

## Failure modes

The compile fails, naming the cause, on: an unknown key in `input_params` or `images`; a component without `name`, `version` or `provider`; a scan pattern that matches no file or a file outside the compile root; a scanned file that is not YAML; an image with a digest but no tag; with `require_digest`, an image without digest; two resources with the same name; an `images.names` key that matches no image.

Without `output_type: plain` Kapitan dumps the returned text as a YAML string. Without `output_path: .` the scan globs cannot reach the other entries' output.

With `kapitan compile --cache`, the result is keyed on the inventory and input parameters, not on the files the generator reads: a changed image with no inventory change can reuse the old constructor.
