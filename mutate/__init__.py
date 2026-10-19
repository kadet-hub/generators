"""Patch the YAML files an earlier compile entry wrote, in place (docs/specs/mutate.md)."""

import json

from kapitan.inputs.kadet import BaseObj, inventory

from .mutations import MutationError, apply, check_entries, read_files


def main(input_params):
    params = dict(input_params)
    root = params.pop("compile_path")
    # Inventory Boxes to plain data, so merged values dump as YAML.
    mutations = json.loads(json.dumps(params.pop("mutations", None) or {}))
    if params:
        raise MutationError(f"mutate: unknown input_params {sorted(params)}")
    check_entries(inventory().parameters.kapitan.compile)
    out = BaseObj()
    for rel, text in apply(read_files(root), mutations).items():
        out.root[rel] = text
    return out
