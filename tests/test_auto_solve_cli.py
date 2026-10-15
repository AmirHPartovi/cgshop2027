#!/usr/bin/env python3
"""Exercise explicit auto-runner selection and selection-report semantics."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLVER = Path(sys.argv[1]).resolve()
INSTANCE = ROOT / "tests/fixtures/instances/tiny-square.instance.json"
RUNNER_PYTHON = ROOT / ".venv/bin/python"
if not RUNNER_PYTHON.is_file():
    RUNNER_PYTHON = Path(sys.executable)
sys.argv = sys.argv[:1]


class AutoSolveCliTests(unittest.TestCase):
    def test_forced_algorithm_is_reported_and_officially_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "selected.solution.json"
            result = subprocess.run(
                [
                    str(RUNNER_PYTHON), str(ROOT / "scripts/auto_solve.py"),
                    "--instance", str(INSTANCE), "--output", str(output),
                    "--algorithm", "partition", "--solver", str(SOLVER),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(
                Path(str(output) + ".selection.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["requested"]["execution_policy"], "forced_algorithm")
            self.assertEqual(report["requested"]["algorithm"], "partition")
            self.assertEqual(report["algorithms_actually_executed"], ["partition"])
            self.assertEqual(report["selection"]["selected_algorithm"], "partition")
            self.assertTrue(report["selection"]["official_validated"])
            self.assertFalse(report["selection"]["optimality_certified"])
            comparison = report["reference_comparison"]
            self.assertEqual(comparison["best_validated_feasible_makespan"],
                             report["selection"]["selected_makespan"])
            self.assertIsNone(comparison["certified_optimum_makespan"])
            self.assertIsNone(comparison["ip_kont_lower_bound"])
            self.assertTrue(output.is_file())

    def test_exact_policy_fails_without_claiming_solver_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "no-exact.solution.json"
            result = subprocess.run(
                [
                    str(RUNNER_PYTHON), str(ROOT / "scripts/auto_solve.py"),
                    "--instance", str(INSTANCE), "--output", str(output),
                    "--policy", "exact", "--solver", str(SOLVER),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no mathematically exact solver", result.stderr)
            self.assertFalse(output.exists())

    def test_auto_runs_its_tier_portfolio_and_selects_official_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "auto.solution.json"
            result = subprocess.run(
                [
                    str(RUNNER_PYTHON), str(ROOT / "scripts/auto_solve.py"),
                    "--instance", str(INSTANCE), "--output", str(output),
                    "--solver", str(SOLVER),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(
                Path(str(output) + ".selection.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["requested"]["execution_policy"], "auto")
            self.assertEqual(report["effective"]["estimated_tier"], "LIGHT")
            self.assertEqual(
                report["algorithms_actually_executed"],
                ["partition", "boustrophedon", "tsp-cov"],
            )
            self.assertIn(
                report["selection"]["selected_algorithm"],
                report["algorithms_actually_executed"],
            )
            self.assertEqual(report["selection"]["selected_candidate_kind"], "heuristic")
            self.assertTrue(report["selection"]["official_validated"])


if __name__ == "__main__":
    unittest.main()
