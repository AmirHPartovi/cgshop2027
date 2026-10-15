#!/usr/bin/env python3
"""Run a bounded, tier-selected portfolio and keep its best official candidate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from benchmark import (
    _ip_kont_metadata,
    official_validator_available,
    run_bounded_process_with_metrics,
)
from profile_instances import DEFAULT_THRESHOLDS
from runtime_config import ROOT, load_runtime_config
from reference_comparison import compare_instance_results
from solution_metrics import makespan
from solver_policy import (
    DEFAULT_POLICY,
    build_plan,
    select_candidate,
)


def _official_validate(
    instance: Path, solution: Path, timeout: float, memory_mib: int
) -> tuple[str, str, dict[str, Any]]:
    code, stdout, stderr, limit_error, metrics = run_bounded_process_with_metrics(
        [sys.executable, str(ROOT / "scripts/validate.py"),
         str(instance), str(solution)],
        timeout,
        memory_mib,
    )
    if limit_error:
        if "wall-clock" in limit_error:
            return "official_timeout", limit_error, metrics
        if "RSS exceeded" in limit_error:
            return "official_memory_limit", limit_error, metrics
        return "official_resource_error", limit_error, metrics
    if code != 0:
        return "official_invalid", (stderr + stdout).strip(), metrics
    return "ok", "official verifier accepted candidate", metrics


def _resource_fields(metrics: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    return {
        f"{prefix}wall_seconds": metrics.get("wall_seconds"),
        f"{prefix}child_process_tree_cpu_seconds": metrics.get(
            "child_process_tree_cpu_seconds"
        ),
        f"{prefix}peak_process_tree_rss_bytes": metrics.get(
            "peak_process_tree_rss_bytes"
        ),
        f"{prefix}process_tree_rss_sample_count": metrics.get(
            "process_tree_rss_sample_count", 0
        ),
        f"{prefix}process_tree_cpu_sample_count": metrics.get(
            "process_tree_cpu_sample_count", 0
        ),
        f"{prefix}termination_reason": metrics.get("termination_reason"),
    }


def _candidate_kind(algorithm: str, solution_path: Path) -> str:
    if algorithm != "ilp":
        return "heuristic"
    try:
        solution = json.loads(solution_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    backend = solution.get("meta", {}).get("ilp_backend")
    if backend == "KONT":
        return "ip_kont_surrogate_incumbent"
    if backend == "partition-fallback":
        return "heuristic_fallback_from_ip_kont_surrogate"
    return "unknown"


def run_candidate(
    solver: Path,
    instance: Path,
    algorithm: str,
    output: Path,
    timeout: float,
    memory_mib: int,
    seed: int,
    runtime: dict[str, Any],
    validation_timeout: float,
    global_deadline: float | None,
) -> dict[str, Any]:
    config = runtime["effective"]
    command = [
        str(solver), "-i", str(instance), "-o", str(output),
        "--algorithm", algorithm,
        "--instance-timeout", str(timeout),
        "--algorithm-timeout", str(timeout),
        "--kont-timeout", str(
            min(timeout, config["ip_kont_timeout_seconds"])
        ),
        "--memory-limit-mib", str(memory_mib),
        "--threads-per-solver", "1",
        "--benchmark-jobs", "1",
        "--seed", str(seed),
        "--lns-iterations", str(config["algorithm_parameters"]["lns_iterations"]),
        "--tsp-max-anchors", str(config["algorithm_parameters"]["tsp_max_anchors"]),
        "--two-opt-passes", str(config["algorithm_parameters"]["two_opt_passes"]),
        "--exact-policy", (
            config["exact_solving_policy"] if algorithm == "ilp" else "disabled"
        ),
        "--exact-max-candidates", str(
            config["exact_solver_max_candidates"] if algorithm == "ilp" else 0
        ),
        "--portfolio", ",".join(config["heuristic_portfolio"]),
        "--tier", "all",
        "--repetitions", "1",
        "--output-dir", str(output.parent),
        "--log-level", config["logging_verbosity"],
    ]
    if config["overwrite_existing"]:
        command.append("--overwrite")
    started = time.monotonic()
    return_code, stdout, stderr, limit_error, resource_metrics = run_bounded_process_with_metrics(
        command, timeout, memory_mib
    )
    elapsed = time.monotonic() - started
    result: dict[str, Any] = {
        "algorithm": algorithm,
        "status": "ok",
        "elapsed_seconds": elapsed,
        "solution": None,
        "makespan": None,
        "validation_level": None,
        "official_validated": False,
        "candidate_kind": None,
        "outcome": "",
    }
    result.update(_resource_fields(resource_metrics))
    if limit_error:
        result["status"] = (
            "memory_limit" if "RSS exceeded" in limit_error else
            "memory_probe_failed" if "memory probe failed" in limit_error else
            "timeout"
        )
        result["outcome"] = limit_error
        return result
    if return_code != 0:
        result["status"] = (
            "timeout"
            if "deadline" in stderr.lower() or "timed out" in stderr.lower()
            else "solver_failed"
        )
        result["outcome"] = stderr.strip() or f"solver exited {return_code}"
        return result
    try:
        solution = json.loads(output.read_text(encoding="utf-8"))
        score = makespan(solution)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        result["status"] = "invalid_output"
        result["outcome"] = str(error)
        return result
    result.update(_ip_kont_metadata(solution, algorithm))
    result["solver_execution_status"] = solution.get("meta", {}).get(
        "execution_status", "COMPLETED"
    )
    result["candidate_source"] = solution.get("meta", {}).get(
        "candidate_source", "requested_algorithm"
    )
    result["makespan"] = score
    result["candidate_kind"] = _candidate_kind(algorithm, output)
    result["validation_level"] = "internal_cpp"
    if global_deadline is not None:
        validation_timeout = min(
            validation_timeout, global_deadline - time.monotonic()
        )
    if validation_timeout <= 0:
        result["status"] = "global_deadline"
        result["outcome"] = "global deadline reached before official validation"
        return result
    validation_status, validation_message, validation_metrics = _official_validate(
        instance, output, validation_timeout, memory_mib
    )
    result.update(_resource_fields(validation_metrics, "official_"))
    if validation_status != "ok":
        result["status"] = validation_status
        result["outcome"] = validation_message
        return result
    result["official_validated"] = True
    result["validation_level"] = "official"
    result["solution"] = str(output)
    result["outcome"] = validation_message
    result["solver_stdout"] = stdout.strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument("--policy", choices=("auto", "heuristic", "exact"),
                              default="auto")
    policy_group.add_argument("--algorithm",
                              help="force one explicit algorithm; does not use auto")
    parser.add_argument("--include-ip-kont-surrogate", action="store_true",
                        help="explicitly add the bounded non-exact IP-KONT strip surrogate")
    parser.add_argument("--config", type=Path, default=ROOT / "config/default.json")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--policy-config", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument("--validation-timeout", type=float, default=30.0)
    parser.add_argument("--overwrite", action="store_true",
                        help="allow replacing existing solution/report files")
    args = parser.parse_args()

    instance = args.instance.resolve()
    output = args.output.resolve()
    selection_report_path = Path(str(output) + ".selection.json")
    try:
        runtime_requested, runtime_effective, adjustments = load_runtime_config(
            args.config
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    runtime = {
        "requested": runtime_requested,
        "effective": runtime_effective,
        "automatic_adjustments": adjustments,
    }
    if not instance.is_file():
        parser.error(f"instance file not found: {instance}")
    if not args.solver.is_file() or not os.access(args.solver, os.X_OK):
        parser.error(f"solver executable not found or not executable: {args.solver}")
    if args.validation_timeout <= 0:
        parser.error("--validation-timeout must be positive")
    if runtime_effective["per_instance_timeout_seconds"] <= 0:
        parser.error("auto solving requires per_instance_timeout_seconds > 0")
    if runtime_effective["per_algorithm_timeout_seconds"] <= 0:
        parser.error("auto solving requires per_algorithm_timeout_seconds > 0")
    overwrite_allowed = args.overwrite or runtime_effective["overwrite_existing"]
    if (output.exists() or selection_report_path.exists()) and not overwrite_allowed:
        parser.error(f"output or selection report exists; refusing overwrite: {output}")
    if output == instance or selection_report_path == instance:
        parser.error("output and selection report must not overwrite the input instance")
    if (output.exists() and not output.is_file()) or (
        selection_report_path.exists() and not selection_report_path.is_file()
    ):
        parser.error("solution output and selection report paths must be regular files")
    started = time.monotonic()
    global_deadline = (
        started + runtime_effective["global_run_deadline_seconds"]
        if runtime_effective["global_run_deadline_seconds"] is not None else None
    )
    try:
        plan = build_plan(
            instance,
            args.thresholds.resolve(),
            args.policy_config.resolve(),
            requested_policy=args.policy,
            forced_algorithm=args.algorithm,
            include_ip_kont_surrogate=args.include_ip_kont_surrogate,
            surrogate_allowed_by_runtime_config=(
                runtime_effective["exact_solving_policy"] == "ip_kont_surrogate"
            ),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    if not official_validator_available():
        parser.error("auto solving requires cgshop2027_pyutils for official candidate selection")

    output.parent.mkdir(parents=True, exist_ok=True)
    requested_timeout = plan["per_algorithm_timeout_seconds"]
    if args.algorithm:
        requested_timeout = min(
            runtime_effective["per_instance_timeout_seconds"],
            runtime_effective["per_algorithm_timeout_seconds"],
        )
    candidates: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cgshop-auto-solve-") as temp:
        scratch = Path(temp)
        for index, algorithm in enumerate(plan["algorithms_to_run"]):
            timeout = (
                plan["ip_kont_surrogate_budget_seconds"]
                if algorithm == "ilp" and plan["ip_kont_surrogate_scheduled"]
                else requested_timeout
            )
            timeout = min(timeout, runtime_effective["per_instance_timeout_seconds"])
            timeout = min(timeout, runtime_effective["per_algorithm_timeout_seconds"])
            if global_deadline is not None:
                timeout = min(timeout, global_deadline - time.monotonic())
            if timeout <= 0:
                candidates.append({
                    "algorithm": algorithm,
                    "status": "global_deadline",
                    "elapsed_seconds": 0.0,
                    "official_validated": False,
                    "validation_level": None,
                    "outcome": "global run deadline exhausted before candidate launch",
                })
                continue
            candidate_path = scratch / f"candidate-{index:03d}-{algorithm}.solution.json"
            result = run_candidate(
                args.solver.resolve(), instance, algorithm, candidate_path,
                timeout, runtime_effective["memory_limit_mib"],
                runtime_effective["random_seed"],
                runtime, args.validation_timeout, global_deadline,
            )
            candidates.append(result)
            print(
                f"{algorithm}\t{result['status']}\t"
                f"{result.get('makespan') if result.get('makespan') is not None else ''}"
            )

        selection = select_candidate(plan, candidates)
        instance_uid = json.loads(instance.read_text(encoding="utf-8"))["instance_uid"]
        comparison_rows = [
            {
                **row,
                "instance_uid": instance_uid,
                "repetition": 0,
                "seconds": row.get("elapsed_seconds"),
            }
            for row in candidates
        ]
        reference_comparison = compare_instance_results(comparison_rows)[0]
        if selection["status"] == "ok":
            shutil.copyfile(selection["selected_solution"], output)
            selection["selected_solution"] = str(output)
        report = {
            "schema_version": 1,
            "requested": {
                "execution_policy": args.policy if args.algorithm is None else "forced_algorithm",
                "algorithm": args.algorithm,
                "include_ip_kont_surrogate": args.include_ip_kont_surrogate,
                "instance": str(instance),
                "output": str(output),
            },
            "effective": {
                **plan,
                "candidate_timeout_seconds": requested_timeout,
                "memory_limit_mib": runtime_effective["memory_limit_mib"],
                "official_validation_required": True,
                "official_validation_tool": "cgshop2027_pyutils",
            },
            "runtime_configuration": runtime,
            "algorithms_actually_executed": [
                row["algorithm"] for row in candidates
                if row["status"] != "global_deadline" or
                row.get("elapsed_seconds", 0) > 0
            ],
            "algorithms_not_started_due_to_global_deadline": [
                row["algorithm"] for row in candidates
                if row["status"] == "global_deadline" and
                row.get("elapsed_seconds", 0) == 0
            ],
            "candidates": candidates,
            "selection": selection,
            "reference_comparison": reference_comparison,
            "elapsed_seconds": time.monotonic() - started,
        }
        selection_report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"selection report: {selection_report_path}")
    if selection["status"] != "ok":
        print("no officially validated candidate; no solution was written", file=sys.stderr)
        return 1
    print(
        f"selected {selection['selected_algorithm']} "
        f"makespan={selection['selected_makespan']} "
        f"official_validated={selection['official_validated']} "
        f"optimality_certified={selection['optimality_certified']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
