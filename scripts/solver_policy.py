"""Deterministic tier policy and candidate selection for local auto solving."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

from profile_instances import (
    DEFAULT_THRESHOLDS,
    classify,
    extract_features,
    load_thresholds,
)
from runtime_config import ALGORITHMS, ROOT


DEFAULT_POLICY = ROOT / "config/auto_policy.json"
ALGORITHM_NAMES = ALGORITHMS - {"hybrid", "local", "ilp"}


def load_auto_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read auto policy {path}: {error}") from error
    expected = {
        "policy_version", "exact_model", "tier_policies", "ip_kont_surrogate_probe"
    }
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError("auto policy must define policy_version, exact_model, tier_policies, and ip_kont_surrogate_probe")
    if not isinstance(config["policy_version"], str) or not config["policy_version"]:
        raise ValueError("policy_version must be a nonempty string")
    exact = config["exact_model"]
    if not isinstance(exact, dict) or set(exact) != {
        "available_for_original_closed_tour_objective", "method", "light_budget_seconds"
    }:
        raise ValueError("exact_model has unsupported or missing settings")
    if exact["available_for_original_closed_tour_objective"] is not False:
        raise ValueError(
            "no exact model for the original closed-tour objective is implemented; "
            "do not enable an unverified method"
        )
    if exact["method"] is not None:
        raise ValueError("exact_model.method must remain null until an exact route solver exists")
    if not _seconds(exact["light_budget_seconds"], allow_zero=True):
        raise ValueError("light exact budget must be between 0 and 31536000 seconds")

    tiers = config["tier_policies"]
    if not isinstance(tiers, dict) or set(tiers) != {"LIGHT", "MEDIUM", "HEAVY", "UNKNOWN"}:
        raise ValueError("tier_policies must define LIGHT, MEDIUM, HEAVY, and UNKNOWN")
    for name, values in tiers.items():
        if not isinstance(values, dict) or set(values) != {
            "heuristic_portfolio", "per_algorithm_timeout_seconds"
        }:
            raise ValueError(f"{name} must define portfolio and per-algorithm timeout")
        portfolio = values["heuristic_portfolio"]
        if (not isinstance(portfolio, list) or not portfolio or
                any(not isinstance(item, str) or item not in ALGORITHM_NAMES
                    for item in portfolio) or len(set(portfolio)) != len(portfolio)):
            raise ValueError(
                f"{name} portfolio must contain distinct supported non-fallback heuristics"
            )
        if not _seconds(values["per_algorithm_timeout_seconds"], allow_zero=False):
            raise ValueError(f"{name} per-algorithm timeout must be positive")
    probe = config["ip_kont_surrogate_probe"]
    if not isinstance(probe, dict) or set(probe) != {
        "enabled_by_default", "maximum_estimated_column_count", "budget_seconds"
    }:
        raise ValueError("ip_kont_surrogate_probe has unsupported or missing settings")
    if not isinstance(probe["enabled_by_default"], bool):
        raise ValueError("ip_kont_surrogate_probe.enabled_by_default must be boolean")
    if (not isinstance(probe["maximum_estimated_column_count"], int) or
            isinstance(probe["maximum_estimated_column_count"], bool) or
            probe["maximum_estimated_column_count"] < 0):
        raise ValueError("maximum_estimated_column_count must be nonnegative")
    if not _seconds(probe["budget_seconds"], allow_zero=True):
        raise ValueError("IP-KONT surrogate budget must be between 0 and 31536000 seconds")
    if probe["enabled_by_default"] and (
        probe["maximum_estimated_column_count"] < 1 or probe["budget_seconds"] <= 0
    ):
        raise ValueError(
            "enabled IP-KONT probe requires positive estimated-column cap and budget"
        )
    return config


def _seconds(value: Any, allow_zero: bool) -> bool:
    minimum = 0 if allow_zero else 0.000001
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and
        math.isfinite(value) and minimum <= value <= 31536000
    )


def build_plan(
    instance_path: Path,
    thresholds_path: Path = DEFAULT_THRESHOLDS,
    policy_path: Path = DEFAULT_POLICY,
    requested_policy: str = "auto",
    forced_algorithm: str | None = None,
    include_ip_kont_surrogate: bool = False,
    surrogate_allowed_by_runtime_config: bool = True,
) -> dict[str, Any]:
    thresholds = load_thresholds(thresholds_path)
    policy = load_auto_policy(policy_path)
    features = extract_features(instance_path)
    tier = classify(features, thresholds)
    tier_name = tier["tier"]
    if requested_policy not in {"auto", "heuristic", "exact"}:
        raise ValueError(f"unsupported execution policy: {requested_policy}")
    if forced_algorithm is not None:
        if forced_algorithm not in ALGORITHMS:
            raise ValueError(f"unsupported forced algorithm: {forced_algorithm}")
        algorithm_list = [forced_algorithm]
        mode = "forced_algorithm"
        reason = f"explicit algorithm override: {forced_algorithm}"
    elif requested_policy == "exact":
        raise ValueError(
            "exact policy requested, but no mathematically exact solver for the "
            "original closed-tour objective is implemented"
        )
    else:
        tier_policy = policy["tier_policies"][tier_name]
        algorithm_list = list(tier_policy["heuristic_portfolio"])
        mode = requested_policy
        reason = (
            "no exact route model is implemented; using bounded tier portfolio"
            if requested_policy == "auto" else "explicit heuristic portfolio policy"
        )
    probe = policy["ip_kont_surrogate_probe"]
    probe_attempted = False
    probe_requested = include_ip_kont_surrogate or (
        requested_policy == "auto" and tier_name == "MEDIUM" and
        probe["enabled_by_default"]
    )
    probe_reason = "disabled; IP-KONT is not exact for the original route objective"
    if probe_requested and not surrogate_allowed_by_runtime_config:
        probe_reason = (
            "not run: exact_solving_policy=disabled in the central runtime configuration"
        )
    elif probe_requested:
        limit = probe["maximum_estimated_column_count"]
        estimated_columns = features["estimated_ip_kont_columns_upper_bound"]
        if estimated_columns > limit:
            probe_reason = (
                f"not run: estimated IP-KONT columns upper bound {estimated_columns} "
                f"exceeds configured surrogate-probe cap {limit}"
            )
        elif probe["budget_seconds"] <= 0:
            probe_reason = "not run: surrogate-probe budget is zero"
        else:
            algorithm_list.append("ilp")
            probe_attempted = True
            probe_reason = (
                "bounded IP-KONT strip-assignment surrogate requested explicitly; "
                "not an exact solve of the closed-tour objective"
            )
    tier_timeout = policy["tier_policies"][tier_name]["per_algorithm_timeout_seconds"]
    return {
        "requested_policy": mode,
        "requested_algorithm": forced_algorithm,
        "estimated_tier": tier_name,
        "classification_reason": tier["reason"],
        "classification_confidence": tier["confidence"],
        "threshold_version": thresholds["threshold_version"],
        "policy_version": policy["policy_version"],
        "instance_features": features,
        "algorithms_to_run": algorithm_list,
        "per_algorithm_timeout_seconds": tier_timeout,
        "exact_method_available": False,
        "exact_method_status": "unavailable",
        "exact_method_reason": (
            "IP-KONT minimizes a strip-assignment surrogate; it does not optimize "
            "the original closed-tour makespan objective"
        ),
        "ip_kont_surrogate_requested": probe_requested,
        "ip_kont_surrogate_scheduled": probe_attempted,
        "ip_kont_surrogate_reason": probe_reason,
        "ip_kont_surrogate_budget_seconds": (
            probe["budget_seconds"] if probe_attempted else 0.0
        ),
        "selection_reason": reason,
    }


def select_candidate(
    plan: dict[str, Any],
    candidate_results: list[dict[str, Any]],
    validator: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Choose minimum makespan among successful officially accepted candidates."""
    eligible = []
    for candidate in candidate_results:
        if candidate.get("status") != "ok":
            continue
        if candidate.get("validation_level") != "official" or not candidate.get(
            "official_validated"
        ):
            continue
        if not isinstance(candidate.get("makespan"), (int, float)):
            continue
        if validator is not None and not validator(candidate):
            continue
        eligible.append(candidate)
    if not eligible:
        return {
            "status": "no_valid_candidate",
            "selected_algorithm": None,
            "selected_solution": None,
            "selected_makespan": None,
            "selected_candidate_kind": None,
            "official_validated": False,
            "optimality_certified": False,
            "selection_reason": "no candidate passed official validation",
            "exact_method_status": plan["exact_method_status"],
        }
    selected = min(
        eligible,
        key=lambda candidate: (
            candidate["makespan"], candidate["algorithm"]
        ),
    )
    kind = selected.get(
        "candidate_kind",
        "ip_kont_surrogate" if selected["algorithm"] == "ilp" else "heuristic",
    )
    return {
        "status": "ok",
        "selected_algorithm": selected["algorithm"],
        "selected_solution": selected.get("solution"),
        "selected_makespan": selected["makespan"],
        "selected_candidate_kind": kind,
        "official_validated": True,
        "optimality_certified": False,
        "selection_reason": (
            "lowest makespan among candidates passing official validation"
        ),
        "exact_method_status": plan["exact_method_status"],
    }
