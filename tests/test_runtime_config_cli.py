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
