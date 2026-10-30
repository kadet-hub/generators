"""OCM component constructor from the images of a target's compiled manifests (docs/specs/ocm.md)."""

__version__ = "0.1.0"

from kapitan.inputs.kadet import BaseObj

from .constructor import build


def main(input_params):
    params = dict(input_params)
    root = params.pop("compile_path")
    out = BaseObj()
    for rel, text in build(params, root).items():
        out.root[rel] = text
    return out
