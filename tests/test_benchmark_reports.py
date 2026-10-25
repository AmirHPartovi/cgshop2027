#!/usr/bin/env python3
"""Tests reproducible quality/resource rankings from raw benchmark records."""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark as benchmark_module  # noqa: E402
from runtime_config import load_runtime_config  # noqa: E402
from summarize_benchmark import build_artifacts, generate_reports, read_trials  # noqa: E402


def record(run_id, uid, algorithm, status, trial_status, makespan=None, **extra):
    profile = {
        "estimated_tier": "LIGHT",
        "input_size_features": {"estimated_anchor_count": 16},
    }
    return {
        "run_id": run_id,
        "instance_uid": uid,
        "algorithm_id": algorithm,
        "status": status,
        "trial_status": trial_status,
        "solution_validity_status": "VALID" if status == "ok" else "INVALID",
        "validation_level": "internal_cpp" if status == "ok" else None,
        "official_validated": False,
        "makespan": makespan,
        "wall_seconds": extra.pop("wall_seconds", 2.0),
        "child_process_tree_cpu_seconds": 1.0,
        "peak_process_tree_rss_bytes": 1024,
        "timeout_status": trial_status.startswith("TIMEOUT"),
        "instance_profile": profile,
        "estimated_anchor_count": 16,
        "estimated_raster_point_tests": 256,
        "effective_configuration": {
            "per_instance_timeout_seconds": 10,
            "memory_limit_mib": 2048,
        },
        **extra,
    }


class BenchmarkReportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            record("r1", "case-a", "partition", "ok", "VALID_FEASIBLE", 10),
            record("r2", "case-a", "partition", "ok",
                   "TIMEOUT_WITH_VALID_INCUMBENT", 8,
                   timeout_status=True,
                   solver_execution_status="TIME_LIMIT_WITH_FEASIBLE_CANDIDATE"),
            record("r3", "case-a", "lns", "ok", "VALID_FEASIBLE", 12,
                   seed=2027),
            record("r4", "case-a", "invalid-method", "invalid_output",
                   "INVALID_SOLUTION", 1, wall_seconds=0.01),
            record("r5", "case-b", "partition", "time_limit",
                   "TIMEOUT_NO_SOLUTION", None, wall_seconds=10.0),
            record("r6", "case-b", "partition", "ok", "OPTIMAL_CERTIFIED", 9,
                   optimality_certified=True,
                   certified_optimum=9,
                   certified_optimum_source="validated exact comparator",
                   formulation_exact_for_original_objective=True,
                   certified_solution_validated=True,
                   certified_objective_matched=True),
            record("r7", "case-c", "lns", "ok", "VALID_FEASIBLE", 10,
                   validated_lower_bound=8,
                   validated_lower_bound_valid=True,
                   validated_lower_bound_source="independent valid relaxation"),
        ]

    def test_invalid_solutions_are_excluded_and_timeout_incumbents_remain_feasible(self):
        rows = [
            *self.rows,
            record("r8", "case-z", "lns", "failed", "ERROR", None),
        ]
        artifacts = build_artifacts(rows, Path("/raw/benchmark.tsv"))
        metadata = json.loads(artifacts["report-metadata.json"])
        partition = next(
            row for row in metadata["summary_statistics"]
            if row["algorithm_id"] == "partition"
        )
        self.assertEqual(partition["attempted_trials"], 4)
        self.assertEqual(partition["valid_feasible_solutions"], 3)
        self.assertAlmostEqual(partition["feasible_solution_rate"], 3 / 4)
        self.assertAlmostEqual(partition["timeout_rate"], 2 / 4)
        self.assertEqual(partition["median_makespan"], 9)
        self.assertEqual(partition["certified_optimal_solutions"], 1)
        self.assertEqual(partition["exact_agreement_instance_count"], 1)
        lns = next(
            row for row in metadata["summary_statistics"]
            if row["algorithm_id"] == "lns"
        )
        self.assertGreater(lns["geometric_mean_ratio_to_best_known_feasible"], 1)
        matrix = artifacts["comparison-matrix.tsv"].splitlines()
        header = matrix[0].split("\t")
        row_a = dict(zip(header, next(line.split("\t") for line in matrix[1:]
                                      if line.startswith("case-a\t"))))
        self.assertEqual(float(row_a["partition"]), 8)
        self.assertEqual(float(row_a["lns"]), 12)
        self.assertEqual(row_a["invalid-method"], "NO_VALID_SOLUTION:INVALID_SOLUTION")
        self.assertTrue(artifacts["quality-ranking.tsv"])
        self.assertTrue(artifacts["resource-ranking.tsv"])
        self.assertTrue(artifacts["memory-ranking.tsv"])
        self.assertTrue(artifacts["run-type-ranking.tsv"])
        self.assertTrue(artifacts["budget-comparison.tsv"])
        best_rows = artifacts["best-heuristic-per-instance.tsv"].splitlines()
        self.assertEqual(len(best_rows), 5)
        self.assertIn("BEST_KNOWN_FEASIBLE", best_rows[1])
        self.assertIn("NO_VALID_SOLUTION", best_rows[-1])
        tier_rows = artifacts["best-heuristic-by-tier.tsv"].splitlines()
        self.assertTrue(tier_rows[0].startswith("tier\trank\twinner"))
        self.assertIn("LIGHT\t1\ttrue", tier_rows[1])
        resource_rows = artifacts["resource-ranking.tsv"].splitlines()[1:]
        self.assertEqual(resource_rows[-1].split("\t")[1], "invalid-method")
        quality_rows = artifacts["quality-ranking.tsv"].splitlines()[1:]
        self.assertEqual(quality_rows[-1].split("\t")[1], "invalid-method")
        tier_summary = metadata["tier_summaries"]["LIGHT"]["partition"]
        self.assertEqual(tier_summary["attempted_trials"], 4)
        self.assertEqual(tier_summary["quality_ratio_trial_denominator"], 2)

    def test_optimality_plot_requires_valid_reference_metadata(self):
        artifacts = build_artifacts(self.rows, Path("/raw/benchmark.tsv"))
        self.assertIn("optimality-gaps.svg", artifacts)
        xml = ET.fromstring(artifacts["optimality-gaps.svg"])
        self.assertTrue(xml.tag.endswith("svg"))
        invalid_claim = record(
            "bad-proof", "case-z", "partition", "ok", "VALID_FEASIBLE", 9,
            optimality_certified=True,
            certified_optimum=6,
            certified_optimum_source="untrusted",
            formulation_exact_for_original_objective=False,
        )
        no_proof_artifacts = build_artifacts(
            [invalid_claim], Path("/raw/benchmark.tsv")
        )
        self.assertNotIn("optimality-gaps.svg", no_proof_artifacts)

    def test_reports_regenerate_from_raw_tsv_and_refuse_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "benchmark.tsv"
            fields = list(dict.fromkeys(field for row in self.rows for field in row))
            with raw.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
                writer.writeheader()
                writer.writerows(self.rows)
            self.assertEqual(len(read_trials(raw)), len(self.rows))
            generated = generate_reports(raw, root)
            self.assertTrue(generated)
            self.assertTrue((root / "benchmark.csv").is_file())
            self.assertTrue((root / "benchmark.jsonl").is_file())
            self.assertTrue((root / "instances/case-a.md").is_file())
            self.assertTrue((root / "algorithms/partition.md").is_file())
            for tier in ("light", "medium", "heavy", "unknown"):
                self.assertTrue((root / f"tiers/{tier}.md").is_file())
            with self.assertRaises(FileExistsError):
                generate_reports(raw, root)
            regenerated = generate_reports(raw, root, overwrite=True)
            self.assertEqual(len(regenerated), len(generated))
            with (root / "benchmark.csv").open(newline="", encoding="utf-8") as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertEqual(len(csv_rows), len(self.rows))
            self.assertEqual(csv_rows[1]["solution_validity_status"], "VALID")
            csv_source = root / "benchmark.csv"
            original_digest = hashlib.sha256(csv_source.read_bytes()).hexdigest()
            generate_reports(csv_source, root, overwrite=True)
            self.assertEqual(
                hashlib.sha256(csv_source.read_bytes()).hexdigest(),
                original_digest,
            )
            replay = root / "replayed"
            replay.mkdir()
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/summarize_benchmark.py"),
                    "--input", str(raw), "--output-dir", str(replay),
                ],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((replay / "benchmark-summary.md").is_file())

    def test_reports_include_light_medium_and_heavy_tier_results(self):
        tiered_rows = [
            record("light", "light-case", "partition", "ok", "VALID_FEASIBLE", 4),
            record("medium", "medium-case", "partition", "ok", "VALID_FEASIBLE", 8),
            record("heavy", "heavy-case", "partition", "ok", "VALID_FEASIBLE", 16),
        ]
        for row, tier in zip(tiered_rows, ("LIGHT", "MEDIUM", "HEAVY")):
            row["instance_profile"]["estimated_tier"] = tier
        artifacts = build_artifacts(tiered_rows, Path("/raw/benchmark.tsv"))
        for tier in ("light", "medium", "heavy"):
            self.assertIn(f"# {tier.title()} tier", artifacts[f"tiers/{tier}.md"])
        tier_ranking = artifacts["best-heuristic-by-tier.tsv"]
        for tier in ("LIGHT", "MEDIUM", "HEAVY"):
            self.assertIn(f"{tier}\t1\ttrue", tier_ranking)

    def test_quality_ratios_skip_zero_reference_and_missing_metrics(self):
        artifacts = build_artifacts([
            record("zero", "stationary", "partition", "ok", "VALID_FEASIBLE", 0,
                   wall_seconds=None, peak_process_tree_rss_bytes=None),
        ], Path("/raw/benchmark.tsv"))
        metadata = json.loads(artifacts["report-metadata.json"])
        summary = metadata["summary_statistics"][0]
        self.assertIsNone(summary["geometric_mean_ratio_to_best_known_feasible"])
        self.assertEqual(summary["measurement_denominators"]["wall_seconds"], 0)
        self.assertEqual(summary["measurement_denominators"]["peak_memory_bytes"], 0)

    def test_official_validator_timeout_preserves_internal_valid_incumbent(self):
        solver = ROOT / "build/bin/solver"
        requested, effective, _ = load_runtime_config(overrides={
            "algorithms": ["partition"],
            "official_validation": True,
        })
        real_runner = benchmark_module.run_bounded_process_with_metrics
        official_timeout_metrics = {
            "wall_seconds": 0.1,
            "child_process_tree_cpu_seconds": None,
            "peak_process_tree_rss_bytes": None,
            "process_tree_rss_sample_count": 0,
            "process_tree_cpu_sample_count": 0,
            "termination_reason": "wall_clock_timeout",
        }

        def run_solver_then_timeout_validator(command, timeout, memory):
            if Path(command[0]) == solver:
                return real_runner(command, timeout, memory)
            return None, "", "", "wall-clock limit reached", official_timeout_metrics

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "incumbent.solution.json"
            with patch.object(
                benchmark_module,
                "run_bounded_process_with_metrics",
                side_effect=run_solver_then_timeout_validator,
            ):
                result = benchmark_module.run_one(
                    solver,
                    ROOT / "tests/fixtures/instances/tiny-square.instance.json",
                    "partition",
                    0,
                    output,
                    requested,
                    effective,
                    None,
                )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["feasible"])
        self.assertEqual(result["solution_validity_status"], "VALID")
        self.assertEqual(result["validation_level"], "internal_cpp")
        self.assertEqual(result["official_validation_outcome"], "TIMEOUT")
        self.assertEqual(result["trial_status"], "TIMEOUT_WITH_VALID_INCUMBENT")
        self.assertTrue(result["timeout_status"])
        self.assertGreater(result["makespan"], 0)
        result["instance_uid"] = "tiny-square"
        summary = build_artifacts(
            [result], Path("/raw/benchmark.tsv")
        )
        algorithm_summary = json.loads(summary["report-metadata.json"])[
            "summary_statistics"
        ][0]
        self.assertEqual(algorithm_summary["valid_feasible_solutions"], 1)
        self.assertEqual(algorithm_summary["timeout_rate"], 1)
        self.assertEqual(algorithm_summary["official_validation_failure_count"], 1)
        self.assertEqual(algorithm_summary["officially_validated_solutions"], 0)

    def test_interrupted_trial_recovers_only_cpp_validated_incumbent(self):
        solver = ROOT / "build/bin/solver"
        requested, effective, _ = load_runtime_config(overrides={
            "algorithms": ["partition"],
            "official_validation": False,
        })
        real_runner = benchmark_module.run_bounded_process_with_metrics
        timeout_metrics = {
            "wall_seconds": 0.1,
            "child_process_tree_cpu_seconds": 0.1,
            "peak_process_tree_rss_bytes": 1024,
            "process_tree_rss_sample_count": 1,
            "process_tree_cpu_sample_count": 1,
            "termination_reason": "wall_clock_timeout",
        }

        def write_candidate_then_timeout(command, timeout, memory):
            if Path(command[0]) == solver:
                result = real_runner(command, timeout, memory)
                self.assertIsNone(result[3])
                return None, result[1], "wall-clock limit reached", \
                    "wall-clock limit exceeded", timeout_metrics
            return real_runner(command, timeout, memory)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "incumbent.solution.json"
            with patch.object(
                benchmark_module,
                "run_bounded_process_with_metrics",
                side_effect=write_candidate_then_timeout,
            ):
                result = benchmark_module.run_one(
                    solver,
                    ROOT / "tests/fixtures/instances/tiny-square.instance.json",
                    "partition",
                    0,
                    output,
                    requested,
                    effective,
                    None,
                )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trial_status"], "TIMEOUT_WITH_VALID_INCUMBENT")
        self.assertEqual(result["validation_level"], "internal_cpp")
        self.assertTrue(result["timeout_incumbent_validated"])
        self.assertTrue(result["feasible"])


if __name__ == "__main__":
    unittest.main()
