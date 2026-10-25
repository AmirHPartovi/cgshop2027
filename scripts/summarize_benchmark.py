#!/usr/bin/env python3
"""Generate reproducible local rankings and reports from benchmark trial records."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _value(raw: str) -> Any:
    if raw == "" or raw == "null":
        return None
    if raw in {"true", "false"}:
        return raw == "true"
    if raw[:1] in {"{", "["}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    try:
        return float(raw) if any(char in raw for char in ".eE") else int(raw)
    except ValueError:
        return raw


def read_trials(path: Path) -> list[dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8") as source:
        rows = [{key: _value(value) for key, value in row.items()}
                for row in csv.DictReader(source, delimiter=delimiter)]
    if not rows:
        raise ValueError(f"benchmark input contains no trial records: {path}")
    for index, row in enumerate(rows, 1):
        if not row.get("instance_uid") or not row.get("algorithm_id"):
            raise ValueError(f"trial row {index} lacks instance_uid or algorithm_id")
        row.setdefault("repetition", 0)
        row.setdefault("trial_status", row.get("status", "ERROR"))
    run_ids = [row.get("run_id") for row in rows if row.get("run_id")]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("benchmark input contains duplicate run_id values")
    return rows


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _valid(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("solution_validity_status") == "VALID"
        and row.get("validation_level") in {"internal_cpp", "official"}
        and row.get("official_validation_outcome") != "INVALID"
        and _number(row.get("makespan")) is not None
    )


def _mean(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.fmean(data) if data else None


def _median(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.median(data) if data else None


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    data = sorted(values)
    if not data:
        return None
    position = (len(data) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(data) - 1)
    fraction = position - lower
    return data[lower] * (1 - fraction) + data[upper] * fraction


def _geometric_mean(values: Iterable[float]) -> float | None:
    data = list(values)
    if not data or any(value <= 0 for value in data):
        return None
    return math.exp(statistics.fmean(math.log(value) for value in data))


def _tier(row: dict[str, Any]) -> str:
    profile = row.get("instance_profile")
    if isinstance(profile, dict):
        tier = profile.get("estimated_tier")
        if isinstance(tier, str) and tier.upper() in {"LIGHT", "MEDIUM", "HEAVY"}:
            return tier.upper()
    return "UNKNOWN"


def _certified_optimum(row: dict[str, Any]) -> float | None:
    if not (
        _valid(row)
        and row.get("optimality_certified") is True
        and row.get("formulation_exact_for_original_objective") is True
        and row.get("certified_solution_validated") is True
        and row.get("certified_objective_matched") is True
        and isinstance(row.get("certified_optimum_source"), str)
        and row["certified_optimum_source"].strip()
    ):
        return None
    value = _number(row.get("certified_optimum"))
    return value if value is not None and value >= 0 else None


def _randomized(row: dict[str, Any]) -> bool:
    from runtime_config import RANDOMIZED_ALGORITHMS

    return row.get("algorithm_id") in RANDOMIZED_ALGORITHMS


def _run_type(row: dict[str, Any]) -> str:
    if row.get("algorithm_id") == "auto-policy":
        return "policy"
    return "randomized" if _randomized(row) else "deterministic"


def _instance_best(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_instance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _valid(row):
            by_instance[str(row["instance_uid"])].append(row)
    references: dict[str, dict[str, Any]] = {}
    for uid, candidates in by_instance.items():
        best = min(candidates, key=lambda row: float(row["makespan"]))
        optimum_values = [
            value for row in candidates
            if (value := _certified_optimum(row)) is not None
        ]
        if len(set(optimum_values)) > 1:
            raise ValueError(f"{uid}: conflicting certified optimum values")
        optimum = min(optimum_values, default=None)
        if optimum is not None and optimum > float(best["makespan"]):
            raise ValueError(f"{uid}: certified optimum exceeds a feasible makespan")
        references[uid] = {
            "best_known_feasible": float(best["makespan"]),
            "best_algorithm": best["algorithm_id"],
            "certified_optimum": optimum,
            "certified_optimum_source": next((
                row["certified_optimum_source"] for row in candidates
                if _certified_optimum(row) is not None
            ), None),
        }
    return references


def _trial_quality(
    rows: list[dict[str, Any]], references: dict[str, dict[str, Any]]
) -> dict[int, dict[str, float | None]]:
    result = {}
    for index, row in enumerate(rows):
        ref = references.get(str(row["instance_uid"]))
        score = _number(row.get("makespan")) if _valid(row) else None
        best = ref["best_known_feasible"] if ref else None
        optimum = ref["certified_optimum"] if ref else None
        result[index] = {
            "ratio_to_best_known": score / best if score is not None and best else None,
            "ratio_to_certified_optimum": (
                score / optimum if score is not None and optimum else None
            ),
            "relative_difference_from_optimum": (
                (score - optimum) / optimum
                if score is not None and optimum and optimum > 0 else None
            ),
        }
    return result


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = len(rows)
    valid = [row for row in rows if _valid(row)]
    scores = [float(row["makespan"]) for row in valid]
    wall = [value for row in rows if (value := _number(row.get("wall_seconds"))) is not None]
    cpu = [
        value for row in rows
        if (value := _number(row.get("child_process_tree_cpu_seconds"))) is not None
    ]
    memory = [
        value for row in rows
        if (value := _number(row.get("peak_process_tree_rss_bytes"))) is not None
    ]
    valid_wall = [
        value for row in valid
        if (value := _number(row.get("wall_seconds"))) is not None
    ]
    valid_cpu = [
        value for row in valid
        if (value := _number(row.get("child_process_tree_cpu_seconds"))) is not None
    ]
    valid_memory = [
        value for row in valid
        if (value := _number(row.get("peak_process_tree_rss_bytes"))) is not None
    ]
    timed_out = sum(
        row.get("timeout_status") is True
        or str(row.get("trial_status", "")).startswith("TIMEOUT")
        for row in rows
    )
    errors = sum(row.get("trial_status") == "ERROR" for row in rows)
    certified = sum(_certified_optimum(row) is not None for row in rows)
    return {
        "attempted_trials": attempted,
        "attempted_instances": len({str(row["instance_uid"]) for row in rows}),
        "valid_feasible_solutions": len(valid),
        "officially_validated_solutions": sum(
            row.get("official_validated") is True for row in valid
        ),
        "official_validation_failure_count": sum(
            row.get("official_validation_outcome") in {"TIMEOUT", "INVALID", "ERROR"}
            for row in rows
        ),
        "internally_validated_solutions": sum(
            row.get("validation_level") == "internal_cpp" for row in valid
        ),
        "certified_optimal_solutions": certified,
        "feasible_solution_rate": len(valid) / attempted if attempted else None,
        "timeout_rate": timed_out / attempted if attempted else None,
        "error_rate": errors / attempted if attempted else None,
        "invalid_solution_count": sum(
            row.get("trial_status") == "INVALID_SOLUTION" for row in rows
        ),
        "median_makespan": _median(scores),
        "mean_makespan": _mean(scores),
        "median_wall_seconds": _median(wall),
        "mean_wall_seconds": _mean(wall),
        "median_cpu_seconds": _median(cpu),
        "mean_cpu_seconds": _mean(cpu),
        "median_peak_memory_bytes": _median(memory),
        "mean_peak_memory_bytes": _mean(memory),
        "median_valid_wall_seconds": _median(valid_wall),
        "mean_valid_wall_seconds": _mean(valid_wall),
        "median_valid_cpu_seconds": _median(valid_cpu),
        "median_valid_peak_memory_bytes": _median(valid_memory),
        "valid_solutions_per_wall_second": (
            len(valid) / sum(wall) if wall and sum(wall) > 0 else None
        ),
        "measurement_denominators": {
            "feasibility_timeout_error_rates": attempted,
            "makespan": len(scores),
            "wall_seconds": len(wall),
            "cpu_seconds": len(cpu),
            "peak_memory_bytes": len(memory),
            "valid_wall_seconds": len(valid_wall),
            "valid_cpu_seconds": len(valid_cpu),
            "valid_peak_memory_bytes": len(valid_memory),
        },
    }


def _algorithm_summaries(
    rows: list[dict[str, Any]],
    references: dict[str, dict[str, Any]],
    quality: dict[int, dict[str, float | None]],
) -> list[dict[str, Any]]:
    ids = sorted({str(row["algorithm_id"]) for row in rows})
    summaries = []
    for algorithm in ids:
        indexes = [
            index for index, row in enumerate(rows)
            if row["algorithm_id"] == algorithm
        ]
        selected = [rows[index] for index in indexes]
        valid = [row for row in selected if _valid(row)]
        best_per_instance: dict[str, float] = {}
        for row in valid:
            uid = str(row["instance_uid"])
            score = float(row["makespan"])
            best_per_instance[uid] = min(best_per_instance.get(uid, score), score)
        ratios_best = [
            score / references[uid]["best_known_feasible"]
            for uid, score in best_per_instance.items()
            if uid in references and references[uid]["best_known_feasible"] > 0
        ]
        ratios_optimum = [
            score / references[uid]["certified_optimum"]
            for uid, score in best_per_instance.items()
            if uid in references and references[uid]["certified_optimum"] is not None
            and references[uid]["certified_optimum"] > 0
        ]
        exact_differences = [
            score - references[uid]["certified_optimum"]
            for uid, score in best_per_instance.items()
            if uid in references
            and references[uid]["certified_optimum"] is not None
        ]
        relative_optimum_differences = [
            difference / references[uid]["certified_optimum"]
            for uid, score in best_per_instance.items()
            if uid in references
            and references[uid]["certified_optimum"] is not None
            for difference in [
                score - references[uid]["certified_optimum"]
            ]
            if references[uid]["certified_optimum"] > 0
        ]
        qualities = [quality[index]["ratio_to_best_known"] for index in indexes]
        qualities = [float(value) for value in qualities if value is not None]
        base = _summarize(selected)
        base.update({
            "algorithm_id": algorithm,
            "median_ratio_to_best_known_feasible": _median(ratios_best),
            "mean_ratio_to_best_known_feasible": _mean(ratios_best),
            "geometric_mean_ratio_to_best_known_feasible": _geometric_mean(ratios_best),
            "worst_ratio_to_best_known_feasible": max(ratios_best, default=None),
            "p95_ratio_to_best_known_feasible": _percentile(ratios_best, 0.95),
            "certified_optimum_comparison_instance_count": len(exact_differences),
            "median_ratio_to_certified_optimum": _median(ratios_optimum),
            "mean_ratio_to_certified_optimum": _mean(ratios_optimum),
            "exact_agreement_instance_count": sum(
                difference == 0 for difference in exact_differences
            ),
            "median_additive_difference_from_optimum": _median(exact_differences),
            "mean_additive_difference_from_optimum": _mean(exact_differences),
            "median_relative_difference_from_optimum": _median(
                relative_optimum_differences
            ),
            "mean_relative_difference_from_optimum": _mean(
                relative_optimum_differences
            ),
            "median_trial_ratio_to_best_known": _median(qualities),
            "deterministic": bool(selected) and all(
                _run_type(row) == "deterministic" for row in selected
            ),
            "randomized": any(_randomized(row) for row in selected),
            "policy": bool(selected) and all(
                _run_type(row) == "policy" for row in selected
            ),
            "per_instance_best_run_ratio_denominator": len(ratios_best),
            "ratio_instance_denominator": len(ratios_best),
        })
        summaries.append(base)
    return summaries


def _tier_summaries(
    rows: list[dict[str, Any]],
    quality: dict[int, dict[str, float | None]],
    references: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for index, row in enumerate(rows):
        grouped[_tier(row)][str(row["algorithm_id"])].append(index)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for tier in ("LIGHT", "MEDIUM", "HEAVY", "UNKNOWN"):
        algorithms = grouped.get(tier, {})
        result[tier] = {}
        for algorithm, indexes in sorted(algorithms.items()):
            selected = [rows[index] for index in indexes]
            summary = _summarize(selected)
            best_for_instance: dict[str, float] = {}
            for index in indexes:
                row = rows[index]
                if not _valid(row):
                    continue
                uid = str(row["instance_uid"])
                score = float(row["makespan"])
                best_for_instance[uid] = min(best_for_instance.get(uid, score), score)
            ratios = [
                score / references[uid]["best_known_feasible"]
                for uid, score in best_for_instance.items()
                if uid in references and references[uid]["best_known_feasible"] > 0
            ]
            summary["median_ratio_to_best_known_feasible"] = _median(ratios)
            summary["mean_ratio_to_best_known_feasible"] = _mean(ratios)
            summary["geometric_mean_ratio_to_best_known_feasible"] = (
                _geometric_mean(ratios)
            )
            summary["quality_ratio_trial_denominator"] = len(ratios)
            summary["valid_instance_coverage"] = len(best_for_instance)
            summary["instance_coverage_rate"] = (
                len(best_for_instance) / summary["attempted_instances"]
                if summary["attempted_instances"] else None
            )
            result[tier][algorithm] = summary
    return result


def _per_instance_ratio_stats(
    rows: list[dict[str, Any]], references: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    best_by_instance: dict[str, float] = {}
    for row in rows:
        if not _valid(row):
            continue
        uid = str(row["instance_uid"])
        score = float(row["makespan"])
        best_by_instance[uid] = min(best_by_instance.get(uid, score), score)
    ratios = [
        score / references[uid]["best_known_feasible"]
        for uid, score in best_by_instance.items()
        if uid in references and references[uid]["best_known_feasible"] > 0
    ]
    return {
        "median_ratio_to_best_known_feasible": _median(ratios),
        "mean_ratio_to_best_known_feasible": _mean(ratios),
        "geometric_mean_ratio_to_best_known_feasible": _geometric_mean(ratios),
        "ratio_instance_denominator": len(ratios),
    }


def _cell(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |"
                 for row in rows)
    return "\n".join(lines)


def _summary_markdown(
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    references: dict[str, dict[str, Any]],
) -> str:
    ranking = sorted(
        summaries,
        key=lambda row: (
            -(row["feasible_solution_rate"] or 0),
            row["geometric_mean_ratio_to_best_known_feasible"]
            if row["geometric_mean_ratio_to_best_known_feasible"] is not None
            else float("inf"),
            row["median_makespan"] if row["median_makespan"] is not None else float("inf"),
        ),
    )
    lines = [
        "# Benchmark summary",
        "",
        f"- Trial records: {len(rows)}",
        f"- Instances: {len({str(row['instance_uid']) for row in rows})}",
        f"- Algorithms / policies observed: {len(summaries)}",
        f"- Instances with at least one valid candidate: {len(references)}",
        "",
        "Quality ranking is lexicographic: feasible-solution rate, then geometric "
        "mean ratio to the best validated feasible result per instance, then "
        "median makespan. Invalid outputs are never scored. A timeout with a "
        "validated incumbent is feasible for quality and remains a timeout in "
        "reliability metrics. Missing measurements are omitted from that metric "
        "and reported with denominators in `report-metadata.json`.",
        "",
        "The best feasible value is an experiment-relative reference, not an "
        "optimum. Certified-optimum comparisons are separate and are included "
        "only when the input trial record explicitly carries a valid "
        "`optimality_certified` reference.",
        "",
        _markdown_table(
            ["Rank", "Algorithm ID", "Feasible", "Valid / attempted",
             "Ratio instances", "Median / mean / GM ratio to best feasible",
             "Worst / p95 ratio",
             "Median makespan", "Certified optima", "Exact agreements"],
            [[index + 1, row["algorithm_id"],
              f"{row['feasible_solution_rate']:.3f}" if row["feasible_solution_rate"] is not None else "n/a",
              f"{row['valid_feasible_solutions']} / {row['attempted_trials']}",
              row["ratio_instance_denominator"],
              " / ".join(
                  f"{row[key]:.4f}" if row[key] is not None else "n/a"
                  for key in (
                      "median_ratio_to_best_known_feasible",
                      "mean_ratio_to_best_known_feasible",
                      "geometric_mean_ratio_to_best_known_feasible",
                  )
              ),
              " / ".join(
                  f"{row[key]:.4f}" if row[key] is not None else "n/a"
                  for key in (
                      "worst_ratio_to_best_known_feasible",
                      "p95_ratio_to_best_known_feasible",
                  )
              ),
              row["median_makespan"], row["certified_optimal_solutions"],
              row["exact_agreement_instance_count"]]
             for index, row in enumerate(ranking)],
        ),
        "",
        "## Deterministic, randomized, and policy runs",
        "",
        _markdown_table(
            ["Run type", "Valid / attempted", "Feasible rate", "Ratio instances",
             "Median ratio", "Mean ratio", "Geometric mean ratio"],
            [[kind,
              f"{summary['valid_feasible_solutions']} / {summary['attempted_trials']}",
              summary["feasible_solution_rate"],
              ratios["ratio_instance_denominator"],
              ratios["median_ratio_to_best_known_feasible"],
              ratios["mean_ratio_to_best_known_feasible"],
              ratios["geometric_mean_ratio_to_best_known_feasible"]]
             for kind in ("deterministic", "randomized", "policy")
             for selected in [[row for row in rows if _run_type(row) == kind]]
             for summary in [_summarize(selected)]
             for ratios in [_per_instance_ratio_stats(selected, references)]],
        ),
        "",
        "## Runtime and resource ranking",
        "",
        "These are separate metrics, not a composite score. Runtime and memory "
        "rankings order only algorithms with valid solutions by their median "
        "resource use on valid trials; all-attempt resource medians and timeout "
        "rates remain visible alongside the ranks.",
        "",
        _markdown_table(
            ["Algorithm ID", "Valid / attempted", "Feasible rate",
             "Median valid wall (s)", "Mean valid wall (s)",
             "Median valid CPU (s)", "Median valid peak RSS (bytes)",
             "All-attempt median wall (s)", "Timeout rate", "Valid / wall second"],
            [[row["algorithm_id"],
              f"{row['valid_feasible_solutions']} / {row['attempted_trials']}",
              row["feasible_solution_rate"], row["median_valid_wall_seconds"],
              row["mean_valid_wall_seconds"],
              row["median_valid_cpu_seconds"], row["median_valid_peak_memory_bytes"],
              row["median_wall_seconds"],
              row["timeout_rate"], row["valid_solutions_per_wall_second"]]
             for row in sorted(summaries, key=lambda item: (
                 item["median_valid_wall_seconds"]
                 if item["median_valid_wall_seconds"] is not None
                 else float("inf")
             ))],
        ),
        "",
        "## Quality versus runtime and memory",
        "",
        "See `quality-vs-runtime.svg`, `quality-vs-memory.svg`, and "
        "`runtime-distribution.svg` (median and interquartile/range boxes). "
        "Points include only validated feasible "
        "trial records. Resource distributions include all attempts with "
        "available measurements.",
        "",
        "## Per-tier and scalability views",
        "",
        "Tier reports are generated for LIGHT, MEDIUM, HEAVY, and UNKNOWN. "
        "Scalability plots use recorded `estimated_anchor_count` when present; "
        "otherwise size-by-tier summaries remain the only supported view. "
        "Instance tiers are workload classifications, not quality guarantees.",
        "",
        "## Missing and optimality data",
        "",
        f"- Certified optimum comparisons available: "
        f"{sum(ref['certified_optimum'] is not None for ref in references.values())}.",
        "- Optimality-gap plot: generated only if a trial record provides a "
        "certified optimum or mathematically validated lower-bound gap.",
        "- No invalid or missing solution is assigned a makespan of zero.",
        "",
    ]
    return "\n".join(lines)


def _svg_scatter(
    rows: list[dict[str, Any]],
    quality: dict[int, dict[str, float | None]],
    x_field: str,
    x_label: str,
    filename: str,
    y_field: str = "quality",
    y_label: str = "Ratio to best feasible (lower is better)",
) -> str:
    points = []
    for index, row in enumerate(rows):
        if not _valid(row):
            continue
        x = _number(row.get(x_field))
        y = (
            quality[index]["ratio_to_best_known"]
            if y_field == "quality" else _number(row.get(y_field))
        )
        if x is not None and y is not None:
            points.append((x, float(y), str(row["algorithm_id"])))
    width, height = 840, 520
    left, right, top, bottom = 80, 30, 55, 75
    x_max = max((point[0] for point in points), default=1) or 1
    y_max = max((point[1] for point in points), default=1) or 1
    x_min = min((point[0] for point in points), default=0)
    if x_min == x_max:
        if x_min > 0:
            x_min = max(0, x_min - 1)
        else:
            x_max = 1
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
              "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")
    algorithms = sorted({point[2] for point in points})
    color_map = {algorithm: colors[index % len(colors)]
                 for index, algorithm in enumerate(algorithms)}

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (width - left - right)

    def sy(value: float) -> float:
        return height - bottom - value / y_max * (height - top - bottom)

    content = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<rect width='100%' height='100%' fill='white'/>",
        f"<text x='{left}' y='28' font-family='sans-serif' font-size='18'>"
        f"{html.escape(filename.replace('-', ' ').replace('.svg', '').title())}</text>",
        f"<path d='M {left} {top} V {height-bottom} H {width-right}' "
        "fill='none' stroke='#333'/>",
        f"<text x='{width/2}' y='{height-20}' text-anchor='middle' "
        f"font-family='sans-serif'>{html.escape(x_label)}</text>",
        f"<text x='18' y='{height/2}' transform='rotate(-90 18 {height/2})' "
        f"text-anchor='middle' font-family='sans-serif'>{html.escape(y_label)}</text>",
    ]
    if not points:
        content.append(
            f"<text x='{width/2}' y='{height/2}' text-anchor='middle' "
            "font-family='sans-serif'>No validated feasible points with this measurement</text>"
        )
    for x, y, algorithm in points:
        content.append(
            f"<circle cx='{sx(x):.2f}' cy='{sy(y):.2f}' r='4' "
            f"fill='{color_map[algorithm]}'><title>{html.escape(algorithm)}: "
            f"x={x:g}, ratio={y:.5g}</title></circle>"
        )
    legend_y = 48
    for index, algorithm in enumerate(algorithms):
        x = left + (index % 4) * 190
        y = legend_y + (index // 4) * 18
        content.append(
            f"<circle cx='{x}' cy='{y}' r='4' fill='{color_map[algorithm]}'/>"
            f"<text x='{x+9}' y='{y+4}' font-family='sans-serif' "
            f"font-size='11'>{html.escape(algorithm)}</text>"
        )
    content.append("</svg>")
    return "\n".join(content) + "\n"


def _runtime_svg(rows: list[dict[str, Any]]) -> str:
    by_algorithm: dict[str, list[float]] = defaultdict(list)
    timeouts: dict[str, int] = defaultdict(int)
    for row in rows:
        runtime = _number(row.get("wall_seconds"))
        algorithm = str(row["algorithm_id"])
        if runtime is not None:
            by_algorithm[algorithm].append(runtime)
        if str(row.get("trial_status", "")).startswith("TIMEOUT"):
            timeouts[algorithm] += 1
    ids = sorted(set(by_algorithm) | set(timeouts))
    width, height = 900, max(180, 80 + 42 * len(ids))
    max_value = max((max(values) for values in by_algorithm.values()), default=1) or 1
    content = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        "<rect width='100%' height='100%' fill='white'/>",
        "<text x='24' y='28' font-family='sans-serif' font-size='18'>"
        "Runtime distributions and timeout counts</text>",
    ]
    for index, algorithm in enumerate(ids):
        y = 60 + index * 42
        values = by_algorithm.get(algorithm, [])
        median = _median(values)
        content.append(
            f"<text x='24' y='{y+5}' font-family='sans-serif' font-size='12'>"
            f"{html.escape(algorithm)}</text>"
        )
        if median is not None:
            minimum = min(values)
            maximum = max(values)
            first_quartile = _percentile(values, 0.25)
            third_quartile = _percentile(values, 0.75)
            scale = lambda value: 200 + value / max_value * 520
            x_min, x_max = scale(minimum), scale(maximum)
            x_q1, x_q3, x_median = (
                scale(first_quartile), scale(third_quartile), scale(median)
            )
            content.append(
                f"<path d='M {x_min:.1f} {y} H {x_max:.1f} M {x_min:.1f} {y-5} V {y+5} "
                f"M {x_max:.1f} {y-5} V {y+5}' stroke='#4c78a8'/>"
                f"<rect x='{x_q1:.1f}' y='{y-8}' width='{max(1, x_q3-x_q1):.1f}' "
                f"height='16' fill='#9ecae9' stroke='#4c78a8'/>"
                f"<path d='M {x_median:.1f} {y-9} V {y+9}' stroke='#102a43' "
                f"stroke-width='2'/>"
                f"<text x='730' y='{y+5}' font-family='sans-serif' font-size='12'>"
                f"median {median:.3g}s, Q1-Q3 {first_quartile:.3g}-{third_quartile:.3g}s "
                f"(n={len(values)}); timeouts={timeouts[algorithm]}</text>"
            )
        else:
            content.append(
                f"<text x='200' y='{y+5}' font-family='sans-serif' font-size='12'>"
                f"no wall-time measurements; timeouts={timeouts[algorithm]}</text>"
            )
    content.append("</svg>")
    return "\n".join(content) + "\n"


def _validated_optimality_gap(row: dict[str, Any]) -> tuple[str, float] | None:
    if not _valid(row):
        return None
    score = _number(row.get("makespan"))
    if score is None:
        return None
    if (
        row.get("optimality_certified") is True
        and row.get("formulation_exact_for_original_objective") is True
        and row.get("certified_solution_validated") is True
        and row.get("certified_objective_matched") is True
    ):
        optimum = _number(row.get("certified_optimum"))
        source = row.get("certified_optimum_source")
        if optimum is not None and optimum > 0 and isinstance(source, str) and source.strip():
            if optimum > score:
                raise ValueError("certified optimum exceeds validated feasible makespan")
            return "certified_optimum", (score - optimum) / optimum
    if (
        row.get("validated_lower_bound_valid") is True
        and isinstance(row.get("validated_lower_bound_source"), str)
        and row["validated_lower_bound_source"].strip()
    ):
        lower_bound = _number(row.get("validated_lower_bound"))
        if lower_bound is not None and lower_bound > 0:
            if score < lower_bound:
                raise ValueError("validated lower bound exceeds feasible makespan")
            return "validated_lower_bound", (score - lower_bound) / lower_bound
    return None


def build_artifacts(
    rows: list[dict[str, Any]], input_path: Path
) -> dict[str, str]:
    references = _instance_best(rows)
    quality = _trial_quality(rows, references)
    summaries = _algorithm_summaries(rows, references, quality)
    tiers = _tier_summaries(rows, quality, references)
    algorithms = sorted({str(row["algorithm_id"]) for row in rows})
    instances = sorted({str(row["instance_uid"]) for row in rows})
    if len({_safe(uid) for uid in instances}) != len(instances):
        raise ValueError("instance IDs collide after report filename normalization")
    if len({_safe(algorithm) for algorithm in algorithms}) != len(algorithms):
        raise ValueError("algorithm IDs collide after report filename normalization")
    artifacts: dict[str, str] = {}

    csv_fields = list(dict.fromkeys(
        field for row in rows for field in row
    ))
    from io import StringIO

    csv_buffer = StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=csv_fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _cell(row.get(field)) for field in csv_fields})
    artifacts["benchmark.csv"] = csv_buffer.getvalue()
    artifacts["benchmark.jsonl"] = "".join(
        json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows
    )
    artifacts["report-metadata.json"] = json.dumps({
        "schema_version": 1,
        "raw_trials": str(input_path.resolve()),
        "record_count": len(rows),
        "quality_definition": (
            "valid trial makespan divided by lowest valid makespan on the same "
            "instance across this experiment"
        ),
        "ranking_policy": [
            "feasible-solution rate descending",
            "geometric mean of per-instance best-run quality ratios ascending",
            "median valid makespan ascending",
        ],
        "invalid_solution_handling": "excluded from score and quality ratios",
        "metric_definitions": {
            "feasible_solution_rate": "valid feasible trial records / attempted trial records",
            "timeout_rate": "timeout trial records, including timeout with incumbent / attempted trials",
            "per_algorithm_quality_ratios": "best valid run of each algorithm per instance; denominator is instances with a positive best-known makespan",
            "ratio_to_best_known_feasible": "algorithm best makespan / best validated feasible makespan over this experiment for the instance",
            "certified_optimum_comparison": "reported only from validated, objective-matched, source-attributed exact proofs",
            "high_percentile": "linearly interpolated 95th percentile",
            "valid_solutions_per_wall_second": "valid feasible trials / sum of measured wall seconds over all attempts",
        },
        "validated_solution_levels": {
            "official": sum(
                _valid(row) and row.get("validation_level") == "official"
                for row in rows
            ),
            "internal_cpp": sum(
                _valid(row) and row.get("validation_level") == "internal_cpp"
                for row in rows
            ),
        },
        "timeout_handling": (
            "counted as timeout even when a validated incumbent is retained; "
            "such incumbent remains eligible for quality"
        ),
        "missing_measurement_handling": "omitted from metric; denominator recorded",
        "randomized_algorithm_ids": sorted(
            __import__("runtime_config").RANDOMIZED_ALGORITHMS
        ),
        "algorithms_observed": algorithms,
        "instances_observed": instances,
        "instance_best_references": references,
        "summary_statistics": summaries,
        "tier_summaries": tiers,
        "run_type_summaries": {
            kind: {
                **_summarize(selected),
                **_per_instance_ratio_stats(selected, references),
            }
            for kind in ("deterministic", "randomized", "policy")
            for selected in [[row for row in rows if _run_type(row) == kind]]
        },
    }, indent=2, sort_keys=True, allow_nan=False) + "\n"
    artifacts["benchmark-summary.md"] = _summary_markdown(rows, summaries, references)

    best_fields = (
        "instance_uid", "tier", "status", "best_known_feasible_makespan",
        "algorithm_id", "actual_producing_algorithm", "candidate_source",
        "seed", "repetition", "input_path", "output_solution_path",
        "validation_level", "wall_seconds", "child_process_tree_cpu_seconds",
        "peak_process_tree_rss_bytes", "trial_status",
    )
    best_lines = ["\t".join(best_fields)]
    for uid in sorted({str(row["instance_uid"]) for row in rows}):
        instance_rows = [row for row in rows if str(row["instance_uid"]) == uid]
        valid_rows = [row for row in instance_rows if _valid(row)]
        valid_rows.sort(key=lambda row: (
            float(row["makespan"]),
            str(row["algorithm_id"]),
            int(row.get("repetition") or 0),
            str(row.get("seed") if row.get("seed") is not None else ""),
            str(row.get("run_id") or ""),
        ))
        if valid_rows:
            best = valid_rows[0]
            values = [
                uid, _tier(best), "BEST_KNOWN_FEASIBLE", best["makespan"],
                best["algorithm_id"], best.get("actual_producing_algorithm"),
                best.get("candidate_source"), best.get("seed"),
                best.get("repetition"), best.get("input_path"),
                best.get("output_solution_path"), best.get("validation_level"),
                best.get("wall_seconds"),
                best.get("child_process_tree_cpu_seconds"),
                best.get("peak_process_tree_rss_bytes"),
                best.get("trial_status"),
            ]
        else:
            row = instance_rows[0]
            values = [
                uid, _tier(row), "NO_VALID_SOLUTION", None, None, None, None,
                None, None, row.get("input_path"), None, None, None, None, None,
                ",".join(sorted({
                    str(item.get("trial_status", item.get("status", "ERROR")))
                    for item in instance_rows
                })),
            ]
        best_lines.append("\t".join(_cell(value) for value in values))
    artifacts["best-heuristic-per-instance.tsv"] = "\n".join(best_lines) + "\n"

    tier_fields = (
        "tier", "rank", "winner", "algorithm_id", "attempted_trials",
        "attempted_instances", "valid_feasible_solutions",
        "valid_instance_coverage", "instance_coverage_rate",
        "feasible_solution_rate",
        "median_ratio_to_best_known_feasible",
        "geometric_mean_ratio_to_best_known_feasible",
        "timeout_rate", "error_rate", "median_valid_wall_seconds",
        "median_valid_peak_memory_bytes",
    )
    tier_lines = ["\t".join(tier_fields)]
    for tier in ("LIGHT", "MEDIUM", "HEAVY"):
        tier_algorithms = tiers.get(tier, {})
        ordered = sorted(tier_algorithms.items(), key=lambda item: (
            -(item[1]["feasible_solution_rate"] or 0),
            item[1]["geometric_mean_ratio_to_best_known_feasible"]
            if item[1]["geometric_mean_ratio_to_best_known_feasible"] is not None
            else float("inf"),
            item[1]["median_ratio_to_best_known_feasible"]
            if item[1]["median_ratio_to_best_known_feasible"] is not None
            else float("inf"),
            item[1]["timeout_rate"]
            if item[1]["timeout_rate"] is not None else float("inf"),
            item[1]["error_rate"]
            if item[1]["error_rate"] is not None else float("inf"),
            item[0],
        ))
        for rank, (algorithm, summary) in enumerate(ordered, 1):
            tier_lines.append("\t".join(_cell(value) for value in [
                tier, rank, rank == 1, algorithm,
                summary["attempted_trials"], summary["attempted_instances"],
                summary["valid_feasible_solutions"],
                summary["valid_instance_coverage"], summary["instance_coverage_rate"],
                summary["feasible_solution_rate"],
                summary["median_ratio_to_best_known_feasible"],
                summary["geometric_mean_ratio_to_best_known_feasible"],
                summary["timeout_rate"], summary["error_rate"],
                summary["median_valid_wall_seconds"],
                summary["median_valid_peak_memory_bytes"],
            ]))
    artifacts["best-heuristic-by-tier.tsv"] = "\n".join(tier_lines) + "\n"

    matrix_rows = []
    for uid in instances:
        selected = [row for row in rows if str(row["instance_uid"]) == uid]
        cells = []
        for algorithm in algorithms:
            alg_rows = [row for row in selected if row["algorithm_id"] == algorithm]
            valid_scores = [float(row["makespan"]) for row in alg_rows if _valid(row)]
            if valid_scores:
                cells.append(str(min(valid_scores)))
            elif alg_rows:
                cells.append("NO_VALID_SOLUTION:" + ",".join(sorted({
                    str(row.get("trial_status", row.get("status", "ERROR")))
                    for row in alg_rows
                })))
            else:
                cells.append("NOT_ATTEMPTED")
        matrix_rows.append([uid, *cells])
    artifacts["comparison-matrix.tsv"] = "\t".join(["instance_uid", *algorithms]) + "\n"
    artifacts["comparison-matrix.tsv"] += "".join(
        "\t".join(map(str, row)) + "\n" for row in matrix_rows
    )

    quality_rank = sorted(
        summaries,
        key=lambda row: (
            -(row["feasible_solution_rate"] or 0),
            row["geometric_mean_ratio_to_best_known_feasible"]
            if row["geometric_mean_ratio_to_best_known_feasible"] is not None
            else float("inf"),
            row["median_makespan"] if row["median_makespan"] is not None
            else float("inf"),
        ),
    )
    quality_fields = (
        "rank", "algorithm_id", "attempted_trials", "valid_feasible_solutions",
        "officially_validated_solutions",
        "certified_optimal_solutions", "feasible_solution_rate", "timeout_rate",
        "error_rate", "median_makespan", "mean_makespan",
        "median_ratio_to_best_known_feasible", "mean_ratio_to_best_known_feasible",
        "geometric_mean_ratio_to_best_known_feasible",
        "worst_ratio_to_best_known_feasible", "p95_ratio_to_best_known_feasible",
        "certified_optimum_comparison_instance_count",
        "median_ratio_to_certified_optimum",
        "exact_agreement_instance_count",
        "median_additive_difference_from_optimum",
        "mean_additive_difference_from_optimum",
        "median_relative_difference_from_optimum",
        "mean_relative_difference_from_optimum",
        "ratio_instance_denominator",
    )
    artifacts["quality-ranking.tsv"] = "\t".join(quality_fields) + "\n"
    artifacts["quality-ranking.tsv"] += "".join(
        "\t".join(_cell(value) for value in [rank, *[row.get(field) for field in quality_fields[1:]]]) + "\n"
        for rank, row in enumerate(quality_rank, 1)
    )
    resource_fields = (
        "rank_by_median_valid_wall", "algorithm_id", "attempted_trials",
        "valid_feasible_solutions", "feasible_solution_rate", "invalid_solution_count",
        "median_valid_wall_seconds", "mean_valid_wall_seconds",
        "median_valid_cpu_seconds", "median_valid_peak_memory_bytes",
        "median_wall_seconds", "mean_wall_seconds", "median_cpu_seconds",
        "mean_cpu_seconds", "median_peak_memory_bytes", "mean_peak_memory_bytes",
        "timeout_rate", "valid_solutions_per_wall_second",
    )
    resource_rank = sorted(summaries, key=lambda row: (
        row["median_valid_wall_seconds"]
        if row["median_valid_wall_seconds"] is not None
        else float("inf")
    ))
    artifacts["resource-ranking.tsv"] = "\t".join(resource_fields) + "\n"
    artifacts["resource-ranking.tsv"] += "".join(
        "\t".join(_cell(value) for value in [
            rank, *[row.get(field) for field in resource_fields[1:]]
        ]) + "\n"
        for rank, row in enumerate(resource_rank, 1)
    )
    memory_fields = (
        "rank_by_median_valid_peak_memory", "algorithm_id", "attempted_trials",
        "valid_feasible_solutions", "feasible_solution_rate", "invalid_solution_count",
        "median_valid_peak_memory_bytes",
        "median_peak_memory_bytes", "mean_peak_memory_bytes",
        "median_wall_seconds", "median_cpu_seconds", "timeout_rate",
    )
    memory_rank = sorted(summaries, key=lambda row: (
        row["median_valid_peak_memory_bytes"]
        if row["median_valid_peak_memory_bytes"] is not None else float("inf")
    ))
    artifacts["memory-ranking.tsv"] = "\t".join(memory_fields) + "\n"
    artifacts["memory-ranking.tsv"] += "".join(
        "\t".join(_cell(value) for value in [
            rank, *[row.get(field) for field in memory_fields[1:]]
        ]) + "\n"
        for rank, row in enumerate(memory_rank, 1)
    )
    artifacts["quality-vs-runtime.svg"] = _svg_scatter(
        rows, quality, "wall_seconds", "Wall time (seconds)", "quality-vs-runtime.svg"
    )
    artifacts["quality-vs-memory.svg"] = _svg_scatter(
        rows, quality, "peak_process_tree_rss_bytes",
        "Peak sampled process-tree RSS (bytes)", "quality-vs-memory.svg"
    )
    if any(_number(row.get("estimated_anchor_count")) is not None for row in rows):
        artifacts["runtime-vs-instance-size.svg"] = _svg_scatter(
            rows, quality, "estimated_anchor_count",
            "Estimated anchor count (input-size proxy)",
            "runtime-vs-instance-size.svg",
            y_field="wall_seconds",
            y_label="Wall time (seconds; lower is better)",
        )
        artifacts["quality-vs-instance-size.svg"] = _svg_scatter(
            rows, quality, "estimated_anchor_count",
            "Estimated anchor count (input-size proxy)",
            "quality-vs-instance-size.svg",
        )
    artifacts["runtime-distribution.svg"] = _runtime_svg(rows)

    instance_uids = sorted({str(row["instance_uid"]) for row in rows})
    for uid in instance_uids:
        selected = [row for row in rows if str(row["instance_uid"]) == uid]
        valid = [row for row in selected if _valid(row)]
        instance_reference = references.get(uid, {})
        best = instance_reference.get("best_known_feasible")
        optimum = instance_reference.get("certified_optimum")
        algorithm_rows = []
        for algorithm in algorithms:
            algorithm_valid = [
                row for row in selected
                if row["algorithm_id"] == algorithm and _valid(row)
            ]
            algorithm_best = min(
                (float(row["makespan"]) for row in algorithm_valid),
                default=None,
            )
            difference = (
                algorithm_best - optimum
                if algorithm_best is not None and optimum is not None else None
            )
            algorithm_rows.append([
                algorithm,
                sum(row["algorithm_id"] == algorithm for row in selected),
                len(algorithm_valid),
                algorithm_best,
                algorithm_best / best
                if algorithm_best is not None and best and best > 0 else None,
                algorithm_best / optimum
                if algorithm_best is not None and optimum is not None and optimum > 0
                else None,
                difference,
                difference == 0 if difference is not None else None,
                sum(row["algorithm_id"] == algorithm and
                    str(row.get("trial_status", "")).startswith("TIMEOUT")
                    for row in selected),
                sum(row["algorithm_id"] == algorithm and
                    row.get("trial_status") == "ERROR" for row in selected),
            ])
        content = [
            f"# Instance {uid}", "",
            f"- Tier: {_tier(selected[0])}",
            f"- Attempted trials: {len(selected)}",
            f"- Valid feasible trials: {len(valid)}",
            f"- Best known feasible makespan: {best if best is not None else 'unavailable'}",
            f"- Certified optimum: {optimum if optimum is not None else 'unavailable'}",
            f"- Certified optimum source: {instance_reference.get('certified_optimum_source') or 'unavailable'}",
            f"- Best-feasible additive difference from optimum: "
            f"{best - optimum if best is not None and optimum is not None else 'unavailable'}",
            "",
            _markdown_table(
                ["Algorithm ID", "Attempted", "Valid", "Best makespan",
                 "Ratio to best feasible", "Ratio to certified optimum",
                 "Additive difference from optimum", "Exact agreement",
                 "Timeouts", "Errors"],
                algorithm_rows,
            ), "",
        ]
        artifacts[f"instances/{_safe(uid)}.md"] = "\n".join(content)

    for row in summaries:
        algorithm = row["algorithm_id"]
        selected = [trial for trial in rows if trial["algorithm_id"] == algorithm]
        content = [
            f"# Algorithm {algorithm}", "",
            _markdown_table(
                ["Metric", "Value", "Denominator"],
                [[name, row.get(name), row.get("measurement_denominators", {}).get(denominator)]
                 for name, denominator in (
                     ("attempted_trials", "feasibility_timeout_error_rates"),
                     ("valid_feasible_solutions", "feasibility_timeout_error_rates"),
                     ("feasible_solution_rate", "feasibility_timeout_error_rates"),
                     ("timeout_rate", "feasibility_timeout_error_rates"),
                     ("error_rate", "feasibility_timeout_error_rates"),
                     ("median_makespan", "makespan"),
                     ("mean_makespan", "makespan"),
                     ("median_wall_seconds", "wall_seconds"),
                     ("mean_wall_seconds", "wall_seconds"),
                     ("median_cpu_seconds", "cpu_seconds"),
                     ("median_peak_memory_bytes", "peak_memory_bytes"),
                     ("geometric_mean_ratio_to_best_known_feasible",
                      "per_instance_best_run_ratio_denominator"),
                     ("exact_agreement_instance_count",
                      "certified_optimum_comparison_instance_count"),
                     ("median_additive_difference_from_optimum",
                      "certified_optimum_comparison_instance_count"),
                     ("median_relative_difference_from_optimum",
                      "certified_optimum_comparison_instance_count"),
                 )],
            ),
            "",
            "## Run type",
            "",
            f"- Deterministic registry classification: {_run_type(selected[0]) == 'deterministic' if selected else 'unknown'}",
            f"- Randomized: {bool(selected) and _randomized(selected[0])}",
            f"- Run type: {_run_type(selected[0]) if selected else 'unknown'}",
            f"- Distinct seeds: {len({trial.get('seed') for trial in selected})}",
            "- Per-instance quality uses the best valid repetition for this algorithm; "
            "runtime and reliability use all attempted repetitions.",
            "",
        ]
        artifacts[f"algorithms/{_safe(algorithm)}.md"] = "\n".join(content)

    for tier, by_algorithm in tiers.items():
        artifacts[f"tiers/{tier.lower()}.md"] = "\n".join([
            f"# {tier.title()} tier", "",
            "Tier is an instance workload classification; missing tiers are UNKNOWN.",
            "",
            _markdown_table(
                ["Algorithm ID", "Valid / attempted", "Instance coverage",
                 "Feasible rate",
                 "Median makespan", "Mean makespan", "Ratio instances",
                 "Median / geometric mean ratio to best feasible",
                 "Timeout rate", "Median wall (s)", "Median peak RSS (bytes)"],
                [[algorithm,
                  f"{summary['valid_feasible_solutions']} / {summary['attempted_trials']}",
                  f"{summary['valid_instance_coverage']} / {summary['attempted_instances']}",
                  summary["feasible_solution_rate"], summary["median_makespan"],
                  summary["mean_makespan"],
                  summary["quality_ratio_trial_denominator"],
                  " / ".join(
                      _cell(summary[key]) for key in (
                          "median_ratio_to_best_known_feasible",
                          "geometric_mean_ratio_to_best_known_feasible",
                      )
                  ),
                  summary["timeout_rate"], summary["median_wall_seconds"],
                  summary["median_peak_memory_bytes"]]
                 for algorithm, summary in sorted(by_algorithm.items())],
            ), "",
        ])

    optimality_points: list[tuple[str, str, float]] = []
    for row in rows:
        gap = _validated_optimality_gap(row)
        if gap is not None:
            source_kind, value = gap
            optimality_points.append(
                (str(row["algorithm_id"]), source_kind, value)
            )
    if optimality_points:
        height = 90 + len(optimality_points) * 24
        content = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}">',
            "<rect width='100%' height='100%' fill='white'/>",
            "<text x='20' y='28' font-family='sans-serif' font-size='18'>"
            "Validated relative gaps (certified optimum or validated lower bound)</text>",
        ]
        max_value = max((value for _, _, value in optimality_points), default=1) or 1
        for index, (algorithm, source_kind, value) in enumerate(optimality_points):
            y = 65 + index * 24
            content.append(
                f"<text x='20' y='{y+4}' font-family='sans-serif' font-size='11'>"
                f"{html.escape(algorithm)} ({source_kind})</text><rect x='210' y='{y-7}' "
                f"width='{min(540, 540*value/max_value):.1f}' height='13' fill='#e45756'/>"
                f"<text x='760' y='{y+4}' font-family='sans-serif' font-size='11'>{value:.4g}</text>"
            )
        content.append("</svg>")
        artifacts["optimality-gaps.svg"] = "\n".join(content) + "\n"
    run_types: dict[str, list[dict[str, Any]]] = {
        kind: [row for row in rows if _run_type(row) == kind]
        for kind in ("deterministic", "randomized", "policy")
    }
    artifacts["run-type-ranking.tsv"] = (
        "run_type\tattempted_trials\tvalid_feasible_solutions\t"
        "feasible_solution_rate\tmedian_makespan\tmedian_wall_seconds\t"
        "median_peak_memory_bytes\ttimeout_rate\tmedian_ratio_to_best_known\t"
        "mean_ratio_to_best_known\tgeometric_mean_ratio_to_best_known\t"
        "ratio_instance_denominator\n"
    )
    for kind, selected in run_types.items():
        summary = _summarize(selected)
        ratio_stats = _per_instance_ratio_stats(selected, references)
        artifacts["run-type-ranking.tsv"] += "\t".join(_cell(value) for value in (
            kind, summary["attempted_trials"], summary["valid_feasible_solutions"],
            summary["feasible_solution_rate"], summary["median_makespan"],
            summary["median_wall_seconds"], summary["median_peak_memory_bytes"],
            summary["timeout_rate"], ratio_stats["median_ratio_to_best_known_feasible"],
            ratio_stats["mean_ratio_to_best_known_feasible"],
            ratio_stats["geometric_mean_ratio_to_best_known_feasible"],
            ratio_stats["ratio_instance_denominator"],
        )) + "\n"

    budgets: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        config = row.get("effective_configuration")
        if not isinstance(config, dict):
            continue
        timeout = config.get("effective_per_run_wall_clock_timeout_seconds")
        if timeout is None:
            timeout = config.get("per_instance_timeout_seconds")
        budgets[(timeout, config.get("memory_limit_mib"))].append(row)
    artifacts["budget-comparison.tsv"] = (
        "timeout_seconds\tmemory_limit_mib\talgorithm_id\tvalid_feasible_solutions\t"
        "feasible_solution_rate\tmedian_ratio_to_best_known\tmedian_makespan\n"
    )
    for budget, budget_rows in sorted(budgets.items(), key=lambda item: str(item[0])):
        for algorithm in sorted({str(row["algorithm_id"]) for row in budget_rows}):
            selected = [row for row in budget_rows if row["algorithm_id"] == algorithm]
            valid_scores = [float(row["makespan"]) for row in selected if _valid(row)]
            ratios = []
            best_by_instance: dict[str, float] = {}
            for row in selected:
                if _valid(row):
                    uid = str(row["instance_uid"])
                    value = float(row["makespan"])
                    best_by_instance[uid] = min(best_by_instance.get(uid, value), value)
            for uid, value in best_by_instance.items():
                if uid in references and references[uid]["best_known_feasible"] > 0:
                    ratios.append(value / references[uid]["best_known_feasible"])
            artifacts["budget-comparison.tsv"] += "\t".join(_cell(value) for value in (
                budget[0], budget[1], algorithm, len(valid_scores),
                len(valid_scores) / len(selected) if selected else None,
                _median(ratios), _median(valid_scores),
            )) + "\n"
    return artifacts


def _safe(value: str) -> str:
    import re

    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return clean or "item"


def generate_reports(input_path: Path, output_dir: Path, overwrite: bool = False) -> list[Path]:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    if not input_path.is_file():
        raise ValueError(f"benchmark trial file does not exist: {input_path}")
    if not output_dir.is_dir():
        raise ValueError(f"report output directory does not exist: {output_dir}")
    rows = read_trials(input_path)
    artifacts = build_artifacts(rows, input_path)
    if input_path == output_dir / "benchmark.csv":
        artifacts.pop("benchmark.csv", None)
    paths = [output_dir / relative for relative in artifacts]
    if not overwrite:
        existing = [path for path in paths if path.exists()]
        if existing:
            raise FileExistsError(
                "refusing to overwrite report artifact(s): " +
                ", ".join(str(path) for path in existing[:8])
            )
    for path, content in zip(paths, artifacts.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="raw benchmark.tsv or benchmark.csv")
    parser.add_argument("--output-dir", type=Path,
                        help="default: directory containing --input")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace generated report artifacts")
    args = parser.parse_args()
    output_dir = args.output_dir or args.input.resolve().parent
    try:
        paths = generate_reports(args.input, output_dir, args.overwrite)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"generated {len(paths)} report artifacts in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
