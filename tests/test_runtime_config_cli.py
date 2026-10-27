#!/usr/bin/env python3
"""Exercise C++ config-file/CLI precedence and fail-fast validation."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOLVER = Path(sys.argv[1]).resolve()
INSTANCE = Path(sys.argv[2]).resolve()
sys.argv = sys.argv[:1]


class RuntimeConfigCliTests(unittest.TestCase):
    def test_public_modes_and_legacy_alias_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            heuristic = work / "heuristic.json"
            result = subprocess.run(
                [
                    str(SOLVER), "-i", str(INSTANCE), "-o", str(heuristic),
                    "--mode", "heuristic", "--algorithm", "partition",
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads(
                Path(str(heuristic) + ".result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["solver_completion_status"], "feasible_not_proven")
            self.assertEqual(contract["solver_mode"], "heuristic")
            self.assertTrue(contract["candidate_exists"])
            self.assertEqual(contract["internal_validation_status"], "passed")
            self.assertEqual(contract["algorithm_implementation"], "partition")
            self.assertEqual(contract["candidate_source"], "partition")
            self.assertFalse(contract["optimality_proved"])

            exact_output = work / "ip-kont.json"
            unavailable = subprocess.run(
                [str(SOLVER), "-i", str(INSTANCE), "-o", str(exact_output),
                 "--mode", "ip-kont"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(unavailable.returncode, 0)
            exact_contract = json.loads(
                Path(str(exact_output) + ".result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(exact_contract["solver_completion_status"], "unavailable")
            self.assertEqual(exact_contract["solver_mode"], "ip-kont")
            self.assertFalse(exact_contract["candidate_exists"])
            self.assertFalse(exact_contract["optimality_proved"])
            self.assertFalse(exact_output.exists())

            decomposition_output = work / "decompose.json"
            decomposition = subprocess.run(
                [str(SOLVER), "-i", str(INSTANCE), "-o", str(decomposition_output),
                 "--mode", "decompose", "--instance-timeout", "10",
                 "--algorithm-timeout", "10"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(decomposition.returncode, 0, decomposition.stderr)
            decomposition_contract = json.loads(
                Path(str(decomposition_output) + ".result.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(
                decomposition_contract["solver_completion_status"],
                "feasible_not_proven",
            )
            self.assertEqual(decomposition_contract["solver_mode"], "decompose")
            self.assertTrue(decomposition_contract["candidate_exists"])
            self.assertIn(
                decomposition_contract["algorithm_implementation"],
                {"decompose_heuristic", "partition"},
            )
            self.assertIn(
                decomposition_contract["candidate_source"],
                {"decomposition_heuristic_merge", "partition_fallback"},
            )
            self.assertFalse(decomposition_contract["optimality_proved"])

            unsupported = subprocess.run(
                [str(SOLVER), "-i", str(INSTANCE), "-o", str(work / "bad-mode.json"),
                 "--mode", "ilp"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("unsupported solver mode", unsupported.stderr)
            exact_with_legacy = subprocess.run(
                [str(SOLVER), "-i", str(INSTANCE),
                 "-o", str(work / "exact-with-heuristic.json"),
                 "--mode", "ip-kont", "--algorithm", "partition"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(exact_with_legacy.returncode, 0)
            self.assertIn("legacy heuristic override", exact_with_legacy.stderr)
            self.assertFalse((work / "exact-with-heuristic.json").exists())

            legacy_alias = work / "legacy-alias.json"
            accepted_alias = subprocess.run(
                [str(SOLVER), "-i", str(INSTANCE), "-o", str(legacy_alias),
                 "--algorithm", "e"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(accepted_alias.returncode, 0, accepted_alias.stderr)
            alias_contract = json.loads(
                Path(str(legacy_alias) + ".result.json").read_text(encoding="utf-8")
            )
            alias_solution = json.loads(legacy_alias.read_text(encoding="utf-8"))
            self.assertEqual(alias_solution["meta"]["requested_algorithm"], "hybrid")
            self.assertNotEqual(alias_contract["algorithm_implementation"], "e")
            self.assertNotEqual(alias_contract["candidate_source"], "e")

    def test_precedence_and_invalid_inputs(self):
        solver = SOLVER
        instance = INSTANCE
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            config = work / "user.json"
            config.write_text(json.dumps({
                "per_algorithm_timeout_seconds": 8.0,
                "random_seed": 17,
                "algorithm_parameters": {
                    "lns_iterations": 4,
                    "lns_max_anchors": 700,
                    "lns_max_move_anchors": 9,
                },
            }))
            output = work / "candidate.solution.json"
            completed = subprocess.run(
                [
                    str(solver), "-i", str(instance), "-o", str(output),
                    "--config", str(config), "--algorithm", "partition",
                    "--timeout", "2", "--seed", "99",
                    "--lns-max-anchors", "450",
                    "--lns-max-move-anchors", "7",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                self.fail(completed.stderr)
            report = json.loads(Path(str(output) + ".config.json").read_text())
            self.assertEqual(report["requested"]["algorithms"], ["partition"])
            self.assertEqual(report["requested"]["random_seed"], 99)
            self.assertEqual(report["requested"]["per_algorithm_timeout_seconds"], 2)
            self.assertEqual(report["requested"]["algorithm_parameters"]["lns_iterations"], 4)
            self.assertEqual(report["requested"]["algorithm_parameters"]["lns_max_anchors"], 450)
            self.assertEqual(report["requested"]["algorithm_parameters"]["lns_max_move_anchors"], 7)
            self.assertEqual(report["effective"]["effective_solver_timeout_seconds"], 2)

            bad = work / "unknown.json"
            bad.write_text('{"not_a_setting": 1}')
            invalid = subprocess.run(
                [str(solver), "-i", str(instance), "-o", str(work / "bad.json"),
                 "--config", str(bad)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("unknown configuration key", invalid.stderr)

            invalid_threads = subprocess.run(
                [str(solver), "-i", str(instance), "-o", str(work / "threads.json"),
                 "--threads-per-solver", "2"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid_threads.returncode, 0)
            self.assertIn("threads_per_solver must be 1", invalid_threads.stderr)

            excessive_timeout = subprocess.run(
                [str(solver), "-i", str(instance), "-o", str(work / "timeout.json"),
                 "--algorithm-timeout", "31536001"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(excessive_timeout.returncode, 0)
            self.assertIn("between 0 and 31536000", excessive_timeout.stderr)

            excessive_repetitions = subprocess.run(
                [str(solver), "-i", str(instance), "-o", str(work / "repetitions.json"),
                 "--algorithm", "lns", "--repetitions", "1001"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(excessive_repetitions.returncode, 0)
            self.assertIn("randomized_repetitions must be between 1 and 1000",
                          excessive_repetitions.stderr)

            invalid_lns_limits = subprocess.run(
                [str(solver), "-i", str(instance), "-o", str(work / "lns-limits.json"),
                 "--lns-max-anchors", "4", "--lns-max-move-anchors", "5"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid_lns_limits.returncode, 0)
            self.assertIn("lns_max_move_anchors <= lns_max_anchors",
                          invalid_lns_limits.stderr)

            unknown_option = subprocess.run(
                [str(solver), "--not-a-real-option"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(unknown_option.returncode, 0)
            self.assertIn("unknown option", unknown_option.stderr)


if __name__ == "__main__":
    unittest.main()
