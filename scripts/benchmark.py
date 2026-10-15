#!/usr/bin/env python3
"""Run selected algorithms concurrently under the shared runtime configuration."""

from __future__ import annotations

import argparse
import copy
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from runtime_config import ROOT, available_cpu_workers, load_runtime_config
from reference_comparison import compare_instance_results, comparison_tsv
from solution_metrics import makespan


def terminate_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def _parse_ps_time(value: str) -> float:
    value = value.strip()
    days = 0
    if "-" in value:
        day_text, value = value.split("-", 1)
        days = int(day_text)
    fields = value.split(":")
    if len(fields) == 3:
        hours, minutes, seconds = fields
    elif len(fields) == 2:
        hours = "0"
        minutes, seconds = fields
    else:
        return float(value)
    return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def process_tree_snapshot(root_pid: int) -> dict[str, Any]:
    if os.name != "posix":
        raise RuntimeError("process-tree monitoring requires POSIX ps")
    output = subprocess.check_output(
        ["ps", "-axo", "pid=,ppid=,rss=,time="],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    parent: dict[int, int] = {}
    rss: dict[int, int] = {}
    cpu: dict[int, float] = {}
    for line in output.splitlines():
        fields = line.split(None, 3)
        if len(fields) != 4:
            continue
        pid, ppid, memory = map(int, fields[:3])
        parent[pid] = ppid
        rss[pid] = memory
        cpu[pid] = _parse_ps_time(fields[3])
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid in parent.items():
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return {
        "rss_kib": sum(rss.get(pid, 0) for pid in descendants),
        "cpu_seconds": sum(cpu.get(pid, 0.0) for pid in descendants),
        "process_count": len(descendants),
    }


def process_tree_rss_kib(root_pid: int) -> int:
    """Compatibility wrapper for callers that only need aggregate tree RSS."""
    return int(process_tree_snapshot(root_pid)["rss_kib"])


def official_validator_available() -> bool:
    try:
        import cgshop2027_pyutils  # noqa: F401

        return True
    except ImportError:
        return False


def _ip_kont_metadata(solution: dict[str, Any], algorithm: str) -> dict[str, Any]:
    if algorithm != "ilp":
        return {"candidate_kind": "heuristic"}
    meta = solution.get("meta", {})
    if not isinstance(meta, dict):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "ip_kont_model", "ip_kont_status", "ip_kont_raw_status",
        "ip_kont_termination_reason", "ip_kont_solver_log",
        "ip_kont_runtime_seconds", "ip_kont_process_exit_code",
        "ip_kont_column_count", "ip_kont_variable_count",
        "ip_kont_binary_variable_count", "ip_kont_continuous_variable_count",
        "ip_kont_constraint_count", "ip_kont_assignment_constraint_count",
        "ip_kont_load_constraint_count", "ip_kont_surrogate_assignment_objective",
        "ip_kont_reconstructed_makespan",
        "ip_kont_exact_for_original_objective", "ilp_backend",
    ):
        if key not in meta:
            continue
        value = meta[key]
        if key.endswith("_count") or key.endswith("_seconds") or key.endswith("_code"):
            try:
                value = float(value) if key.endswith("_seconds") else int(value)
            except (TypeError, ValueError):
                pass
        elif key == "ip_kont_exact_for_original_objective":
            value = value is True or str(value).lower() == "true"
        result[key] = value
    backend = result.get("ilp_backend")
    result["candidate_kind"] = (
        "ip_kont_surrogate_incumbent" if backend == "KONT" else
        "heuristic_fallback_from_ip_kont_surrogate"
        if backend == "partition-fallback" else "unknown"
    )
    return result


def run_bounded_process(
    command: list[str], timeout: float, memory_limit_mib: int
) -> tuple[int | None, str, str, str | None]:
    return run_bounded_process_with_metrics(
        command, timeout, memory_limit_mib
    )[:4]


def run_bounded_process_with_metrics(
    command: list[str], timeout: float, memory_limit_mib: int
) -> tuple[int | None, str, str, str | None, dict[str, Any]]:
    with tempfile.TemporaryFile(mode="w+t") as stdout_file, tempfile.TemporaryFile(
        mode="w+t"
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            start_new_session=(os.name == "posix"),
        )
        limit_error = ""
        started = time.monotonic()
        termination_reason = "process_exited"
        peak_rss_kib: int | None = None
        peak_cpu_seconds: float | None = None
        rss_samples = 0
        cpu_samples = 0
        while process.poll() is None:
            if time.monotonic() - started >= timeout:
                limit_error = f"wall-clock limit exceeded ({timeout:g}s)"
                termination_reason = "wall_clock_timeout"
                break
            try:
                snapshot = process_tree_snapshot(process.pid)
            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
                limit_error = f"memory probe failed; run stopped: {error}"
                termination_reason = "resource_probe_error"
                break
            memory_kib = int(snapshot["rss_kib"])
            if memory_kib > 0:
                peak_rss_kib = max(peak_rss_kib or 0, memory_kib)
                rss_samples += 1
            cpu_value = snapshot.get("cpu_seconds")
            if isinstance(cpu_value, (int, float)):
                peak_cpu_seconds = max(peak_cpu_seconds or 0.0, float(cpu_value))
                cpu_samples += 1
            if memory_kib > memory_limit_mib * 1024:
                limit_error = f"process-tree RSS exceeded {memory_limit_mib} MiB"
                termination_reason = "process_tree_memory_limit"
                break
            time.sleep(0.05)
        if limit_error:
            terminate_tree(process)
        else:
            process.wait()
        elapsed = time.monotonic() - started
        stdout_file.seek(0)
        stderr_file.seek(0)
        metrics = {
            "wall_seconds": elapsed,
            "child_process_tree_cpu_seconds": peak_cpu_seconds,
            "peak_process_tree_rss_bytes": (
                peak_rss_kib * 1024 if peak_rss_kib is not None else None
            ),
            "process_tree_rss_sample_count": rss_samples,
            "process_tree_cpu_sample_count": cpu_samples,
            "termination_reason": termination_reason,
            "memory_enforcement": "sampled aggregate process-tree RSS watchdog",
            "cpu_measurement": "sampled cumulative process-tree CPU from ps",
        }
        if limit_error is None and process.returncode != 0:
            termination_reason = f"process_exit_{process.returncode}"
            metrics["termination_reason"] = termination_reason
        return (
            None if limit_error else process.returncode,
            stdout_file.read(),
            stderr_file.read(),
            limit_error or None,
            metrics,
        )


def collect_benchmark_future(
    future: Future[dict[str, Any]], algorithm: str, repetition: int
) -> dict[str, Any]:
    try:
        return future.result()
    except Exception as error:
        return {
            "algorithm": algorithm,
            "repetition": repetition,
            "status": "worker_error",
            "seconds": None,
            "error": f"{type(error).__name__}: {error}",
            "validation_level": None,
            "official_validated": False,
            "termination_reason": "benchmark_worker_exception",
        }


def run_one(
    solver: Path,
    instance: Path,
    algorithm: str,
    repetition: int,
    output: Path,
    requested: dict[str, Any],
    effective: dict[str, Any],
    global_deadline: float | None,
) -> dict[str, Any]:
    started = time.monotonic()
    seed = requested["random_seed"] + repetition
    sidecar = Path(str(output) + ".config.json")
    run_report_path = Path(str(output) + ".run-config.json")
    timeout = min(
        effective["per_instance_timeout_seconds"],
        effective["per_algorithm_timeout_seconds"],
    )
    deadline_reached = False
    if global_deadline is not None:
        remaining = global_deadline - time.monotonic()
        if remaining <= 0:
            timeout = 0.0
            deadline_reached = True
        else:
            timeout = min(timeout, remaining)
    run_requested = copy.deepcopy(requested)
    run_effective = copy.deepcopy(effective)
    run_repetitions = (
        requested["randomized_repetitions"]
        if algorithm in {"lns", "hybrid"} else 1
    )
    run_effective["algorithms"] = [algorithm]
    run_effective["randomized_repetitions"] = run_repetitions
    run_effective["random_seed"] = seed
    run_effective["output_directory"] = str(output.parent)
    run_effective["per_instance_timeout_seconds"] = min(
        run_effective["per_instance_timeout_seconds"], timeout
    )
    run_effective["per_algorithm_timeout_seconds"] = min(
        run_effective["per_algorithm_timeout_seconds"], timeout
    )
    finalization_reserve = min(5.0, max(0.25, timeout * 0.2))
    run_effective["cooperative_search_budget_cap_seconds"] = max(
        0.0, timeout - finalization_reserve
    )
    run_effective["finalization_reserve_seconds"] = finalization_reserve
    run_effective["effective_solver_timeout_seconds"] = min(
        run_effective["per_instance_timeout_seconds"],
        run_effective["per_algorithm_timeout_seconds"],
        timeout,
    )
    run_effective["effective_per_run_wall_clock_timeout_seconds"] = timeout
    run_effective["effective_solver_timeout_seconds"] = min(
        run_effective["effective_solver_timeout_seconds"],
        run_effective["global_run_deadline_seconds"]
        if run_effective["global_run_deadline_seconds"] is not None
        else float("inf"),
    )
    run_effective["official_validation"] = effective["official_validation"]
    run_report = {
        "requested": run_requested,
        "effective": run_effective,
        "automatic_adjustments": [
            *([] if run_effective["benchmark_jobs"] == run_requested["benchmark_jobs"]
              else [f"benchmark_jobs reduced to {run_effective['benchmark_jobs']}"]),
            *([] if run_repetitions == run_requested["randomized_repetitions"]
              else [f"randomized_repetitions set to 1 for deterministic {algorithm}"]),
            f"effective per-run wall-clock timeout is {timeout:g}s",
            f"cooperative search reserves {finalization_reserve:g}s for validation and output",
            f"seed for this repetition is {seed}",
        ],
        "repetition_index": repetition + 1,
        "memory_enforcement": (
            "per-process RLIMIT_AS plus sampled process-tree RSS watchdog"
            if sys.platform.startswith("linux")
            else "sampled process-tree RSS watchdog"
        ),
    }
    run_report_path.write_text(
        json.dumps(run_report, indent=2) + "\n", encoding="utf-8"
    )
    if deadline_reached:
        return {
            "algorithm": algorithm, "repetition": repetition,
            "status": "global_deadline", "seconds": 0.0,
            "error": "global run deadline reached",
            "config_report": str(run_report_path),
        }
    command = [
        str(solver), "-i", str(instance), "-o", str(output),
        "--algorithm", algorithm,
        "--instance-timeout", str(run_effective["per_instance_timeout_seconds"]),
        "--algorithm-timeout", str(run_effective["per_algorithm_timeout_seconds"]),
        "--kont-timeout", str(min(effective["ip_kont_timeout_seconds"], timeout)),
        "--memory-limit-mib", str(effective["memory_limit_mib"]),
        "--threads-per-solver", str(effective["threads_per_solver"]),
        "--benchmark-jobs", str(effective["benchmark_jobs"]),
        "--seed", str(seed),
        "--lns-iterations", str(effective["algorithm_parameters"]["lns_iterations"]),
        "--tsp-max-anchors", str(effective["algorithm_parameters"]["tsp_max_anchors"]),
        "--two-opt-passes", str(effective["algorithm_parameters"]["two_opt_passes"]),
        "--exact-policy", effective["exact_solving_policy"],
        "--exact-max-candidates", str(effective["exact_solver_max_candidates"]),
        "--portfolio", ",".join(effective["heuristic_portfolio"]),
        "--tier", "all",
        "--repetitions", str(run_repetitions),
        "--output-dir", str(output.parent),
        "--log-level", effective["logging_verbosity"],
    ]
    if effective["overwrite_existing"]:
        command.append("--overwrite")
    if effective["global_run_deadline_seconds"] is not None:
        command.extend([
            "--global-deadline",
            str(effective["global_run_deadline_seconds"]),
        ])
    returncode, stdout, stderr, limit_error, resource_metrics = run_bounded_process_with_metrics(
        command, timeout, effective["memory_limit_mib"]
    )
    if limit_error:
        status = "memory_limit" if "RSS exceeded" in limit_error else "time_limit"
        if "memory probe failed" in limit_error:
            status = "memory_probe_failed"
        return {
            "algorithm": algorithm, "repetition": repetition,
            "status": status, "seconds": time.monotonic() - started,
            "error": limit_error, "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }
    if returncode != 0:
        timed_out = "deadline" in stderr.lower() or "timed out" in stderr.lower()
        if timed_out:
            resource_metrics["termination_reason"] = "cooperative_timeout"
        return {
            "algorithm": algorithm, "repetition": repetition,
            "status": "time_limit" if timed_out else "failed",
            "seconds": time.monotonic() - started,
            "error": stderr.strip() or f"solver exited {returncode}",
            "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }
    try:
        solution = json.loads(output.read_text(encoding="utf-8"))
        score = makespan(solution)
        report = json.loads(sidecar.read_text(encoding="utf-8"))
        kont_fields = _ip_kont_metadata(solution, algorithm)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        return {
            "algorithm": algorithm, "repetition": repetition, "status": "invalid_output",
            "seconds": time.monotonic() - started, "error": str(error),
            "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }
    official_resource_metrics: dict[str, Any] = {}
    if effective["official_validation"]:
        validation_timeout = timeout - (time.monotonic() - started)
        if validation_timeout <= 0:
            return {
                "algorithm": algorithm, "repetition": repetition,
                "status": "official_time_limit",
                "seconds": time.monotonic() - started,
                "error": "per-instance deadline expired before official validation",
                "config_report": str(run_report_path),
                "validation_level": "internal_cpp", "official_validated": False,
                **kont_fields,
                **resource_metrics,
            }
        validator = ROOT / "scripts/validate.py"
        official_code, official_stdout, official_stderr, official_limit, validation_metrics = (
            run_bounded_process_with_metrics(
                [sys.executable, str(validator), str(instance), str(output)],
                validation_timeout, effective["memory_limit_mib"],
            )
        )
        official_resource_metrics = {
            f"official_{key}": value for key, value in validation_metrics.items()
        }
        if official_limit:
            return {
                "algorithm": algorithm, "repetition": repetition,
                "status": "official_time_limit" if "wall-clock" in official_limit
                else "official_resource_limit",
                "seconds": time.monotonic() - started, "error": official_limit,
                "config_report": str(run_report_path),
                "validation_level": "internal_cpp", "official_validated": False,
                **kont_fields,
                **resource_metrics,
                **official_resource_metrics,
            }
        if official_code != 0:
            return {
                "algorithm": algorithm, "repetition": repetition,
                "status": "official_invalid", "seconds": time.monotonic() - started,
                "error": (official_stderr + official_stdout).strip(),
                "config_report": str(run_report_path),
                "validation_level": "internal_cpp", "official_validated": False,
                **{
                    **kont_fields,
                    **({"ip_kont_status": "INVALID_OUTPUT"}
                       if algorithm == "ilp" else {}),
                },
                **resource_metrics,
                **official_resource_metrics,
            }
    return {
        "algorithm": algorithm, "repetition": repetition, "status": "ok",
        "seconds": time.monotonic() - started, "makespan": score,
        "validation_level": (
            "official" if effective["official_validation"] else "internal_cpp"
        ),
        "official_validated": bool(effective["official_validation"]),
        "effective_per_run_wall_clock_timeout_seconds": timeout,
        "effective_random_seed": seed,
        "solution": str(output),
        "config_report": str(run_report_path),
        "solver_config_report": str(sidecar),
        "effective_config": report.get("effective"),
        "stdout": stdout.strip(),
        "solver_execution_status": solution.get("meta", {}).get(
            "execution_status", "COMPLETED"
        ),
        "candidate_source": solution.get("meta", {}).get(
            "candidate_source", "requested_algorithm"
        ),
        **resource_metrics,
        **official_resource_metrics,
        **kont_fields,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/default.json")
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument("--instances", type=Path, default=ROOT / "data/test")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, help="compatibility alias setting both timeout limits")
    parser.add_argument("--algorithms", help="comma-separated algorithm override")
    parser.add_argument("--jobs", type=int, help="benchmark_jobs override")
    official_group = parser.add_mutually_exclusive_group()
    official_group.add_argument("--official", dest="official", action="store_true")
    official_group.add_argument("--no-official", dest="official", action="store_false")
    parser.set_defaults(official=None)
    overwrite_group = parser.add_mutually_exclusive_group()
    overwrite_group.add_argument("--overwrite", dest="overwrite", action="store_true")
    overwrite_group.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    parser.set_defaults(overwrite=None)
    args = parser.parse_args()

    overrides: dict[str, Any] = {}
    if args.timeout is not None:
        overrides["per_instance_timeout_seconds"] = args.timeout
        overrides["per_algorithm_timeout_seconds"] = args.timeout
    if args.algorithms is not None:
        overrides["algorithms"] = [item.strip() for item in args.algorithms.split(",")]
    if args.jobs is not None:
        overrides["benchmark_jobs"] = args.jobs
    if args.output is not None:
        overrides["output_directory"] = str(args.output)
    if args.official is not None:
        overrides["official_validation"] = args.official
    if args.overwrite is not None:
        overrides["overwrite_existing"] = args.overwrite
    try:
        requested, effective, adjustments = load_runtime_config(args.config, overrides)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    solver = args.solver.resolve()
    if not solver.is_file() or not os.access(solver, os.X_OK):
        parser.error(f"solver executable not found or not executable: {solver}")
    if not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    instances = sorted(args.instances.glob("*.instance.json"))
    if not instances:
        parser.error(f"no *.instance.json inputs found in {args.instances}")
    for path in instances:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"cannot read valid JSON instance {path}: {error}")
        if not isinstance(value, dict) or not isinstance(value.get("instance_uid"), str):
            parser.error(f"instance has no string instance_uid: {path}")
    if effective["official_validation"] and not official_validator_available():
        parser.error("official_validation requires cgshop2027_pyutils in this Python interpreter")

    output_dir = (args.output or Path(effective["output_directory"]))
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if output_dir.exists() and not effective["overwrite_existing"]:
        parser.error(f"output directory already exists: {output_dir} (set overwrite_existing)")
    if output_dir.exists() and not output_dir.is_dir():
        parser.error(f"output path is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    global_deadline = None
    if effective["global_run_deadline_seconds"] is not None:
        global_deadline = time.monotonic() + effective["global_run_deadline_seconds"]
    report = {
        "requested": requested,
        "effective": effective,
        "automatic_adjustments": adjustments,
        "available_cpu_workers": available_cpu_workers(),
        "intended_max_active_solver_workers":
            effective["benchmark_jobs"] * effective["threads_per_solver"],
        "memory_enforcement": "sampled process-tree RSS watchdog",
        "cpu_measurement": "sampled cumulative process-tree CPU from ps",
        "global_run_deadline_started_at": (
            time.time() if effective["global_run_deadline_seconds"] is not None else None
        ),
        "official_validation": (
            "enabled" if effective["official_validation"] else "disabled"
        ),
    }
    config_report_path = output_dir / "runtime-config.json"
    if config_report_path.exists() and not effective["overwrite_existing"]:
        parser.error(f"configuration report exists: {config_report_path}")
    config_report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    tasks: list[tuple[Path, str, int, Path]] = []
    for instance in instances:
        uid = instance.name.removesuffix(".instance.json")
        for algorithm in requested["algorithms"]:
            repetitions = (
                requested["randomized_repetitions"]
                if algorithm in {"lns", "hybrid"} else 1
            )
            for repetition in range(repetitions):
                suffix = f".rep-{repetition + 1}" if repetitions > 1 else ""
                tasks.append((
                    instance, algorithm, repetition,
                    output_dir / f"{uid}.{algorithm}{suffix}.solution.json",
                ))
    if not effective["overwrite_existing"]:
        existing = [path for _, _, _, path in tasks
                    if (path.exists() or Path(str(path) + ".config.json").exists() or
                        Path(str(path) + ".run-config.json").exists())]
        if existing:
            parser.error("candidate already exists (set overwrite_existing): " +
                         ", ".join(str(path) for path in existing[:5]))

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=effective["benchmark_jobs"]) as executor:
        futures = {
            executor.submit(
                run_one, solver, instance, algorithm, repetition, output,
                requested, effective, global_deadline,
            ): (instance, algorithm, repetition, output)
            for instance, algorithm, repetition, output in tasks
        }
        for future in as_completed(futures):
            instance, algorithm, repetition, _ = futures[future]
            result = collect_benchmark_future(future, algorithm, repetition)
            result["instance_uid"] = instance.name.removesuffix(".instance.json")
            if algorithm == "ilp" and not result.get("ip_kont_status"):
                if result["status"] in {"time_limit", "official_time_limit"}:
                    result["ip_kont_status"] = "TIME_LIMIT_NO_INCUMBENT"
                elif result["status"] == "invalid_output":
                    result["ip_kont_status"] = "INVALID_OUTPUT"
                else:
                    result["ip_kont_status"] = "ERROR"
                result["ip_kont_raw_status"] = None
                result["ip_kont_termination_reason"] = result.get(
                    "error", "KONT result metadata was not available"
                )
                result["ip_kont_exact_for_original_objective"] = False
                result["ip_kont_proof_completed"] = False
                result["candidate_kind"] = (
                    "heuristic_fallback_from_ip_kont_surrogate"
                    if result.get("status") == "ok" else None
                )
            if result.get("status") == "ok":
                result["ip_kont_elapsed_seconds"] = (
                    result["seconds"] if algorithm == "ilp" else None
                )
            results.append(result)
            print(
                f"{result['instance_uid']}\t{algorithm}\t{repetition + 1}\t"
                f"{result['status']}\t{result.get('makespan', '')}"
            )

    results.sort(key=lambda row: (row["instance_uid"], row["algorithm"], row["repetition"]))
    table = output_dir / "benchmark.tsv"
    fields = ("instance_uid", "algorithm", "repetition", "status", "makespan",
              "validation_level", "official_validated", "candidate_kind",
              "ilp_backend",
              "ip_kont_model", "ip_kont_status", "ip_kont_raw_status",
              "ip_kont_runtime_seconds", "ip_kont_process_exit_code",
              "ip_kont_elapsed_seconds",
              "ip_kont_termination_reason", "ip_kont_column_count",
              "ip_kont_variable_count", "ip_kont_constraint_count",
              "ip_kont_exact_for_original_objective",
              "seconds", "effective_per_run_wall_clock_timeout_seconds",
              "effective_random_seed", "wall_seconds",
              "child_process_tree_cpu_seconds", "peak_process_tree_rss_bytes",
              "process_tree_rss_sample_count", "process_tree_cpu_sample_count",
              "termination_reason", "memory_enforcement",
              "solver_execution_status", "candidate_source",
              "official_wall_seconds", "official_child_process_tree_cpu_seconds",
              "official_peak_process_tree_rss_bytes",
              "official_process_tree_rss_sample_count",
              "official_process_tree_cpu_sample_count",
              "official_termination_reason", "solution", "config_report",
              "solver_config_report", "error")
    table.write_text(
        "\t".join(fields) + "\n" +
        "\n".join(
            "\t".join(
                ("null" if row.get(field) is None else str(row.get(field, "")))
                .replace("\t", " ").replace("\n", " ")
                for field in fields
            )
            for row in results
        ) + "\n",
        encoding="utf-8",
    )
    comparisons = compare_instance_results(results)
    comparison_json = output_dir / "reference-comparison.json"
    comparison_json.write_text(
        json.dumps({
            "schema_version": 1,
            "semantics": {
                "makespan": "maximum closed-tour Manhattan length",
                "certified_optimum": (
                    "null unless a proof for the original objective is available"
                ),
                "ip_kont_lower_bound": (
                    "null: the current strip-assignment objective is not a "
                    "proven lower bound for closed-tour makespan"
                ),
            },
            "instances": comparisons,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    comparison_table = output_dir / "reference-comparison.tsv"
    comparison_table.write_text(comparison_tsv(comparisons), encoding="utf-8")
    successes = sum(row["status"] == "ok" for row in results)
    print(
        f"completed {successes}/{len(results)} runs with "
        f"{effective['benchmark_jobs']} benchmark_jobs x "
        f"{effective['threads_per_solver']} threads_per_solver"
    )
    print(f"run report: {config_report_path}")
    print(f"results table: {table}")
    print(f"reference comparison: {comparison_json} and {comparison_table}")
    return 0 if successes == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
