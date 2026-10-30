"""Tests for tools/workflow-policy (UPD-6, docs/specs/upstream.md); no network."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("workflow-policy")


def policy(step):
    """Runs the policy on one workflow whose only job, without an
    environment, has the given step."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "tools").mkdir()
        shutil.copy(SCRIPT, Path(tmp) / "tools")
        workflows = Path(tmp) / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "w.yml").write_text(
            "on: push\njobs:\n  j:\n    runs-on: ubuntu-24.04\n    steps:\n      - " + step + "\n"
        )
        env = dict(os.environ, GITHUB_REPOSITORY="o/r")
        return subprocess.run(
            [Path(tmp) / "tools" / "workflow-policy"], env=env, capture_output=True, text=True, check=False
        )


class SecretReads(unittest.TestCase):
    def assert_flags(self, step, why):
        proc = policy(step)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout, f"UPD-6: w.yml job j holds {why} without an environment\n")

    def assert_passes(self, step):
        proc = policy(step)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_named_secret(self):
        self.assert_flags("run: echo ${{ secrets.KEY }}", "secrets.KEY")

    def test_named_secret_in_upper_case(self):
        self.assert_flags("run: echo ${{ SECRETS.KEY }}", "secrets.KEY")

    def test_whole_context(self):
        self.assert_flags("run: echo '${{ toJSON(secrets) }}'", "secrets")

    def test_whole_context_in_a_format_string(self):
        self.assert_flags("run: echo \"${{ format('{0}', Secrets) }}\"", "secrets")

    def test_whole_context_without_spaces(self):
        self.assert_flags("run: echo '${{secrets}}'", "secrets")

    def test_github_token(self):
        self.assert_passes("run: echo ${{ secrets.GITHUB_TOKEN }} ${{ SECRETS.github_token }}")

    def test_word_outside_an_expression(self):
        self.assert_passes("run: echo no secrets here")

    def test_input_named_secrets(self):
        self.assert_passes("run: echo ${{ inputs.secrets }}")


if __name__ == "__main__":
    unittest.main()
