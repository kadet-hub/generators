# Changelog

## 1.0.1

Republished so the artefact carries the repository's LICENSE, which the kadet-hub registry adds to every artefact it builds since kadet-hub/registry#418. The artefact of 1.0.0 has no LICENSE although it declares Apache-2.0. Rendered output is unchanged.

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Removed the compile-time jsonschema validation and the `jsonschema` import; the gate checks the output against the shipped k3d v5.9.0 schema (QA-7), and krab can now compile the generator.
- Removed an unused `yaml` import.
