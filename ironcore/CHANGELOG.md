# Changelog

## 1.0.3

Built for IronCore 0.9.0. The breaking changes of the release are in the IRI runtime API, etcd and the Kubernetes Go libraries. The generated OpenAPI v3 documents of the compute, networking and storage groups are the same as at v0.8.0, so the shipped schemas and rendered output are unchanged. The validation and defaulting files the README cites are unchanged at v0.9.0, and their links move to that tag.

## 1.0.2

Republished so the artefact carries the repository's LICENSE, which the kadet-hub registry adds to every artefact it builds since kadet-hub/registry#418. The artefacts of 1.0.1 and earlier have no LICENSE although they declare Apache-2.0. Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Ships the JSON Schemas of all eight kinds from the generated OpenAPI v3 documents of IronCore v0.8.0 (QA-7). IronCore has no CRDs, so the upstream schema tool cannot regenerate them.
- LoadBalancer `type`, VirtualIP and NATGateway `ipFamily` and LoadBalancer `ipFamilies` have no default any more; the schema check fails without them.
- `ipFamilies` of NetworkInterfaces and LoadBalancers is derived from `ips` when unset; an ephemeral IP without `ipFamily` fails the compile.
- A NetworkInterface without `ips` no longer gets `ipFamilies: [IPv4]` and `ips: []`, which the API server rejects.
- Machine `power` is no longer set to `On`; the API server defaults it.
- Removed `image_pull_secret_ref` (Volume), `target_ref` (VirtualIP) and `incoming_peerings` (Network): not a v0.8.0 field, a UID reference, and controller-written.
- Reference shorthands pass a dict through unchanged; peerings, LoadBalancer ports and Machine attachments keep keys the generator does not know.
- `providerID` is accepted in camelCase like the other flat keys.
- The flat-key collision warning reads "Flat key '<key>' overrides spec passthrough '<field>' for resource '<name>'".
