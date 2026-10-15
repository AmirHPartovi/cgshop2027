#!/usr/bin/env python3
"""Run the configured algorithms on the paper's fixed local instance subset."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from benchmark import run_bounded_process_with_metrics, run_one
from runtime_config import ROOT, load_runtime_config
from visualize_solution import safe_filename_component


INSTANCES = (
    "fpg73_1k_1s2.instance.json",
    "fpg73_1k_3s2.instance.json",
    "srpg_246_821_1s3.instance.json",
)


def _metric(value: object) -> str:
    return "null" if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/default.json")
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument("--instances", type=Path, default=ROOT / "data/test")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--algorithms", help="comma-separated algorithm override")
    overwrite = parser.add_mutually_exclusive_group()
    overwrite.add_argument("--overwrite", dest="overwrite", action="store_true")
    overwrite.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    parser.set_defaults(overwrite=None)
    args = parser.parse_args()

    overrides = {}
    if args.timeout is not None:
        overrides["per_instance_timeout_seconds"] = args.timeout
        overrides["per_algorithm_timeout_seconds"] = args.timeout
    if args.algorithms is not None:
        overrides["algorithms"] = [item.strip() for item in args.algorithms.split(",")]
    if args.output is not None:
        overrides["output_directory"] = str(args.output)
    if args.overwrite is not None:
        overrides["overwrite_existing"] = args.overwrite
    try:
        requested, effective, adjustments = load_runtime_config(args.config, overrides)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if effective["benchmark_jobs"] != 1:
        parser.error("run_paper_algorithms is sequential; use benchmark.py for benchmark_jobs > 1")
    if effective["randomized_repetitions"] != 1:
        parser.error("run_paper_algorithms does not repeat runs; use benchmark.py")

    solver = args.solver.resolve()
    if not solver.is_file() or not os.access(solver, os.X_OK):
        parser.error(f"solver executable missing or not executable: {solver}")
    if not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    instance_paths = [args.instances / name for name in INSTANCES]
    missing = [str(path) for path in instance_paths if not path.is_file()]
    if missing:
        parser.error("required paper input instance(s) missing: " + ", ".join(missing))

    output = args.output or Path(effective["output_directory"]) / "paper-algorithms"
    if not output.is_absolute():
        output = ROOT / output
    if output.exists() and not effective["overwrite_existing"]:
        parser.error(f"output directory already exists: {output} (pass --overwrite)")
    output.mkdir(parents=True, exist_ok=True)

    if effective["official_validation"]:
        try:
            import cgshop2027_pyutils  # noqa: F401
        except ImportError as error:
            parser.error(f"official validation dependency unavailable: {error}")

    global_deadline = None
    if effective["global_run_deadline_seconds"] is not None:
        global_deadline = time.monotonic() + effective["global_run_deadline_seconds"]
    (output / "runtime-config.json").write_text(
        json.dumps({
            "requested": requested,
            "effective": effective,
            "automatic_adjustments": adjustments,
            "intended_max_active_solver_workers":
                effective["benchmark_jobs"] * effective["threads_per_solver"],
            "memory_enforcement": "sampled process-tree RSS watchdog",
            "cpu_measurement": "sampled cumulative process-tree CPU from ps",
            "official_validation": (
                "enabled" if effective["official_validation"] else "disabled"
            ),
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    visualize = ROOT / "scripts/visualize.py"
    rows = [
        "instance_uid\talgorithm\tvalid\tofficial\tmakespan\tsvg\tconfig_report\t"
        "solver_wall_seconds\tsolver_cpu_seconds\tsolver_peak_rss_bytes\t"
        "solver_termination_reason\t"
        "visualizer_wall_seconds\tvisualizer_cpu_seconds\tvisualizer_peak_rss_bytes\t"
        "error"
    ]
    failures = 0
    for instance_path in instance_paths:
        instance = json.loads(instance_path.read_text(encoding="utf-8"))
        uid = instance["instance_uid"]
        for algorithm in requested["algorithms"]:
            stem = (
                f"{safe_filename_component(uid)}."
                f"{safe_filename_component(algorithm)}.rep-0000."
                f"seed-{effective['random_seed']}"
            )
            solution_path = output / f"{stem}.solution.json"
            svg_path = output / f"{stem}.svg"
            result = run_one(
                solver, instance_path, algorithm, 0, solution_path,
                requested, effective, global_deadline,
            )
            error = result.get("error", "")
            valid = result["status"] == "ok"
            renderable = (
                result["status"] in {"ok", "official_invalid"}
                and solution_path.is_file()
            )
            if result["status"] == "official_invalid":
                official_value = "False"
            elif valid and effective["official_validation"]:
                official_value = "True"
            else:
                official_value = "not_checked"
            makespan = str(result.get("makespan", ""))
            visualizer_metrics = {
                "wall_seconds": None,
                "child_process_tree_cpu_seconds": None,
                "peak_process_tree_rss_bytes": None,
            }
            visualization_ok = False
            if renderable:
                try:
                    visualizer_timeout = effective["per_algorithm_timeout_seconds"]
                    if global_deadline is not None:
                        visualizer_timeout = min(
                            visualizer_timeout, global_deadline - time.monotonic()
                        )
                    if visualizer_timeout <= 0:
                        raise RuntimeError("global deadline reached before visualization")
                    code, stdout, stderr, limit_error, visualizer_metrics = (
                        run_bounded_process_with_metrics(
                            [sys.executable, str(visualize), str(instance_path),
                             str(solution_path), "-o", str(svg_path),
                             "--algorithm-id", algorithm,
                             "--status", (
                                 "OFFICIAL_INVALID"
                                 if result["status"] == "official_invalid"
                                 else (
                                     "OFFICIAL_VALID"
                                     if effective["official_validation"]
                                     else "VALID_FEASIBLE; OFFICIAL_CHECKER_DISABLED"
                                 )
                             ),
                             *(["--overwrite"] if effective["overwrite_existing"] else [])],
                            visualizer_timeout, effective["memory_limit_mib"],
                        )
                    )
                    if limit_error:
                        raise RuntimeError(limit_error)
                    if code != 0:
                        raise RuntimeError(stderr.strip() or f"visualizer exited {code}")
                    visualization_ok = True
                except (OSError, RuntimeError) as exception:
                    error = f"{error}; visualization: {exception}".strip("; ")
            if not valid:
                failures += 1
            rows.append(
                f"{uid}\t{algorithm}\t{valid}\t{official_value}\t{makespan}\t"
                f"{svg_path if visualization_ok else ''}\t{result.get('config_report', '')}\t"
                f"{_metric(result.get('wall_seconds'))}\t"
                f"{_metric(result.get('child_process_tree_cpu_seconds'))}\t"
                f"{_metric(result.get('peak_process_tree_rss_bytes'))}\t"
                f"{_metric(result.get('termination_reason'))}\t"
                f"{_metric(visualizer_metrics['wall_seconds'])}\t"
                f"{_metric(visualizer_metrics['child_process_tree_cpu_seconds'])}\t"
                f"{_metric(visualizer_metrics['peak_process_tree_rss_bytes'])}\t"
                f"{error.replace(chr(9), ' ').replace(chr(10), ' ')}"
            )
            print(f"{uid}\t{algorithm}\t{valid}\t{official_value}\t{makespan}")

    table = output / "summary.tsv"
    table.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {table}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
