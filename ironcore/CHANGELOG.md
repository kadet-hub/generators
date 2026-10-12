# Changelog

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
