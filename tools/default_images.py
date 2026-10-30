"""Print the default images of every generator as `<generator> <image>` (docs/specs/images.md IMG-1)."""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = re.compile(r"[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9._-]+)+:[\w.-]+@sha256:[0-9a-f]{64}")
BAD_DIGEST = re.compile(r"\S*@sha256:(?![0-9a-f]{64}$)\S*")


def images(root=ROOT):
    found = set()
    for manifest in sorted(root.glob("*/kapitan-generator.yaml")):
        gen = manifest.parent
        for path in sorted(gen.rglob("*.py")):
            if "tests" in path.relative_to(gen).parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(), str(path))):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                if IMAGE.fullmatch(node.value):
                    found.add((gen.name, node.value))
                elif BAD_DIGEST.fullmatch(node.value):
                    raise ValueError(f"{path}:{node.lineno}: digest is not 64 lowercase hex digits at the end: {node.value}")
    return sorted(found)


if __name__ == "__main__":
    for gen, image in images(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT):
        print(gen, image)
