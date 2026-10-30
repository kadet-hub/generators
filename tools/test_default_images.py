"""Tests for tools/default_images.py (docs/specs/images.md IMG-1)."""

import tempfile
import unittest
from pathlib import Path

import default_images

DIGEST = "@sha256:" + "a" * 64


class Images(unittest.TestCase):
    def test_literals_with_tag_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            gen = Path(d, "gen")
            (gen / "tests").mkdir(parents=True)
            (gen / "kapitan-generator.yaml").write_text("name: gen\n")
            (gen / "__init__.py").write_text(
                f'A = "registry.example.org/a:v1{DIGEST}"\n'
                f'B = ("example.org/b:v2"\n     "{DIGEST}")\n'  # implicit concatenation is one literal
                f'C = "kindest/node:v1.37.0{DIGEST}"\n'
                'D = "example.org/d:v3"\n'  # no digest
                f'E = "csi-provisioner:v6{DIGEST}"\n'  # no repository path
            )
            (gen / "tests" / "test_x.py").write_text(f'T = "example.org/t:v1{DIGEST}"\n')
            Path(d, "tools").mkdir()
            (Path(d, "tools") / "x.py").write_text(f'X = "example.org/x:v1{DIGEST}"\n')
            self.assertEqual(
                default_images.images(Path(d)),
                [("gen", f"example.org/b:v2{DIGEST}"), ("gen", f"kindest/node:v1.37.0{DIGEST}"), ("gen", f"registry.example.org/a:v1{DIGEST}")],
            )

    def test_mistyped_digest_fails(self):
        # an uppercase or non-hex digit would otherwise drop the image from the scan
        for digest in ("@sha256:" + "A" * 64, "@sha256:" + "a" * 63 + "l", "@sha256:" + "a" * 63):
            with self.subTest(digest=digest), tempfile.TemporaryDirectory() as d:
                gen = Path(d, "gen")
                gen.mkdir()
                (gen / "kapitan-generator.yaml").write_text("name: gen\n")
                (gen / "__init__.py").write_text(f'A = "registry.example.org/a:v1{digest}"\n')
                with self.assertRaisesRegex(ValueError, "__init__.py:1: digest"):
                    default_images.images(Path(d))


if __name__ == "__main__":
    unittest.main()
