# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Talos 1.14.2. Node outputs are multi-document configs: the `v1alpha1` document keeps only the fields Talos 1.14 has not deprecated, and the deprecated ones are written as their replacement kinds (`HostnameConfig`, `LinkConfig`, `UnattendedInstallConfig`, `KubeletConfig`, `KubeAPIServerConfig` and others; see the README for the mapping). The inventory keys stay the same. Blocks without a multi-document equivalent (install kernel arguments and extensions, kubelet `extraMounts`, control plane `extraVolumes`, `machine.disks`, interface `deviceSelector`, files outside `/etc/cri/conf.d/*.part`, `cluster.discovery` with the Kubernetes registry, API server authentication and authorization flags) stay in the `v1alpha1` document with a warning.
- Changed meaning: certificate and key values for the API server, aggregator and service account CAs and registry TLS are decoded from base64 to PEM; Kapitan refs for them must hold PEM. Interfaces in link documents stop Talos from running DHCP on unconfigured links. `persist` is ignored.
- The default installer image moves from `ghcr.io/siderolabs/installer:v1.13.0` to `factory.talos.dev/metal-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.2`, the one `talosctl gen config` 1.14.2 writes; `ghcr.io/siderolabs/installer` is no longer published from Talos 1.14.
- A `hostname` or `ip` shorthand that overrides a nested value logs `Flat key '<key>' overrides spec passthrough '<path>' for resource '<node>'`.
- Ships the Talos 1.14.2 schema split per multi-document kind (MPL-2.0, notice in `schemas/core/NOTICE`) and the Kubernetes 1.35.0 Secret schema; the kadet-hub gate validates the Talos documents and the userdata Secret against them (QA-7). The `v1alpha1` base document has no `apiVersion`/`kind` and is not schema-checked.
- `/etc/cri/conf.d/<name>.part` files become `CRICustomizationConfig` documents named `<name>`.
