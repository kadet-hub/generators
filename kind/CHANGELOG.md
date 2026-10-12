# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for kind v0.33.0.
- New `kubernetes_version` key on clusters and nodes: resolves to the digest-pinned `kindest/node` image from the kind v0.33.0 release notes.
- New cluster `spec` passthrough for kind fields without a flat key (`kubeadmConfigPatches`, `networking.dnsSearch`). Flat keys override it and log a warning.
- `networking.dns_domain` removed: kind v0.33.0 has no `dnsDomain` field and rejects the file. The key is now dropped with a warning.
- The JSON Schema check at compile time is removed. Its schema was hand-written and kind publishes none, so no schema ships and the kadet-hub gate does not validate the output (QA-7).
