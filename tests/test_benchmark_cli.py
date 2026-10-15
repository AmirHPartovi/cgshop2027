#!/usr/bin/env python3
"""Integration tests for isolated benchmark selection and persisted trial rows."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark import trial_status  # noqa: E402
from runtime_config import CANONICAL_ALGORITHMS, canonical_algorithm_id  # noqa: E402


class BenchmarkCliTests(unittest.TestCase):
    def test_canonical_registry_aliases_and_trial_statuses(self):
        self.assertEqual(canonical_algorithm_id("c2"), "connected-growth")
        self.assertEqual(canonical_algorithm_id("a1"), "boustrophedon")
        self.assertEqual(len(CANONICAL_ALGORITHMS), len(set(CANONICAL_ALGORITHMS)))
        self.assertEqual(trial_status({"status": "time_limit"}), "TIMEOUT_NO_SOLUTION")
        self.assertEqual(
            trial_status({
                "status": "ok",
                "solver_execution_status": "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE",
            }),
            "TIMEOUT_WITH_VALID_INCUMBENT",
        )
        self.assertEqual(
            trial_status({
                "status": "ok",
                "optimality_certified": False,
                "ip_kont_status": "OPTIMAL_CERTIFIED",
                "ip_kont_exact_for_original_objective": False,
            }),
            "VALID_FEASIBLE",
        )
        self.assertEqual(
            trial_status({"status": "skipped_by_policy"}), "SKIPPED_BY_POLICY"
        )

    def test_single_instance_trial_persists_identity_logs_and_refuses_reuse(self):
        solver = Path(sys.argv[1]).resolve()
        instance = ROOT / "tests/fixtures/instances/tiny-square.instance.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "results"
            command = [
                sys.executable, str(ROOT / "scripts/benchmark.py"),
                "--solver", str(solver), "--instance", str(instance),
                "--algorithm", "partition", "--no-official", "--timeout", "10",
                "--output", str(output_dir),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (output_dir / "benchmark.tsv").open(
                newline="", encoding="utf-8"
            ) as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["algorithm_id"], "partition")
            self.assertEqual(row["requested_algorithm"], "partition")
            self.assertEqual(row["trial_status"], "VALID_FEASIBLE")
            self.assertEqual(row["solution_validity_status"], "VALID")
            self.assertEqual(row["official_validation_outcome"], "NOT_REQUESTED")
            self.assertTrue(row["run_id"])
            self.assertTrue(row["input_fingerprint_sha256"])
            self.assertTrue(row["source_version_fingerprint"])
            self.assertTrue(row["algorithm_version_fingerprint"])
            self.assertTrue(row["effective_configuration"])
            self.assertTrue(Path(row["output_solution_path"]).is_file())
            self.assertTrue((output_dir / "runtime-config.json").is_file())
            self.assertTrue((output_dir / "benchmark.csv").is_file())
            self.assertTrue((output_dir / "benchmark.jsonl").is_file())
            self.assertTrue((output_dir / "benchmark-summary.md").is_file())
            self.assertTrue((output_dir / "quality-ranking.tsv").is_file())
            self.assertTrue((output_dir / "memory-ranking.tsv").is_file())
            self.assertTrue((output_dir / "quality-vs-runtime.svg").is_file())
            self.assertTrue((output_dir / "quality-vs-memory.svg").is_file())
            self.assertTrue((Path(row["log_path"]) / "stdout.log").is_file())
            run_id = row["run_id"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            with (output_dir / "benchmark.tsv").open(
                newline="", encoding="utf-8"
            ) as stream:
                self.assertEqual(next(csv.DictReader(stream, delimiter="\t"))["run_id"], run_id)

    def test_empty_input_directory_is_a_nonzero_preflight_failure(self):
        solver = Path(sys.argv[1]).resolve()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            empty_instances = root / "empty"
            empty_instances.mkdir()
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/benchmark.py"),
                    "--solver", str(solver), "--instances", str(empty_instances),
                    "--output", str(root / "output"),
                ],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no *.instance.json inputs found", result.stderr)
            self.assertFalse((root / "output" / "runtime-config.json").exists())

    def test_selected_ids_aliases_and_randomized_repetitions_are_isolated(self):
        solver = Path(sys.argv[1]).resolve()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "selected"
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/benchmark.py"),
                    "--solver", str(solver),
                    "--instances", str(ROOT / "tests/fixtures/instances"),
                    "--instance-ids", "tiny-square",
                    "--algorithms", "partition,d1", "--repetitions", "2",
                    "--no-official", "--timeout", "10",
                    "--output", str(output_dir),
                ],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with (output_dir / "benchmark.tsv").open(
                newline="", encoding="utf-8"
            ) as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 3)
            partition = [row for row in rows if row["algorithm_id"] == "partition"]
            lns = [row for row in rows if row["algorithm_id"] == "lns"]
            self.assertEqual(len(partition), 1)
            self.assertEqual(len(lns), 2)
            self.assertTrue(all(row["requested_algorithm"] == "d1" for row in lns))
            self.assertEqual({row["seed"] for row in lns}, {"2027", "2028"})
            self.assertEqual(
                len({row["effective_config_fingerprint"] for row in lns}), 2
            )
            self.assertEqual(len({row["run_id"] for row in rows}), 3)
            self.assertTrue(all(row["trial_status"] == "VALID_FEASIBLE" for row in rows))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("expected path to built solver")
    unittest.main(argv=[sys.argv[0]])
