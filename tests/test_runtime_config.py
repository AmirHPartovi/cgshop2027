#!/usr/bin/env python3
"""Regression tests for shared runtime configuration defaults and precedence."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_config import CANONICAL_SOLVER_MODES, load_runtime_config  # noqa: E402


class RuntimeConfigTests(unittest.TestCase):
    def test_defaults_are_loaded_from_central_file(self):
        requested, effective, adjustments = load_runtime_config()
        self.assertEqual(requested["per_algorithm_timeout_seconds"], 10.0)
        self.assertEqual(requested["solver_mode"], "heuristic")
        self.assertEqual(CANONICAL_SOLVER_MODES, ("heuristic", "ip-kont", "decompose"))
        self.assertEqual(requested["algorithm_parameters"]["lns_iterations"], 250)
        self.assertEqual(requested["algorithm_parameters"]["lns_max_anchors"], 5000)
        self.assertEqual(requested["algorithm_parameters"]["lns_max_move_anchors"], 16)
        self.assertEqual(effective, requested)
        self.assertEqual(adjustments, [])

    def test_command_line_overrides_configuration_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "user.json"
            path.write_text(json.dumps({
                "per_algorithm_timeout_seconds": 4,
                "random_seed": 18,
            }))
            requested, _, _ = load_runtime_config(
                path, {"per_algorithm_timeout_seconds": 2.5}
            )
            path.write_text(json.dumps({"solver_mode": "decompose"}))
            mode_requested, _, _ = load_runtime_config(path)
        self.assertEqual(requested["per_algorithm_timeout_seconds"], 2.5)
        self.assertEqual(mode_requested["solver_mode"], "decompose")
        self.assertEqual(requested["random_seed"], 18)
        self.assertEqual(requested["algorithm_parameters"]["tsp_max_anchors"], 3500)

    def test_unknown_key_and_unsupported_tier_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"unknown": 1}')
            with self.assertRaisesRegex(ValueError, "unknown configuration key"):
                load_runtime_config(path)
            with self.assertRaisesRegex(ValueError, "solver_mode must be one of"):
                load_runtime_config(overrides={"solver_mode": "ilp"})
            path.write_text('{"difficulty_tier_filter": ["easy"]}')
            with self.assertRaisesRegex(ValueError, "validated tier classifier"):
                load_runtime_config(path)
            path.write_text('{"heuristic_portfolio": ["ilp"]}')
            with self.assertRaisesRegex(ValueError, "unsupported or duplicate"):
                load_runtime_config(path)

    def test_threads_and_invalid_timeout_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"threads_per_solver": 2}')
            with self.assertRaisesRegex(ValueError, "single-threaded"):
                load_runtime_config(path)
            path.write_text('{"per_algorithm_timeout_seconds": -1}')
            with self.assertRaisesRegex(ValueError, "between 0 and 31536000"):
                load_runtime_config(path)
            path.write_text('{"per_algorithm_timeout_seconds": 31536001}')
            with self.assertRaisesRegex(ValueError, "between 0 and 31536000"):
                load_runtime_config(path)

    def test_only_implemented_algorithm_parameters_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({
                "algorithm_parameters": {"restart_count": 7}
            }))
            with self.assertRaisesRegex(ValueError, "unsupported algorithm parameter"):
                load_runtime_config(path)
            with self.assertRaisesRegex(ValueError, "must not exceed"):
                load_runtime_config(overrides={
                    "algorithm_parameters": {
                        "lns_max_anchors": 4,
                        "lns_max_move_anchors": 5,
                    }
                })
            with self.assertRaisesRegex(ValueError, "at most 100000"):
                load_runtime_config(overrides={
                    "algorithm_parameters": {"lns_iterations": 100001}
                })

    def test_concurrency_adjustment_and_randomized_repetitions(self):
        requested, effective, adjustments = load_runtime_config(
            overrides={"benchmark_jobs": 1000, "randomized_repetitions": 2}
        )
        self.assertEqual(requested["benchmark_jobs"], 1000)
        self.assertLessEqual(effective["benchmark_jobs"], 1000)
        self.assertEqual(effective["randomized_repetitions"], 2)
        self.assertTrue(adjustments)
        with self.assertRaisesRegex(ValueError, "at most 1000"):
            load_runtime_config(overrides={"randomized_repetitions": 1001})


if __name__ == "__main__":
    unittest.main()
