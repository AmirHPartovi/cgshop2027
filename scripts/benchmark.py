#!/usr/bin/env python3
"""Run selected algorithms concurrently under the shared runtime configuration."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from runtime_config import (
    CANONICAL_ALGORITHMS,
    RANDOMIZED_ALGORITHMS,
    ROOT,
    available_cpu_workers,
    canonical_algorithm_id,
    load_runtime_config,
)
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    sources = sorted(
        path for path in (ROOT / "src").rglob("*")
        if path.is_file() and path.suffix in {".cpp", ".h"}
    )
    for directory in (ROOT / "scripts", ROOT / "config"):
        sources.extend(
            path for path in directory.rglob("*")
            if path.is_file() and path.suffix in {".py", ".json"}
        )
    sources.extend(path for path in (
        ROOT / "CMakeLists.txt",
        ROOT / "tests/internal_solution_check.cpp",
    ) if path.is_file())
    for path in sorted(set(sources)):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def output_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return component or "instance"


def trial_status(row: dict[str, Any]) -> str:
    if row.get("status") == "skipped_by_policy":
        return "SKIPPED_BY_POLICY"
    if row.get("status") in {"time_limit", "global_deadline"}:
        return "TIMEOUT_NO_SOLUTION"
    if row.get("status") == "official_time_limit":
        return "TIMEOUT_NO_SOLUTION"
    if row.get("status") in {"invalid_output", "official_invalid"}:
        return "INVALID_SOLUTION"
    if row.get("status") != "ok":
        return "ERROR"
    if row.get("solver_execution_status") in {
        "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE", "TIME_LIMIT_WITH_INCUMBENT"
    }:
        return "TIMEOUT_WITH_VALID_INCUMBENT"
    if row.get("official_validation_outcome") == "TIMEOUT":
        return "TIMEOUT_WITH_VALID_INCUMBENT"
    if row.get("optimality_certified"):
        return "OPTIMAL_CERTIFIED"
    if row.get("ip_kont_status") == "TIME_LIMIT_WITH_INCUMBENT":
        return "TIMEOUT_WITH_VALID_INCUMBENT"
    if row.get("ip_kont_status") == "FEASIBLE_NOT_PROVEN":
        return "FEASIBLE_NOT_PROVEN"
    return "VALID_FEASIBLE"


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
    def finish(
        row: dict[str, Any],
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
    ) -> dict[str, Any]:
        row["raw_exit_code"] = exit_code
        row["stdout"] = stdout
        row["stderr"] = stderr
        row["requested_algorithm"] = algorithm
        row["algorithm_id"] = canonical_algorithm_id(algorithm)
        row["seed"] = seed
        row["requested_configuration"] = run_requested
        row["effective_configuration"] = run_effective
        row["solution"] = (
            str(output)
            if row.get("status") == "ok" and row.get("makespan") is not None
            else None
        )
        row["timeout_status"] = (
            row.get("status") in {"time_limit", "official_time_limit", "global_deadline"}
            or row.get("official_validation_outcome") == "TIMEOUT"
            or row.get("solver_execution_status") in {
                "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE", "TIME_LIMIT_WITH_INCUMBENT"
            }
            or row.get("ip_kont_status") == "TIME_LIMIT_WITH_INCUMBENT"
            or row.get("termination_reason") in {
                "wall_clock_timeout", "cooperative_timeout", "global_deadline"
            }
        )
        row.setdefault("official_validation_outcome", (
            "NOT_REQUESTED" if not effective["official_validation"] else "NOT_RUN"
        ))
        row["feasible"] = bool(
            row.get("status") == "ok" and row.get("makespan") is not None
        )
        row["solution_validity_status"] = (
            "VALID" if row["feasible"] else
            "INVALID" if row.get("status") in {"invalid_output", "official_invalid"}
            else "NO_SOLUTION"
        )
        row["optimality_certified"] = bool(
            row.get("ip_kont_status") == "OPTIMAL_CERTIFIED"
            and row.get("ip_kont_exact_for_original_objective") is True
        )
        row["certified_optimum"] = None
        row["validated_lower_bound"] = None
        row["relative_gap"] = None
        row["trial_status"] = trial_status(row)
        return row
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
    run_repetitions = 1
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
        return finish({
            "algorithm": algorithm, "repetition": repetition,
            "status": "global_deadline", "seconds": 0.0,
            "error": "global run deadline reached",
            "config_report": str(run_report_path),
            "termination_reason": "global_deadline",
        })
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
        return finish({
            "algorithm": algorithm, "repetition": repetition,
            "status": status, "seconds": time.monotonic() - started,
            "error": limit_error, "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }, stdout, stderr, returncode)
    if returncode != 0:
        timed_out = "deadline" in stderr.lower() or "timed out" in stderr.lower()
        if timed_out:
            resource_metrics["termination_reason"] = "cooperative_timeout"
        return finish({
            "algorithm": algorithm, "repetition": repetition,
            "status": "time_limit" if timed_out else "failed",
            "seconds": time.monotonic() - started,
            "error": stderr.strip() or f"solver exited {returncode}",
            "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }, stdout, stderr, returncode)
    try:
        solution = json.loads(output.read_text(encoding="utf-8"))
        score = makespan(solution)
        report = json.loads(sidecar.read_text(encoding="utf-8"))
        kont_fields = _ip_kont_metadata(solution, algorithm)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        return finish({
            "algorithm": algorithm, "repetition": repetition, "status": "invalid_output",
            "seconds": time.monotonic() - started, "error": str(error),
            "config_report": str(run_report_path),
            "validation_level": None, "official_validated": False,
            **resource_metrics,
        }, stdout, stderr, returncode)
    official_resource_metrics: dict[str, Any] = {}
    if effective["official_validation"]:
        validation_timeout = timeout - (time.monotonic() - started)
        if validation_timeout <= 0:
            return finish({
                "algorithm": algorithm, "repetition": repetition,
                "status": "ok", "makespan": score,
                "seconds": time.monotonic() - started,
                "error": "per-instance deadline expired before official validation",
                "config_report": str(run_report_path),
                "solution": str(output),
                "validation_level": "internal_cpp", "official_validated": False,
                "official_validation_outcome": "TIMEOUT",
                **kont_fields,
                **resource_metrics,
            }, stdout, stderr, returncode)
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
            return finish({
                "algorithm": algorithm, "repetition": repetition,
                "status": "ok", "makespan": score,
                "seconds": time.monotonic() - started, "error": official_limit,
                "config_report": str(run_report_path),
                "solution": str(output),
                "validation_level": "internal_cpp", "official_validated": False,
                "official_validation_outcome": "TIMEOUT" if "wall-clock" in official_limit else "ERROR",
                **kont_fields,
                **resource_metrics,
                **official_resource_metrics,
            }, stdout, stderr, returncode)
        if official_code != 0:
            return finish({
                "algorithm": algorithm, "repetition": repetition,
                "status": "official_invalid", "seconds": time.monotonic() - started,
                "error": (official_stderr + official_stdout).strip(),
                "config_report": str(run_report_path),
                "validation_level": "internal_cpp", "official_validated": False,
                "official_validation_outcome": "INVALID",
                **{
                    **kont_fields,
                    **({"ip_kont_status": "INVALID_OUTPUT"}
                       if algorithm == "ilp" else {}),
                },
                **resource_metrics,
                **official_resource_metrics,
            }, stdout, stderr, returncode)
    return finish({
        "algorithm": algorithm, "repetition": repetition, "status": "ok",
        "seconds": time.monotonic() - started, "makespan": score,
        "validation_level": (
            "official" if effective["official_validation"] else "internal_cpp"
        ),
        "official_validated": bool(effective["official_validation"]),
        "official_validation_outcome": (
            "VALID" if effective["official_validation"] else "NOT_REQUESTED"
        ),
        "effective_per_run_wall_clock_timeout_seconds": timeout,
        "effective_random_seed": seed,
        "solution": str(output),
        "config_report": str(run_report_path),
        "solver_config_report": str(sidecar),
        "effective_config": report.get("effective"),
        "solver_execution_status": solution.get("meta", {}).get(
            "execution_status", "COMPLETED"
        ),
        "algorithm_implementation": solution.get("meta", {}).get(
            "algorithm_implementation"
        ),
        "candidate_source": solution.get("meta", {}).get(
            "candidate_source", "requested_algorithm"
        ),
        **resource_metrics,
        **official_resource_metrics,
        **kont_fields,
    }, stdout, stderr, returncode)


def run_auto_policy_one(
    solver: Path,
    instance: Path,
    output: Path,
    config_path: Path,
    requested: dict[str, Any],
    effective: dict[str, Any],
    repetition: int,
    global_deadline: float | None,
) -> dict[str, Any]:
    started = time.monotonic()
    seed = requested["random_seed"] + repetition
    timeout = min(
        effective["per_instance_timeout_seconds"],
        effective["per_algorithm_timeout_seconds"],
    )
    if global_deadline is not None:
        timeout = min(timeout, max(0.0, global_deadline - time.monotonic()))
    report_path = Path(str(output) + ".selection.json")
    run_config_path = Path(str(output) + ".run-config.json")
    trial_effective = {
        **effective,
        "algorithms": ["auto-policy"],
        "random_seed": seed,
        "per_instance_timeout_seconds": timeout,
        "per_algorithm_timeout_seconds": timeout,
    }
    run_config_path.write_text(json.dumps({
        "requested": requested,
        "effective": trial_effective,
        "automatic_adjustments": [
            "auto policy runs as a separate selection experiment",
            f"trial seed is {seed}",
            f"trial wall-clock cap is {timeout:g}s",
        ],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = [
        sys.executable, str(ROOT / "scripts/auto_solve.py"),
        "--instance", str(instance), "--output", str(output),
        "--solver", str(solver), "--config", str(config_path),
        "--seed", str(seed),
    ]
    if effective["overwrite_existing"]:
        command.append("--overwrite")
    code, stdout, stderr, limit_error, metrics = run_bounded_process_with_metrics(
        command, timeout, effective["memory_limit_mib"]
    )
    result: dict[str, Any] = {
        "algorithm": "auto-policy",
        "algorithm_id": "auto-policy",
        "requested_algorithm": "auto",
        "repetition": repetition,
        "seed": seed,
        "raw_exit_code": code,
        "seconds": time.monotonic() - started,
        "wall_seconds": metrics.get("wall_seconds"),
        "child_process_tree_cpu_seconds": metrics.get(
            "child_process_tree_cpu_seconds"
        ),
        "peak_process_tree_rss_bytes": metrics.get(
            "peak_process_tree_rss_bytes"
        ),
        "process_tree_rss_sample_count": metrics.get(
            "process_tree_rss_sample_count"
        ),
        "process_tree_cpu_sample_count": metrics.get(
            "process_tree_cpu_sample_count"
        ),
        "termination_reason": metrics.get("termination_reason"),
        "memory_enforcement": metrics.get("memory_enforcement"),
        "timeout_status": metrics.get("termination_reason") == "wall_clock_timeout",
        "stdout": stdout,
        "stderr": stderr,
        "solution": None,
        "makespan": None,
        "feasible": False,
        "official_validated": False,
        "official_validation_outcome": "NOT_VALIDATED",
        "validation_level": None,
        "config_report": str(run_config_path),
        "selection_report": str(report_path),
        "effective_config": None,
        "requested_configuration": copy.deepcopy(requested),
        "effective_configuration": copy.deepcopy(trial_effective),
        "optimality_certified": False,
        "certified_optimum": None,
        "validated_lower_bound": None,
        "relative_gap": None,
    }
    if limit_error:
        if "wall-clock" in limit_error:
            status = "time_limit"
        elif "RSS exceeded" in limit_error:
            status = "memory_limit"
        else:
            status = "resource_error"
        result.update(status=status, error=limit_error)
        result["timeout_status"] = status == "time_limit"
    elif code != 0:
        result.update(
            status="failed",
            error=stderr.strip() or f"auto policy exited {code}",
        )
    else:
        try:
            solution = json.loads(output.read_text(encoding="utf-8"))
            selection = json.loads(report_path.read_text(encoding="utf-8"))
            result.update(
                status="ok",
                solution=str(output),
                makespan=makespan(solution),
                feasible=True,
                validation_level="official",
                official_validated=bool(
                    selection.get("selection", {}).get("official_validated")
                ),
                official_validation_outcome=(
                    "VALID" if selection.get("selection", {}).get("official_validated")
                    else "INVALID"
                ),
                portfolio_selected_algorithm=selection.get("selection", {}).get(
                    "selected_algorithm"
                ),
                solver_execution_status=solution.get("meta", {}).get(
                    "execution_status", "COMPLETED"
                ),
                candidate_source=solution.get("meta", {}).get(
                    "candidate_source", "auto_policy"
                ),
                effective_config=selection.get("effective"),
                error=None,
            )
            if not result["official_validated"]:
                result.update(
                    status="official_invalid",
                    feasible=False,
                    solution=None,
                    error="auto policy output was not officially validated",
                )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            result.update(status="invalid_output", error=str(error))
    result["trial_status"] = trial_status(result)
    result["solver_exit_code"] = result.get("raw_exit_code")
    result["run_id"] = hashlib.sha256(json.dumps({
        "instance": str(instance.resolve()),
        "input_fingerprint": file_sha256(instance),
        "algorithm_id": "auto-policy",
        "repetition": repetition,
        "seed": seed,
        "config": hashlib.sha256(
            json.dumps(effective, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "executable": file_sha256(solver),
        "source": source_fingerprint(),
    }, sort_keys=True).encode()).hexdigest()[:24]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/default.json")
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument("--instances", type=Path, default=ROOT / "data/test")
    parser.add_argument("--instance", type=Path,
                        help="run one explicitly selected instance")
    parser.add_argument("--instance-ids",
                        help="comma-separated instance UIDs or filename stems")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, help="compatibility alias setting both timeout limits")
    parser.add_argument("--algorithms", help="comma-separated algorithm override")
    parser.add_argument("--algorithm", help="run one algorithm, independently")
    parser.add_argument("--all-algorithms", action="store_true",
                        help="run every canonical registry algorithm independently")
    parser.add_argument("--repetitions", type=int,
                        help="override randomized_repetitions in central config")
    parser.add_argument("--auto-policy", action="store_true",
                        help="run the separate tier-based auto-policy experiment")
    parser.add_argument("--thresholds", type=Path)
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

    if args.instance is not None and args.instance_ids:
        parser.error("--instance and --instance-ids cannot be combined")
    if args.algorithm and (args.algorithms or args.all_algorithms or args.auto_policy):
        parser.error("--algorithm cannot be combined with other algorithm selection modes")
    if args.all_algorithms and (args.algorithms or args.auto_policy):
        parser.error("--all-algorithms cannot be combined with --algorithms or --auto-policy")
    if args.auto_policy and (args.algorithms or args.all_algorithms):
        parser.error("--auto-policy cannot be combined with --algorithms or --all-algorithms")

    overrides: dict[str, Any] = {}
    if args.timeout is not None:
        overrides["per_instance_timeout_seconds"] = args.timeout
        overrides["per_algorithm_timeout_seconds"] = args.timeout
    if args.algorithms is not None:
        overrides["algorithms"] = [item.strip() for item in args.algorithms.split(",")]
    if args.algorithm is not None:
        overrides["algorithms"] = [args.algorithm]
    if args.all_algorithms:
        overrides["algorithms"] = list(CANONICAL_ALGORITHMS)
    if args.jobs is not None:
        overrides["benchmark_jobs"] = args.jobs
    if args.repetitions is not None:
        overrides["randomized_repetitions"] = args.repetitions
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
    global_started_monotonic = time.monotonic()
    global_started_wall = time.time()
    global_deadline = (
        global_started_monotonic + effective["global_run_deadline_seconds"]
        if effective["global_run_deadline_seconds"] is not None else None
    )

    solver = args.solver.resolve()
    if not solver.is_file() or not os.access(solver, os.X_OK):
        parser.error(f"solver executable not found or not executable: {solver}")
    if args.instance is None and not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    if args.instance is not None:
        instances = [args.instance.resolve()]
        if not instances[0].is_file():
            parser.error(f"instance file does not exist: {instances[0]}")
    else:
        instances = sorted(args.instances.glob("*.instance.json"))
    selected_ids = (
        {item.strip() for item in args.instance_ids.split(",") if item.strip()}
        if args.instance_ids else None
    )
    if args.instance_ids and not selected_ids:
        parser.error("--instance-ids must select at least one nonempty id")
    if not instances:
        parser.error(f"no *.instance.json inputs found in {args.instances}")
    instance_data: dict[Path, dict[str, Any]] = {}
    for path in instances:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            filename_id = path.stem.removesuffix(".instance")
            if selected_ids is not None and filename_id not in selected_ids:
                continue
            parser.error(f"cannot read valid JSON instance {path}: {error}")
        if not isinstance(value, dict) or not isinstance(value.get("instance_uid"), str):
            filename_id = path.stem.removesuffix(".instance")
            if selected_ids is not None and filename_id not in selected_ids:
                continue
            parser.error(f"instance has no string instance_uid: {path}")
        instance_data[path] = value
    if selected_ids is not None:
        instances = [
            path for path in instance_data
            if path.stem.removesuffix(".instance") in selected_ids
            or instance_data[path]["instance_uid"] in selected_ids
        ]
        matched = {
            path.stem.removesuffix(".instance") for path in instances
        } | {instance_data[path]["instance_uid"] for path in instances}
        missing = selected_ids - matched
        if missing:
            parser.error("selected instance id(s) not found: " + ", ".join(sorted(missing)))
        if not instances:
            parser.error("selected instance set is empty")
    if effective["official_validation"] and not official_validator_available():
        parser.error("official_validation requires cgshop2027_pyutils in this Python interpreter")
    auto_policy_mode = args.auto_policy
    if auto_policy_mode and not official_validator_available():
        parser.error("--auto-policy requires cgshop2027_pyutils for official selection")

    if "ilp" in {
        canonical_algorithm_id(name) for name in requested["algorithms"]
    } and effective["exact_solving_policy"] == "ip_kont_surrogate":
        cache_path = ROOT / "build/CMakeCache.txt"
        cache_text = cache_path.read_text(encoding="utf-8") if cache_path.is_file() else ""
        configured = next(
            (line.split("=", 1)[1] for line in cache_text.splitlines()
             if line.startswith("KONT_CMD_EXECUTABLE:FILEPATH=")),
            "",
        )
        if not configured or not Path(configured).is_file() or not os.access(configured, os.X_OK):
            parser.error(
                "selected ilp benchmark requires a configured executable KONT_CMD_EXECUTABLE; "
                "configure KONT or remove ilp from the selected algorithms"
            )

    output_dir = (args.output or Path(effective["output_directory"]))
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if output_dir.exists() and not effective["overwrite_existing"]:
        parser.error(f"output directory already exists: {output_dir} (set overwrite_existing)")
    if output_dir.exists() and not output_dir.is_dir():
        parser.error(f"output path is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        descriptor, probe_path = tempfile.mkstemp(prefix=".benchmark-write-test-", dir=output_dir)
        os.close(descriptor)
        Path(probe_path).unlink()
    except OSError as error:
        parser.error(f"benchmark output directory is not writable: {output_dir}: {error}")

    validation_timeout = max(
        30.0, effective["per_instance_timeout_seconds"],
        effective["per_algorithm_timeout_seconds"],
    )
    for path in instances:
        if global_deadline is not None:
            validation_timeout = min(
                validation_timeout, global_deadline - time.monotonic()
            )
            if validation_timeout <= 0:
                parser.error("global run deadline expired during instance preflight")
        code, _, stderr, limit_error, _ = run_bounded_process_with_metrics(
            [str(solver), "--validate-instance", "-i", str(path)],
            validation_timeout,
            effective["memory_limit_mib"],
        )
        if limit_error:
            parser.error(f"instance preflight failed for {path}: {limit_error}")
        if code != 0:
            parser.error(
                f"instance preflight failed for {path}: "
                f"{stderr.strip() or f'solver exited {code}'}"
            )

    config_report_path = output_dir / "runtime-config.json"

    try:
        from profile_instances import DEFAULT_THRESHOLDS, classify, extract_features, load_thresholds

        thresholds = load_thresholds(
            args.thresholds.resolve() if args.thresholds else DEFAULT_THRESHOLDS
        )
        threshold_version = thresholds["threshold_version"]
        instance_profiles: dict[Path, dict[str, Any]] = {}
        for path in instances:
            if global_deadline is not None and time.monotonic() >= global_deadline:
                parser.error("global run deadline expired during instance classification")
            profile_features = extract_features(path)
            classification = classify(profile_features, thresholds)
            instance_profiles[path] = {
                "estimated_tier": classification["tier"],
                "classification_reason": classification["reason"],
                "classification_confidence": classification["confidence"],
                "threshold_version": threshold_version,
                "input_size_features": {
                    "region_cell_count": profile_features["region_cell_count"],
                    "boundary_vertices": profile_features["boundary_vertices"],
                    "number_of_cutters": profile_features["number_of_cutters"],
                    "estimated_anchor_count": profile_features["estimated_features"][
                        "estimated_anchor_count"
                    ],
                    "estimated_raster_point_tests":
                        profile_features["estimated_features"][
                            "estimated_raster_point_tests"
                        ],
                },
            }
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"cannot classify selected inputs for benchmark metadata: {error}")

    algorithms = (
        ["auto"] if auto_policy_mode else
        [canonical_algorithm_id(name) for name in requested["algorithms"]]
    )
    if len(algorithms) != len(set(algorithms)):
        parser.error("selected algorithm list contains duplicate canonical algorithms")
    requested_by_canonical = {
        canonical_algorithm_id(name): name for name in requested["algorithms"]
    }
    if len({instance_data[path]["instance_uid"] for path in instances}) != len(instances):
        parser.error("selected instances must have unique instance_uid values")
    tasks: list[tuple[Path, str, str, int, Path]] = []
    for instance in instances:
        uid = instance_data[instance]["instance_uid"]
        for algorithm in algorithms:
            requested_algorithm = "auto" if algorithm == "auto" else requested_by_canonical[algorithm]
            repetitions = (
                requested["randomized_repetitions"]
                if algorithm in RANDOMIZED_ALGORITHMS else 1
            )
            for repetition in range(repetitions):
                suffix = f".rep-{repetition + 1}" if repetitions > 1 else ""
                name_suffix = "auto-policy" if algorithm == "auto" else algorithm
                tasks.append((
                    instance, algorithm, requested_algorithm, repetition,
                    output_dir / (
                        f"{output_component(uid)}.{name_suffix}{suffix}.solution.json"
                    ),
                ))
    if len({task[4] for task in tasks}) != len(tasks):
        parser.error("selected trials produce colliding output paths")
    if not effective["overwrite_existing"]:
        existing = [path for _, _, _, _, path in tasks
                    if (path.exists() or Path(str(path) + ".config.json").exists() or
                        Path(str(path) + ".run-config.json").exists() or
                        Path(str(path) + ".selection.json").exists() or
                        Path(str(path) + ".logs").exists())]
        if existing:
            parser.error("candidate already exists (set overwrite_existing): " +
                         ", ".join(str(path) for path in existing[:5]))

    source_hash = source_fingerprint()
    executable_hash = file_sha256(solver)
    config_hash = hashlib.sha256(
        json.dumps(effective, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if config_report_path.exists() and not effective["overwrite_existing"]:
        parser.error(f"configuration report exists: {config_report_path}")
    report = {
        "schema_version": 2,
        "requested": requested,
        "effective": effective,
        "automatic_adjustments": adjustments,
        "selected_instance_paths": [str(path.resolve()) for path in instances],
        "selected_algorithm_ids": [
            "auto-policy" if algorithm == "auto" else algorithm
            for algorithm in algorithms
        ],
        "source_version_fingerprint": source_hash,
        "executable_fingerprint_sha256": executable_hash,
        "effective_configuration_fingerprint": config_hash,
        "available_cpu_workers": available_cpu_workers(),
        "intended_max_active_solver_workers":
            effective["benchmark_jobs"] * effective["threads_per_solver"],
        "memory_enforcement": "sampled process-tree RSS watchdog",
        "cpu_measurement": "sampled cumulative process-tree CPU from ps",
        "global_run_deadline_started_at": (
            global_started_wall
            if effective["global_run_deadline_seconds"] is not None else None
        ),
        "official_validation": (
            "enabled" if effective["official_validation"] else "disabled"
        ),
    }
    config_report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=effective["benchmark_jobs"]) as executor:
        futures = {
            executor.submit(
                run_auto_policy_one if algorithm == "auto" else run_one,
                *(
                    (solver, instance, output, args.config.resolve(), requested,
                     effective, repetition, global_deadline)
                    if algorithm == "auto" else
                    (solver, instance, algorithm, repetition, output,
                     requested, effective, global_deadline)
                ),
            ): (instance, algorithm, requested_algorithm, repetition, output)
            for instance, algorithm, requested_algorithm, repetition, output in tasks
        }
        for future in as_completed(futures):
            instance, algorithm, requested_algorithm, repetition, output = futures[future]
            result = collect_benchmark_future(future, algorithm, repetition)
            instance_uid = instance_data[instance]["instance_uid"]
            result["instance_uid"] = instance_uid
            result["instance_id"] = instance_uid
            result["input_path"] = str(instance.resolve())
            result["input_fingerprint_sha256"] = file_sha256(instance)
            result["algorithm_id"] = "auto-policy" if algorithm == "auto" else algorithm
            result["requested_algorithm"] = requested_algorithm
            result["algorithm_version_fingerprint"] = executable_hash
            result["source_version_fingerprint"] = source_hash
            trial_config = result.get("effective_configuration") or effective
            trial_config_hash = hashlib.sha256(
                json.dumps(
                    trial_config, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            result["effective_config_fingerprint"] = trial_config_hash
            result["batch_config_fingerprint"] = config_hash
            result["instance_profile"] = instance_profiles[instance]
            input_size_features = instance_profiles[instance]["input_size_features"]
            result["estimated_anchor_count"] = input_size_features[
                "estimated_anchor_count"
            ]
            result["estimated_raster_point_tests"] = input_size_features[
                "estimated_raster_point_tests"
            ]
            result.setdefault("requested_configuration", requested)
            result.setdefault(
                "effective_configuration",
                result.get("effective_config") or effective,
            )
            result["actual_producing_algorithm"] = result.get(
                "portfolio_selected_algorithm",
                result.get(
                    "algorithm_implementation", result.get("candidate_source")
                ),
            )
            result["log_path"] = str(output) + ".logs"
            result["output_solution_path"] = (
                str(output) if output.is_file() else None
            )
            log_path = Path(result["log_path"])
            log_path.mkdir(parents=True, exist_ok=True)
            (log_path / "stdout.log").write_text(
                result.get("stdout", ""), encoding="utf-8"
            )
            (log_path / "stderr.log").write_text(
                result.get("stderr", ""), encoding="utf-8"
            )
            if result.get("status") == "ok" and result.get("feasible", True):
                result["solution_validity_status"] = "VALID"
                result["producing_algorithm"] = result.get(
                    "portfolio_selected_algorithm",
                    result.get(
                        "algorithm_implementation", result.get("candidate_source")
                    ),
                )
            else:
                result["solution_validity_status"] = (
                    "INVALID" if result.get("status") in {
                        "invalid_output", "official_invalid"
                    } else "NO_SOLUTION"
                )
                result["producing_algorithm"] = None
            result["trial_status"] = trial_status(result)
            stable_identity = {
                "instance_id": instance_uid,
                "input_fingerprint": result["input_fingerprint_sha256"],
                "algorithm_id": result["algorithm_id"],
                "repetition": repetition,
                "seed": result.get("seed", requested["random_seed"] + repetition),
                "configuration_fingerprint": trial_config_hash,
                "source_fingerprint": source_hash,
                "executable_fingerprint": executable_hash,
            }
            result["run_id"] = hashlib.sha256(
                json.dumps(stable_identity, sort_keys=True).encode("utf-8")
            ).hexdigest()[:24]
            result["actual_producing_algorithm"] = result.get(
                "producing_algorithm"
            )
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
                f"{result['instance_uid']}\t{result['algorithm_id']}\t"
                f"{repetition + 1}\t{result['trial_status']}\t"
                f"{result.get('makespan', '')}"
            )

    results.sort(key=lambda row: (
        row["instance_uid"], row["algorithm_id"], row["repetition"]
    ))
    table = output_dir / "benchmark.tsv"
    fields = (
              "run_id", "instance_id", "instance_uid", "input_path",
              "input_fingerprint_sha256", "algorithm_id", "algorithm",
              "requested_algorithm", "producing_algorithm",
              "actual_producing_algorithm", "repetition", "seed",
              "requested_configuration",
              "output_solution_path",
              "status", "trial_status", "solution_validity_status", "feasible",
              "makespan", "optimality_certified", "certified_optimum",
              "validated_lower_bound", "relative_gap",
              "instance_profile", "estimated_anchor_count",
              "estimated_raster_point_tests", "algorithm_version_fingerprint",
              "source_version_fingerprint", "effective_config_fingerprint",
              "batch_config_fingerprint",
              "effective_configuration",
              "validation_level", "official_validated", "candidate_kind",
              "official_validation_outcome", "solver_exit_code", "raw_exit_code",
              "timeout_status", "error", "log_path",
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
              "solver_config_report")
    def tsv_cell(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, (dict, list, bool)):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return str(value)

    table.write_text(
        "\t".join(fields) + "\n" +
        "\n".join(
            "\t".join(
                tsv_cell(row.get(field, "")).replace("\t", " ").replace("\n", " ")
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
    from summarize_benchmark import generate_reports

    report_paths = generate_reports(
        table, output_dir, overwrite=effective["overwrite_existing"]
    )
    successes = sum(
        row["status"] == "ok" and (
            not effective["official_validation"]
            or row.get("official_validated") is True
        )
        for row in results
    )
    print(
        f"completed {successes}/{len(results)} runs with "
        f"{effective['benchmark_jobs']} benchmark_jobs x "
        f"{effective['threads_per_solver']} threads_per_solver"
    )
    print(f"run report: {config_report_path}")
    print(f"results table: {table}")
    print(f"reference comparison: {comparison_json} and {comparison_table}")
    print(f"quality/resource reports: {len(report_paths)} artifacts in {output_dir}")
    return 0 if successes == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
