"""Shared runtime configuration loader for local solver runners."""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config/default.json"
ALGORITHMS = {
    "strip", "partition", "local", "anchor-cover", "balanced-greedy",
    "boustrophedon", "stc", "tsp-cov", "frederickson", "mstc",
    "region-partition", "ilp", "column-gen", "lns", "hybrid",
}
PORTFOLIO_ALGORITHMS = {
    "boustrophedon", "stc", "frederickson", "mstc", "region-partition",
    "ilp", "column-gen", "tsp-cov",
}
CONFIG_KEYS = {
    "global_run_deadline_seconds", "per_instance_timeout_seconds",
    "per_algorithm_timeout_seconds", "ip_kont_timeout_seconds",
    "threads_per_solver", "benchmark_jobs", "memory_limit_mib", "random_seed",
    "algorithms", "algorithm_parameters", "difficulty_tier_filter",
    "exact_solving_policy", "exact_solver_max_candidates",
    "exact_solver_exploratory_time_budget_seconds", "heuristic_portfolio",
    "randomized_repetitions", "output_directory", "overwrite_existing",
    "logging_verbosity", "official_validation",
}


def available_cpu_workers() -> int:
    if hasattr(os, "sched_getaffinity"):
        try:
            return max(1, len(os.sched_getaffinity(0)))
        except OSError:
            pass
    return max(1, os.cpu_count() or 1)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a JSON object")
    unknown = sorted(set(value) - CONFIG_KEYS)
    if unknown:
        raise ValueError("unknown configuration key(s): " + ", ".join(unknown))
    return value


def load_runtime_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return requested values, effective values, and automatic adjustments."""
    defaults = _read_json(DEFAULT_CONFIG_PATH)
    requested = copy.deepcopy(defaults)
    if config_path is not None:
        selected = _read_json(config_path)
        for key, value in selected.items():
            if key == "algorithm_parameters":
                requested[key].update(value)
            else:
                requested[key] = value
    if overrides:
        for key, value in overrides.items():
            if key not in CONFIG_KEYS:
                raise ValueError(f"unknown runtime override: {key}")
            if value is not None:
                if key == "algorithm_parameters":
                    if not isinstance(value, dict):
                        raise ValueError("algorithm_parameters override must be an object")
                    requested[key].update(value)
                else:
                    requested[key] = value

    parameters = requested["algorithm_parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("algorithm_parameters must be an object")
    unknown_parameters = sorted(set(parameters) - {
        "lns_iterations", "lns_max_anchors", "lns_max_move_anchors",
        "tsp_max_anchors", "two_opt_passes"
    })
    if unknown_parameters:
        raise ValueError("unsupported algorithm parameter(s): " +
                         ", ".join(unknown_parameters))
    for name, minimum in (
        ("lns_iterations", 0), ("lns_max_anchors", 1),
        ("lns_max_move_anchors", 1), ("tsp_max_anchors", 1),
        ("two_opt_passes", 0)
    ):
        value = parameters.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"algorithm_parameters.{name} must be an integer >= {minimum}")
    if parameters["lns_iterations"] > 100000:
        raise ValueError("algorithm_parameters.lns_iterations must be at most 100000")
    if parameters["lns_max_move_anchors"] > parameters["lns_max_anchors"]:
        raise ValueError(
            "algorithm_parameters.lns_max_move_anchors must not exceed "
            "lns_max_anchors"
        )

    for name in (
        "per_instance_timeout_seconds", "per_algorithm_timeout_seconds",
        "ip_kont_timeout_seconds", "exact_solver_exploratory_time_budget_seconds",
    ):
        value = requested[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or not 0 <= value <= 31536000):
            raise ValueError(f"{name} must be between 0 and 31536000 seconds")
    deadline = requested["global_run_deadline_seconds"]
    if deadline is not None and (
        isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or
        not math.isfinite(deadline) or not 0 <= deadline <= 31536000
    ):
        raise ValueError("global_run_deadline_seconds must be null or between 0 and 31536000")
    for name in (
        "threads_per_solver", "benchmark_jobs", "memory_limit_mib",
        "randomized_repetitions",
    ):
        value = requested[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if requested["randomized_repetitions"] > 1000:
        raise ValueError("randomized_repetitions must be at most 1000")
    if requested["threads_per_solver"] != 1:
        raise ValueError("threads_per_solver must be 1; current algorithms are single-threaded")
    if (not isinstance(requested["random_seed"], int) or
            isinstance(requested["random_seed"], bool) or
            not 0 <= requested["random_seed"] <= 2147483647):
        raise ValueError("random_seed must be a nonnegative 32-bit integer")
    algorithms = requested["algorithms"]
    if (not isinstance(algorithms, list) or not algorithms or
            any(not isinstance(item, str) or item not in ALGORITHMS for item in algorithms) or
            len(algorithms) != len(set(algorithms))):
        raise ValueError("algorithms must be a nonempty list of supported algorithm names")
    tiers = requested["difficulty_tier_filter"]
    if tiers != ["all"]:
        raise ValueError(
            "difficulty_tier_filter only supports ['all'] until a validated tier classifier exists"
        )
    if requested["exact_solving_policy"] not in {"disabled", "ip_kont_surrogate"}:
        raise ValueError(
            "exact_solving_policy must be disabled or ip_kont_surrogate; IP-KONT is not exact routing"
        )
    if (isinstance(requested["exact_solver_max_candidates"], bool) or
            not isinstance(requested["exact_solver_max_candidates"], int) or
            requested["exact_solver_max_candidates"] < 0):
        raise ValueError("exact_solver_max_candidates must be nonnegative")
    if (requested["exact_solving_policy"] == "disabled" and
            requested["exact_solver_max_candidates"] != 0):
        raise ValueError(
            "exact_solver_max_candidates requires exact_solving_policy=ip_kont_surrogate"
        )
    if requested["exact_solver_exploratory_time_budget_seconds"] != 0:
        raise ValueError(
            "exact_solver_exploratory_time_budget_seconds is unsupported until tier classification"
        )
    portfolio = requested["heuristic_portfolio"]
    if (not isinstance(portfolio, list) or
            any(not isinstance(item, str) for item in portfolio) or
            len(portfolio) != len(set(portfolio)) or
            any(item not in PORTFOLIO_ALGORITHMS for item in portfolio) or
            not portfolio):
        raise ValueError("heuristic_portfolio contains unsupported or duplicate names")
    if not isinstance(requested["randomized_repetitions"], int):
        raise ValueError("randomized_repetitions must be an integer")
    if requested["randomized_repetitions"] > 1 and not any(
        name in {"lns", "hybrid"} for name in algorithms
    ):
        raise ValueError("repetitions > 1 requires randomized algorithm lns or hybrid")
    if not isinstance(requested["output_directory"], str) or not requested["output_directory"]:
        raise ValueError("output_directory must be a nonempty path")
    if requested["logging_verbosity"] not in {"debug", "info", "warning", "error"}:
        raise ValueError("logging_verbosity must be debug, info, warning, or error")
    for name in ("overwrite_existing", "official_validation"):
        if not isinstance(requested[name], bool):
            raise ValueError(f"{name} must be a boolean")

    effective = copy.deepcopy(requested)
    adjustments: list[str] = []
    workers = available_cpu_workers()
    maximum_jobs = max(1, workers // effective["threads_per_solver"])
    if effective["benchmark_jobs"] > maximum_jobs:
        adjustments.append(
            f"benchmark_jobs reduced from {effective['benchmark_jobs']} to "
            f"{maximum_jobs} to stay within {workers} available CPU workers"
        )
        effective["benchmark_jobs"] = maximum_jobs
    return requested, effective, adjustments
