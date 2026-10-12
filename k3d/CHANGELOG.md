# Changelog

## 1.0.0

First release on kadet-hub, migrated from kapitan-generators.

- Removed the compile-time jsonschema validation and the `jsonschema` import; the gate checks the output against the shipped k3d v5.9.0 schema (QA-7), and krab can now compile the generator.
- Removed an unused `yaml` import.
