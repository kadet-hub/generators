# Changelog

## 1.0.2

Ships the CRDs of the custom resources it renders under `schemas/<group>/crds/`, so the kadet-hub gate dry-runs them on a kube-apiserver (QA-11). Rendered output is unchanged.

## 1.0.1

Fails the compile when metadata.name is not a valid label value (over 63 characters), instead of rendering output the API server rejects.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Built for Cilium 1.20.2. Ships the CRD schemas of that release under `schemas/`; the kadet-hub gate validates the compiled output against them (QA-7). CiliumLoadBalancerIPPool now comes from the Cilium CRD instead of a CRDs catalog snapshot.
- New shorthands, documented with their sources in the README. Precedence, lowest first: generator defaults, `spec`, flat keys and shorthands; a flat key that overrides `spec` logs a warning.
  - Policy rule `ports: [8080, 53/UDP]` expands to a `toPorts` entry with string ports.
  - Policy `allow_dns: true` or `allow_dns: [<pattern>]` adds the kube-dns egress rule with an L7 DNS rule that `toFQDNs` needs.
  - Pool `blocks` accept `"<cidr>"` and `"<start>-<stop>"` strings.
- A CiliumL2AnnouncementPolicy that sets neither `externalIPs` nor `loadBalancerIPs` gets `loadBalancerIPs: true`. Before, such a policy announced nothing.
- Fixture targets set `parameters.kapitan.vars.target`, as the gate requires.
