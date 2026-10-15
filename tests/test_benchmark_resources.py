#!/usr/bin/env python3
"""Controlled tests for bounded process execution and resource accounting."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark import (  # noqa: E402
    collect_benchmark_future,
    run_one,
    run_bounded_process_with_metrics,
)
from runtime_config import load_runtime_config  # noqa: E402


class BenchmarkResourceTests(unittest.TestCase):
    def test_timeout_terminates_the_process_group_and_reports_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "child-survived"
            script = root / "parent.py"
            script.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', "
                "'import pathlib,time; time.sleep(1); pathlib.Path(sys.argv[1]).write_text(\"alive\")', "
                "sys.argv[1]])\n"
                "print('started', flush=True)\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            code, stdout, _, limit_error, metrics = run_bounded_process_with_metrics(
                [sys.executable, str(script), str(marker)], 0.3, 1024
            )
            self.assertIsNone(code)
            self.assertIn("wall-clock limit", limit_error)
            self.assertIn("started", stdout)
            self.assertEqual(metrics["termination_reason"], "wall_clock_timeout")
            self.assertGreater(metrics["wall_seconds"], 0)
            self.assertGreater(metrics["process_tree_rss_sample_count"], 0)
            self.assertIsNotNone(metrics["peak_process_tree_rss_bytes"])
            self.assertGreater(metrics["peak_process_tree_rss_bytes"], 0)
            time.sleep(1.1)
            self.assertFalse(marker.exists(), "a child process survived timeout cleanup")

    def test_worker_exception_is_reported_as_failed_row(self):
        future = Future()
        future.set_exception(RuntimeError("worker broke"))
        result = collect_benchmark_future(future, "partition", 2)
        self.assertEqual(result["status"], "worker_error")
        self.assertEqual(result["termination_reason"], "benchmark_worker_exception")
        self.assertIn("worker broke", result["error"])
        self.assertFalse(result["official_validated"])

    def test_expired_global_deadline_overrides_per_algorithm_budget(self):
        requested, effective, _ = load_runtime_config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.json"
            result = run_one(
                ROOT / "build/bin/solver",
                ROOT / "tests/fixtures/instances/tiny-square.instance.json",
                "partition",
                0,
                output,
                requested,
                effective,
                time.monotonic() - 1,
            )
            self.assertEqual(result["status"], "global_deadline")
            self.assertEqual(result["seconds"], 0.0)
            config_report = Path(result["config_report"]).read_text(encoding="utf-8")
            self.assertIn('"effective_per_run_wall_clock_timeout_seconds": 0.0', config_report)
            self.assertFalse(output.exists())

    def test_cooperative_timeout_returns_and_labels_partition_fallback(self):
        fixture = json.loads(
            (ROOT / "tests/fixtures/instances/tiny-square.instance.json")
            .read_text(encoding="utf-8")
        )
        fixture["instance_uid"] = "deadline-fallback-test"
        fixture["region_to_cover"]["outer_boundary"] = {
            "x": [0, 100, 100, 0],
            "y": [0, 0, 100, 100],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instance = root / "large.instance.json"
            output = root / "candidate.solution.json"
            instance.write_text(json.dumps(fixture), encoding="utf-8")
            result = subprocess.run(
                [
                    str(ROOT / "build/bin/solver"),
                    "-i", str(instance), "-o", str(output),
                    "--algorithm", "anchor-cover",
                    "--instance-timeout", "0.5",
                    "--algorithm-timeout", "0.5",
                    "--memory-limit-mib", "1024",
                    "--overwrite",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            solution = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            solution["meta"]["execution_status"],
            "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE",
        )
        self.assertEqual(solution["meta"]["candidate_source"], "partition_fallback")


if __name__ == "__main__":
    unittest.main()
