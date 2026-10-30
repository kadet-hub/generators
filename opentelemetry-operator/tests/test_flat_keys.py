"""Unit test of the opentelemetry-operator flat keys (README, Inventory Contract).

Run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest
--with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider
--import-mode=importlib opentelemetry-operator/tests` (bytecode in the tree fails SEC-5).
The directory name is no identifier and the gate rejects dynamic imports, so the test reads the
flat keys from the source; the fixture target `complete` renders them through the gate.
"""

import json
import re
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]


def test_instrumentation_flat_keys_are_the_spec_fields():
    source = (GEN / "__init__.py").read_text()
    fields = re.search(r'class Instrumentation\b.*?_flat_keys\(\s*"""(.*?)"""', source, re.S).group(1).split()
    schema = json.loads((GEN / "schemas" / "opentelemetry.io" / "instrumentation_v1alpha1.json").read_text())
    assert sorted(fields) == sorted(schema["properties"]["spec"]["properties"]), fields
