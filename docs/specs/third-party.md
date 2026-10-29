# Third-party licences and notices

Status: Draft
Code: `*/schemas/sources.yaml`, `*/schemas/<group>/NOTICE`, `*/schemas/<group>/LICENSE`
Verified against: main @ 1ea7e4e

## Problem and decision

The JSON Schemas, CRDs and Terraform provider schema extracts under
`<generator>/schemas/` are copies or derivatives of upstream files, and
they ship: the registry packs the generator directory into the artefact
consumers pull. The registry gate checks the generator's own licence
(QA-2) but not the licence of schema files (QA-12), so nothing here kept
the upstream licences and notices with the copies.

On main @ 1ea7e4e, 70 of the 74 `sources.yaml` entries named a `license`.
The four Terraform provider entries did not, although all four providers
are MPL-2.0 at the pinned tags. Five upstream repositories carry a NOTICE
at the pinned ref. rabbitmq already carried the substance of its NOTICE.
prometheus-operator, kyverno, multus and crossplane did not.

A notice lives next to the files it covers, in the group directory, as
rabbitmq, talos and k3d already do. A NOTICE in the generator root would
cover groups under other licences. The notice text names no upstream
version, so a schema update does not leave it stale. The version is in
the group's `sources.yaml` entry.

## Licence field

- TP-1: Every `sources.yaml` entry MUST name `license`, the SPDX
  identifier of the upstream licence at the pinned ref.

  For a GitHub source, the upstream licence is what
  `gh api repos/<owner>/<repo>/license?ref=<ref>` reports. Where that is
  `NOASSERTION`, the licence text decides (`yannh/kubernetes-json-schema`
  is Apache-2.0). For a Terraform Registry source, the provider's
  repository at the version's tag decides.

  - Test: manual: compare each entry with the API at its ref
  - Since: this change

## Notices

- TP-2: A schema group MUST carry the upstream notice in its directory
  when its upstream is MPL-2.0 or MIT, or holds a NOTICE file at the
  pinned ref.

  MPL-2.0 groups get a `NOTICE` that starts with the Exhibit A notice and
  names the upstream source and the modification. MIT groups carry the
  upstream `LICENSE` (k3d). An upstream NOTICE is carried with its
  attribution lines. Lines that list upstream's own dependencies, which
  the schemas do not contain, are left out (kyverno). crossplane carries
  provider-upjet-aws's CC0 note, although it attributes the provider's
  Terraform components rather than the CRDs.

  - Test: manual: for each entry, `gh api
    repos/<owner>/<repo>/contents/?ref=<ref>` lists no NOTICE, or the
    group directory has one
  - Since: this change

## Open questions

None.

## Implementation inventory

| Item | Value |
|---|---|
| MPL-2.0 groups | `rabbitmq/schemas/rabbitmq.com`, `talos/schemas/core` (`*_v1alpha1.json`), `terraform-{aws,azurerm,google,opentelekomcloud}/schemas/terraform` |
| MIT groups | `k3d/schemas/k3d.io` |
| Upstream NOTICE carried | `prometheus-operator/schemas/monitoring.coreos.com`, `kyverno/schemas/kyverno.io`, `kyverno/schemas/policies.kyverno.io`, `multus/schemas/k8s.cni.cncf.io`, `crossplane/schemas/aws.m.upbound.io`, `rabbitmq/schemas/rabbitmq.com` |
