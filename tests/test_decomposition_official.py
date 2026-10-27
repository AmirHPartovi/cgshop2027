#!/usr/bin/env python3
"""Verify a direct globally merged decomposition candidate with official pyutils."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECOMPOSITION_TEST = Path(sys.argv[1]).resolve()
sys.argv = sys.argv[:1]


class DecompositionOfficialTests(unittest.TestCase):
    def test_merged_candidate_passes_official_checker(self):
        with tempfile.TemporaryDirectory(prefix="cgshop-decomposition-official-") as directory:
            solution = Path(directory) / "merged.solution.json"
            generated = subprocess.run(
                [str(DECOMPOSITION_TEST), "--write-merged", str(solution)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertTrue(solution.is_file())
            checked = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/validate.py"),
                    str(ROOT / "tests/fixtures/instances/tiny-hole-multicutter.instance.json"),
                    str(solution),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main()
