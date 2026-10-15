"""Build honest feasible-solution, bound, and optimality comparison records."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def compare_instance_results(
    results: Iterable[dict[str, Any]],
    references: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate benchmark runs and optional independently certified references.

    Reference values are used only with explicit proof/validity flags and a
    nonempty source. Current benchmark runs provide no such original-objective
    reference, so their optimum and lower-bound fields remain null.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row["instance_uid"])].append(row)

    comparisons = []
    references = references or {}
    for uid, rows in sorted(grouped.items()):
        feasible = [
            row for row in rows
            if row.get("status") == "ok"
            and row.get("validation_level") in {"internal_cpp", "official"}
            and isinstance(row.get("makespan"), int)
            and not isinstance(row.get("makespan"), bool)
        ]
        best = min(
            feasible,
            key=lambda row: (row["makespan"], row["algorithm"], row["repetition"]),
            default=None,
        )
        official = [
            row for row in feasible if row.get("official_validated") is True
        ]
        best_official = min(
            official,
            key=lambda row: (row["makespan"], row["algorithm"], row["repetition"]),
            default=None,
        )
        ip_rows = [row for row in rows if row.get("algorithm") == "ilp"]
        ip_run = ip_rows[0] if ip_rows else None
        ip_status = (
            ip_run.get("ip_kont_status") if ip_run else "NOT_RUN"
        )
        if ip_run and not ip_status and ip_run.get("status") in {
            "time_limit", "memory_limit", "memory_probe_failed"
        }:
            ip_status = "TIME_LIMIT_NO_INCUMBENT"
        if ip_run and not ip_status:
            ip_status = "ERROR"

        best_makespan = best["makespan"] if best else None

        reference = references.get(uid, {})
        certified_optimum = None
        optimum_source = None
        if (
            reference.get("optimality_certified") is True
            and reference.get("formulation_exact_for_original_objective") is True
            and reference.get("solution_validated") is True
            and reference.get("objective_matched") is True
            and _positive_integer(reference.get("certified_optimum_makespan"))
            and isinstance(reference.get("certified_optimum_source"), str)
            and reference["certified_optimum_source"].strip()
        ):
            certified_optimum = reference["certified_optimum_makespan"]
            optimum_source = reference["certified_optimum_source"]
            if best_makespan is not None and certified_optimum > best_makespan:
                raise ValueError(
                    f"{uid}: certified optimum exceeds a validated feasible makespan"
                )

        lower_bound = None
        lower_bound_source = (
            "unavailable: the column-assignment surrogate is not a proven "
            "lower bound for closed-tour makespan"
        )
        if (
            reference.get("ip_kont_lower_bound_valid") is True
            and _positive_integer(reference.get("ip_kont_lower_bound"))
            and isinstance(reference.get("ip_kont_lower_bound_source"), str)
            and reference["ip_kont_lower_bound_source"].strip()
        ):
            lower_bound = reference["ip_kont_lower_bound"]
            lower_bound_source = reference["ip_kont_lower_bound_source"]
            if best_makespan is not None and lower_bound > best_makespan:
                raise ValueError(
                    f"{uid}: valid lower bound exceeds a validated feasible makespan"
                )
        relative_gap = (
            (best_makespan - lower_bound) / lower_bound
            if best_makespan is not None and lower_bound is not None and lower_bound > 0
            else None
        )
        exact_agreement = (
            best_makespan == certified_optimum
            if best_makespan is not None and certified_optimum is not None else None
        )
        additive_difference = (
            best_makespan - certified_optimum
            if best_makespan is not None and certified_optimum is not None else None
        )
        relative_difference = (
            additive_difference / certified_optimum
            if additive_difference is not None and certified_optimum > 0 else None
        )

        def candidate_source(row: dict[str, Any] | None) -> str | None:
            if row is None:
                return None
            kind = row.get("candidate_kind")
            if kind == "heuristic_fallback_from_ip_kont_surrogate":
                return "partition fallback (ilp wrapper)"
            if kind == "ip_kont_surrogate_incumbent":
                return "ilp (IP-KONT surrogate candidate)"
            return str(row["algorithm"])

        comparisons.append({
            "instance_uid": uid,
            "best_validated_feasible_makespan": best_makespan,
            "best_validated_algorithm": candidate_source(best),
            "best_validated_validation_level": (
                best.get("validation_level") if best else None
            ),
            "best_officially_validated_feasible_makespan": (
                best_official["makespan"] if best_official else None
            ),
            "best_officially_validated_algorithm": (
                candidate_source(best_official)
            ),
            "certified_optimum_makespan": certified_optimum,
            "certified_optimum_source": optimum_source,
            "exact_agreement": exact_agreement,
            "additive_difference_from_optimum": additive_difference,
            "relative_difference_from_optimum": relative_difference,
            "ip_kont_lower_bound": lower_bound,
            "ip_kont_lower_bound_valid": lower_bound is not None,
            "ip_kont_lower_bound_source": lower_bound_source,
            "relative_gap_to_valid_lower_bound": relative_gap,
            "best_known_upper_bound": best_makespan,
            "best_known_upper_bound_source": (
                f"{candidate_source(best)} ({best['validation_level']} validation)"
                if best else None
            ),
            "ip_kont_solver_status": ip_status,
            "ip_kont_raw_status": (
                ip_run.get("ip_kont_raw_status") if ip_run else None
            ),
            "ip_kont_proof_completed": False,
            "ip_kont_solver_runtime_seconds": (
                ip_run.get("ip_kont_runtime_seconds") if ip_run else None
            ),
            "ip_kont_process_exit_code": (
                ip_run.get("ip_kont_process_exit_code") if ip_run else None
            ),
            "ip_kont_reported_mip_gap": None,
            "ip_kont_reported_dual_bound": None,
            "ip_kont_elapsed_seconds": ip_run.get("seconds") if ip_run else None,
            "ip_kont_termination_reason": (
                ip_run.get("ip_kont_termination_reason") or
                ip_run.get("error") if ip_run else "not requested"
            ),
            "ip_kont_model": (
                ip_run.get("ip_kont_model") if ip_run else None
            ),
            "ip_kont_variable_count": (
                ip_run.get("ip_kont_variable_count") if ip_run else None
            ),
            "ip_kont_binary_variable_count": (
                ip_run.get("ip_kont_binary_variable_count") if ip_run else None
            ),
            "ip_kont_continuous_variable_count": (
                ip_run.get("ip_kont_continuous_variable_count") if ip_run else None
            ),
            "ip_kont_constraint_count": (
                ip_run.get("ip_kont_constraint_count") if ip_run else None
            ),
            "ip_kont_assignment_constraint_count": (
                ip_run.get("ip_kont_assignment_constraint_count") if ip_run else None
            ),
            "ip_kont_load_constraint_count": (
                ip_run.get("ip_kont_load_constraint_count") if ip_run else None
            ),
            "ip_kont_surrogate_assignment_objective": (
                ip_run.get("ip_kont_surrogate_assignment_objective")
                if ip_run else None
            ),
            "ip_kont_reconstructed_makespan": (
                ip_run.get("ip_kont_reconstructed_makespan") if ip_run else None
            ),
            "ip_kont_exact_for_original_objective": False,
            "ip_kont_solver_log": (
                ip_run.get("ip_kont_solver_log") if ip_run else None
            ),
        })
    return comparisons


def comparison_tsv(comparisons: list[dict[str, Any]]) -> str:
    fields = (
        "instance_uid",
        "best_validated_feasible_makespan",
        "best_validated_algorithm",
        "best_validated_validation_level",
        "best_officially_validated_feasible_makespan",
        "certified_optimum_makespan",
        "exact_agreement",
        "additive_difference_from_optimum",
        "relative_difference_from_optimum",
        "ip_kont_lower_bound",
        "ip_kont_lower_bound_valid",
        "relative_gap_to_valid_lower_bound",
        "best_known_upper_bound",
        "best_known_upper_bound_source",
        "ip_kont_solver_status",
        "ip_kont_raw_status",
        "ip_kont_proof_completed",
        "ip_kont_solver_runtime_seconds",
        "ip_kont_process_exit_code",
        "ip_kont_reported_mip_gap",
        "ip_kont_reported_dual_bound",
        "ip_kont_elapsed_seconds",
        "ip_kont_termination_reason",
        "ip_kont_model",
        "ip_kont_variable_count",
        "ip_kont_binary_variable_count",
        "ip_kont_continuous_variable_count",
        "ip_kont_constraint_count",
        "ip_kont_assignment_constraint_count",
        "ip_kont_load_constraint_count",
        "ip_kont_surrogate_assignment_objective",
        "ip_kont_reconstructed_makespan",
        "ip_kont_exact_for_original_objective",
    )
    lines = ["\t".join(fields)]
    for row in comparisons:
        lines.append("\t".join(
            str(row.get(field, "") if row.get(field) is not None else "")
            .replace("\t", " ").replace("\r", " ").replace("\n", " ")
            for field in fields
        ))
    return "\n".join(lines) + "\n"
