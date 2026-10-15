#!/usr/bin/env python3
"""Estimate instance workload and optionally collect a bounded solver pilot."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from benchmark import run_bounded_process_with_metrics
from runtime_config import ALGORITHMS, ROOT, available_cpu_workers
from solution_metrics import makespan


DEFAULT_THRESHOLDS = ROOT / "config/instance_profiler.json"
PROFILE_COLUMNS = (
    "instance_uid",
    "path",
    "file_bytes",
    "region_cell_count",
    "bounding_box_area",
    "boundary_vertices",
    "hole_count",
    "cutter_cell_count",
    "cutter_width",
    "cutter_height",
    "number_of_cutters",
    "estimated_anchor_count",
    "estimated_coverage_candidate_pairs",
    "estimated_ip_kont_columns_upper_bound",
    "estimated_ip_kont_variables_upper_bound",
    "estimated_ip_kont_constraints_upper_bound",
    "estimated_raster_point_tests",
    "estimated_coordinate_payload_bytes_lower_bound",
    "estimated_total_coverage_memory_bytes",
    "estimated_tier",
    "classification_reason",
    "classification_confidence",
    "threshold_version",
    "selected_algorithm",
    "empirical_status",
    "elapsed_seconds",
    "cpu_seconds",
    "peak_process_tree_rss_bytes",
    "process_tree_rss_sample_count",
    "termination_reason",
    "official_validation_seconds",
    "official_process_tree_cpu_seconds",
    "official_peak_process_tree_rss_bytes",
    "validation_level",
    "makespan",
    "outcome",
)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ring(value: Any, field: str) -> tuple[list[tuple[int, int]], int]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    x_values, y_values = value.get("x"), value.get("y")
    if (not isinstance(x_values, list) or not isinstance(y_values, list) or
            len(x_values) != len(y_values) or len(x_values) < 4 or
            any(not _integer(point) for point in x_values + y_values)):
        raise ValueError(f"{field} must contain matching integer x/y arrays")
    points = list(zip(x_values, y_values))
    if len(set(points)) != len(points):
        raise ValueError(f"{field} has repeated vertices")
    for start, end in zip(points, points[1:] + points[:1]):
        if start == end or (start[0] != end[0] and start[1] != end[1]):
            raise ValueError(f"{field} must have nonzero rectilinear edges")
    double_area = sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(points, points[1:] + points[:1])
    )
    if double_area == 0:
        raise ValueError(f"{field} has zero signed area")
    return points, double_area


def extract_features(path: Path) -> dict[str, Any]:
    """Extract inexpensive geometric features; no raster or coverage map is built."""
    try:
        instance = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read instance {path}: {error}") from error
    if not isinstance(instance, dict):
        raise ValueError("instance root must be an object")
    if instance.get("content_type") != "CGSHOP2027_Instance":
        raise ValueError("unsupported instance content_type")
    uid = instance.get("instance_uid")
    if not isinstance(uid, str) or not uid:
        raise ValueError("instance_uid must be a nonempty string")
    region = instance.get("region_to_cover")
    if not isinstance(region, dict) or not isinstance(region.get("inner_boundaries"), list):
        raise ValueError("region_to_cover and inner_boundaries are required")
    outer, outer_double_area = _ring(region.get("outer_boundary"), "outer_boundary")
    if outer_double_area <= 0:
        raise ValueError("outer_boundary must be counter-clockwise")
    holes: list[list[tuple[int, int]]] = []
    hole_areas: list[int] = []
    for index, value in enumerate(region["inner_boundaries"]):
        hole, double_area = _ring(value, f"inner_boundaries[{index}]")
        if double_area >= 0:
            raise ValueError(f"inner_boundaries[{index}] must be clockwise")
        holes.append(hole)
        hole_areas.append(abs(double_area))
    cutter, cutter_double_area = _ring(instance.get("cutter"), "cutter")
    if cutter_double_area <= 0:
        raise ValueError("cutter must be counter-clockwise")
    cutter_center = instance.get("cutter_center")
    if (not isinstance(cutter_center, list) or len(cutter_center) != 2 or
            any(not _integer(item) for item in cutter_center)):
        raise ValueError("cutter_center must contain two integer coordinates")
    cutters = instance.get("number_of_cutters")
    if not _integer(cutters) or cutters < 1:
        raise ValueError("number_of_cutters must be a positive integer")

    min_x = min(point[0] for point in outer)
    max_x = max(point[0] for point in outer)
    min_y = min(point[1] for point in outer)
    max_y = max(point[1] for point in outer)
    box_area = (max_x - min_x) * (max_y - min_y)
    net_double_area = outer_double_area - sum(hole_areas)
    if net_double_area <= 0 or net_double_area % 2:
        raise ValueError("region has nonpositive or nonintegral orthogonal area")

    cutter_x = [point[0] for point in cutter]
    cutter_y = [point[1] for point in cutter]
    cutter_width = max(cutter_x) - min(cutter_x)
    cutter_height = max(cutter_y) - min(cutter_y)
    region_cells = net_double_area // 2
    cutter_cells = abs(cutter_double_area) // 2
    total_vertices = len(outer) + sum(len(hole) for hole in holes)
    # This bounds ring-edge predicates in one raster scan of the outer box.
    raster_point_tests = box_area * total_vertices
    features = {
        "instance_uid": uid,
        "file_bytes": path.stat().st_size,
        "region_cell_count": region_cells,
        "bounding_box_area": box_area,
        "boundary_vertices": total_vertices,
        "hole_count": len(holes),
        "cutter_cell_count": cutter_cells,
        "cutter_width": cutter_width,
        "cutter_height": cutter_height,
        "number_of_cutters": cutters,
        "estimated_anchor_count": region_cells,
        "estimated_coverage_candidate_pairs": region_cells * cutter_cells,
        "estimated_ip_kont_columns_upper_bound": min(
            max_x - min_x, region_cells
        ),
        "estimated_ip_kont_variables_upper_bound": (
            min(max_x - min_x, region_cells) * cutters
        ),
        "estimated_ip_kont_constraints_upper_bound": (
            min(max_x - min_x, region_cells) + cutters
        ),
        "estimated_raster_point_tests": raster_point_tests,
        "estimated_coordinate_payload_bytes_lower_bound": 8 * (
            region_cells + cutter_cells
        ),
        "estimated_total_coverage_memory_bytes": None,
        "geometry_note": (
            "integer shoelace areas assume valid simple, mutually compatible rings; "
            "full topology validation is intentionally not run during profiling"
        ),
    }
    features["measured_features"] = {
        key: features[key] for key in (
            "file_bytes", "bounding_box_area", "boundary_vertices", "hole_count",
            "cutter_width", "cutter_height", "number_of_cutters",
        )
    }
    features["derived_exact_features"] = {
        "region_cell_count": region_cells,
        "cutter_cell_count": cutter_cells,
    }
    features["estimated_features"] = {
        key: features[key] for key in (
            "estimated_anchor_count", "estimated_coverage_candidate_pairs",
            "estimated_ip_kont_columns_upper_bound",
            "estimated_ip_kont_variables_upper_bound",
            "estimated_ip_kont_constraints_upper_bound",
            "estimated_raster_point_tests",
            "estimated_coordinate_payload_bytes_lower_bound",
            "estimated_total_coverage_memory_bytes",
        )
    }
    return features


def load_thresholds(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read profiler thresholds {path}: {error}") from error
    if not isinstance(config, dict) or set(config) != {
        "threshold_version", "tiers", "automatic_algorithm_by_tier"
    }:
        raise ValueError("profiler config must define threshold_version, tiers, and automatic_algorithm_by_tier")
    if not isinstance(config["threshold_version"], str) or not config["threshold_version"]:
        raise ValueError("threshold_version must be a nonempty string")
    tiers = config["tiers"]
    if not isinstance(tiers, dict) or set(tiers) != {"LIGHT", "MEDIUM"}:
        raise ValueError("tiers must define exactly LIGHT and MEDIUM thresholds")
    previous: tuple[int, int] | None = None
    for name in ("LIGHT", "MEDIUM"):
        values = tiers[name]
        if not isinstance(values, dict) or set(values) != {
            "max_estimated_raster_point_tests", "max_estimated_anchor_count"
        }:
            raise ValueError(f"{name} must define both workload thresholds")
        pair = tuple(values[key] for key in (
            "max_estimated_raster_point_tests", "max_estimated_anchor_count"
        ))
        if any(not _integer(item) or item < 0 for item in pair):
            raise ValueError(f"{name} thresholds must be nonnegative integers")
        if previous and any(current < prior for current, prior in zip(pair, previous)):
            raise ValueError("MEDIUM thresholds must not be lower than LIGHT thresholds")
        previous = pair
    mapping = config["automatic_algorithm_by_tier"]
    if (not isinstance(mapping, dict) or
            set(mapping) != {"LIGHT", "MEDIUM", "HEAVY", "UNKNOWN"} or
            any(not isinstance(item, str) or item not in ALGORITHMS
                for item in mapping.values())):
        raise ValueError("automatic_algorithm_by_tier must map all four tiers to supported algorithms")
    return config


def classify(features: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, str]:
    anchor_count = features.get("estimated_anchor_count")
    raster_work = features.get("estimated_raster_point_tests")
    if not _integer(anchor_count) or not _integer(raster_work):
        return {
            "tier": "UNKNOWN",
            "reason": "required anchor-count or raster-work feature is unavailable",
            "confidence": "LOW",
        }
    for tier in ("LIGHT", "MEDIUM"):
        limits = thresholds["tiers"][tier]
        if (raster_work <= limits["max_estimated_raster_point_tests"] and
                anchor_count <= limits["max_estimated_anchor_count"]):
            return {
                "tier": tier,
                "reason": (
                    f"raster_work={raster_work} <= "
                    f"{limits['max_estimated_raster_point_tests']} and "
                    f"anchors={anchor_count} <= {limits['max_estimated_anchor_count']}"
                ),
                "confidence": "LOW",
            }
    return {
        "tier": "HEAVY",
        "reason": "estimated raster work or anchor count exceeds MEDIUM threshold",
        "confidence": "LOW",
    }


def select_algorithm(tier: str, requested: str, thresholds: dict[str, Any]) -> str:
    if requested == "auto":
        return thresholds["automatic_algorithm_by_tier"][tier]
    if requested not in ALGORITHMS:
        raise ValueError(f"unsupported algorithm: {requested}")
    return requested


def select_pilot_instances(
    profiles: list[dict[str, Any]], maximum: int
) -> list[dict[str, Any]]:
    available = [
        profile for profile in profiles
        if isinstance(profile.get("estimated_raster_point_tests"), int)
    ]
    available.sort(key=lambda profile: (
        profile["estimated_raster_point_tests"], profile["instance_uid"]
    ))
    if len(available) <= maximum:
        return available
    indices = sorted({
        round(index * (len(available) - 1) / (maximum - 1))
        for index in range(maximum)
    }) if maximum > 1 else [len(available) // 2]
    return [available[index] for index in indices]


def run_pilot(
    solver: Path,
    instance: Path,
    output: Path,
    algorithm: str,
    timeout: float,
    memory_limit_mib: int,
    official: bool,
) -> dict[str, Any]:
    command = [
        str(solver), "-i", str(instance), "-o", str(output),
        "--algorithm", algorithm,
        "--instance-timeout", str(timeout),
        "--algorithm-timeout", str(timeout),
        "--memory-limit-mib", str(memory_limit_mib),
    ]
    return_code, stdout, stderr, limit_error, metrics = (
        run_bounded_process_with_metrics(command, timeout, memory_limit_mib)
    )
    if limit_error:
        status = (
            "timeout" if "wall-clock" in limit_error else
            "memory_limit" if "RSS exceeded" in limit_error else
            "memory_probe_failed"
        )
        error = limit_error
    elif return_code != 0 and (
        "deadline" in stderr.lower() or "timed out" in stderr.lower()
    ):
        status = "timeout"
        error = stderr.strip() or "solver reported a wall-clock deadline"
    elif return_code != 0:
        status = "solver_failed"
        error = stderr.strip() or f"solver exited {return_code}"
    else:
        status = "ok"
        error = ""
    result: dict[str, Any] = {
        "empirical_status": status,
        "elapsed_seconds": metrics["wall_seconds"],
        "cpu_seconds": metrics["child_process_tree_cpu_seconds"],
        "peak_process_tree_rss_bytes": metrics["peak_process_tree_rss_bytes"],
        "process_tree_rss_sample_count": metrics["process_tree_rss_sample_count"],
        "termination_reason": metrics["termination_reason"],
        "validation_level": "internal_cpp" if return_code == 0 else None,
        "makespan": None,
        "outcome": error or stderr.strip() or stdout.strip() or "solver produced candidate",
    }
    if status != "ok" or return_code != 0:
        return result
    try:
        candidate = json.loads(output.read_text(encoding="utf-8"))
        result["makespan"] = makespan(candidate)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        result["empirical_status"] = "invalid_output"
        result["validation_level"] = None
        result["outcome"] = str(exc)
        return result
    if official:
        validator = ROOT / "scripts/validate.py"
        validation_code, validation_stdout, validation_stderr, validation_limit, validation_metrics = (
            run_bounded_process_with_metrics(
                [sys.executable, str(validator), str(instance), str(output)],
                max(1.0, timeout), memory_limit_mib,
            )
        )
        result["official_validation_seconds"] = validation_metrics["wall_seconds"]
        result["official_peak_process_tree_rss_bytes"] = (
            validation_metrics["peak_process_tree_rss_bytes"]
        )
        result["official_process_tree_cpu_seconds"] = (
            validation_metrics["child_process_tree_cpu_seconds"]
        )
        if validation_limit:
            result["empirical_status"] = (
                "official_timeout" if "wall-clock" in validation_limit
                else "official_resource_limit"
            )
            result["outcome"] = validation_limit
            result["validation_level"] = None
            return result
        if validation_code != 0:
            result["empirical_status"] = "official_invalid"
            result["outcome"] = (validation_stderr + validation_stdout).strip()
            result["validation_level"] = None
            return result
        result["validation_level"] = "official"
        result["outcome"] = "candidate passed official validation"
    return result


def spearman_rank_correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=values.__getitem__)
        output = [0.0] * len(values)
        start = 0
        while start < len(order):
            end = start + 1
            while end < len(order) and values[order[end]] == values[order[start]]:
                end += 1
            rank = (start + end - 1) / 2 + 1
            for index in order[start:end]:
                output[index] = rank
            start = end
        return output

    rank_x, rank_y = ranks(xs), ranks(ys)
    if len(set(rank_x)) < 2 or len(set(rank_y)) < 2:
        return None
    mean_x, mean_y = statistics.mean(rank_x), statistics.mean(rank_y)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(rank_x, rank_y))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in rank_x) *
        sum((y - mean_y) ** 2 for y in rank_y)
    )
    return numerator / denominator if denominator else None


def _calibration_metrics(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        row for row in profiles
        if row.get("empirical_status") == "ok" and
        row.get("validation_level") in {"internal_cpp", "official"}
    ]
    tiers = sorted({row["estimated_tier"] for row in successful})
    rho = spearman_rank_correlation(
        [float(row["estimated_raster_point_tests"]) for row in successful],
        [float(row["elapsed_seconds"]) for row in successful],
    )
    all_tiers = {"LIGHT", "MEDIUM", "HEAVY"}
    return {
        "successful_validated_runs": len(successful),
        "successful_tiers": tiers,
        "spearman_raster_work_vs_elapsed_seconds": rho,
        "timed_out_runs": sum(row.get("empirical_status") == "timeout"
                              for row in profiles),
        "threshold_validation_status": (
            "insufficient tier coverage; descriptive correlation only"
            if not all_tiers.issubset(set(tiers))
            else "pilot tier coverage available; not a hardware-independent guarantee"
        ),
    }


def _hardware_context() -> dict[str, Any]:
    processor = platform.processor() or None
    memory_bytes = None
    if sys.platform == "darwin":
        for key, target in (
            ("machdep.cpu.brand_string", "processor"),
            ("hw.memsize", "memory_bytes"),
        ):
            try:
                result = subprocess.run(
                    ["sysctl", "-n", key], capture_output=True, text=True,
                    timeout=2, check=False,
                )
                if result.returncode == 0:
                    value = result.stdout.strip()
                    if target == "processor":
                        processor = value
                    else:
                        memory_bytes = int(value)
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
    return {
        "platform": platform.platform(),
        "processor": processor,
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "available_cpu_workers": available_cpu_workers(),
        "memory_bytes": memory_bytes,
        "python": sys.version,
    }


def _plot_svg(profiles: list[dict[str, Any]], path: Path) -> None:
    points = [
        (profile["estimated_raster_point_tests"], profile["elapsed_seconds"])
        for profile in profiles
        if profile.get("empirical_status") == "ok"
        and isinstance(profile.get("elapsed_seconds"), (int, float))
        and profile["elapsed_seconds"] > 0
        and profile.get("estimated_raster_point_tests", 0) > 0
    ]
    if len(points) < 3:
        return
    width, height = 800, 500
    left, right, top, bottom = 90, 30, 40, 75
    xs = [math.log10(point[0]) for point in points]
    ys = [math.log10(point[1]) for point in points]
    low_x, high_x = min(xs), max(xs)
    low_y, high_y = min(ys), max(ys)
    if low_x == high_x:
        low_x -= 0.5
        high_x += 0.5
    if low_y == high_y:
        low_y -= 0.5
        high_y += 0.5
    xspan, yspan = width - left - right, height - top - bottom
    circles = []
    for x, y in zip(xs, ys):
        px = left + xspan * (x - low_x) / (high_x - low_x)
        py = top + yspan * (1 - (y - low_y) / (high_y - low_y))
        circles.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#146c94"/>')
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="400" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">Pilot runtime vs estimated raster work</text>',
        f'<path d="M{left} {top}V{height-bottom}H{width-right}" fill="none" stroke="#333"/>',
        *circles,
        f'<text x="400" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="13">Estimated raster point tests (log10 scale)</text>',
        f'<text transform="translate(22 {height/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="13">Elapsed seconds (log10 scale)</text>',
        f'<text x="{left}" y="{height-bottom+20}" font-family="sans-serif" font-size="11">10^{low_x:.1f}</text>',
        f'<text x="{width-right-45}" y="{height-bottom+20}" font-family="sans-serif" font-size="11">10^{high_x:.1f}</text>',
        f'<text x="{left-42}" y="{height-bottom}" font-family="sans-serif" font-size="11">10^{low_y:.1f}</text>',
        f'<text x="{left-42}" y="{top+4}" font-family="sans-serif" font-size="11">10^{high_y:.1f}</text>',
        '</svg>',
    ]
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def _write_tsv(profiles: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=PROFILE_COLUMNS, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        for profile in profiles:
            writer.writerow(profile)


def _summary(
    profiles: list[dict[str, Any]], thresholds: dict[str, Any],
    pilot: dict[str, Any], hardware: dict[str, Any],
) -> str:
    counts = {tier: sum(row.get("estimated_tier") == tier for row in profiles)
              for tier in ("LIGHT", "MEDIUM", "HEAVY", "UNKNOWN")}
    calibration = _calibration_metrics(profiles)
    successful = [
        row for row in profiles if row.get("empirical_status") == "ok"
    ]
    rho = calibration["spearman_raster_work_vs_elapsed_seconds"]
    lines = [
        "# Local instance profiling summary",
        "",
        f"- Threshold version: `{thresholds['threshold_version']}`",
        f"- Instances profiled: {len(profiles)}",
        f"- Estimated tiers: LIGHT {counts['LIGHT']}, MEDIUM {counts['MEDIUM']}, "
        f"HEAVY {counts['HEAVY']}, UNKNOWN {counts['UNKNOWN']}",
        f"- Pilot runs: {len(pilot)}; successful validated outcomes: {len(successful)}",
        f"- Spearman correlation (raster-work proxy vs successful wall time): "
        f"{rho:.3f} (n={len(successful)}; successful tiers: "
        f"{', '.join(calibration['successful_tiers']) or 'none'})" if rho is not None else
        f"- Spearman correlation: unavailable (need >=3 successful runs and nonconstant data; n={len(successful)})",
        f"- Threshold assessment: {calibration['threshold_validation_status']}",
        "",
        "## Thresholds",
        "",
        "| Tier | Max raster point tests | Max estimated anchors |",
        "|---|---:|---:|",
    ]
    for tier in ("LIGHT", "MEDIUM"):
        threshold = thresholds["tiers"][tier]
        lines.append(
            f"| {tier} | {threshold['max_estimated_raster_point_tests']} | "
            f"{threshold['max_estimated_anchor_count']} |"
        )
    lines.extend([
        "",
        "The tiers are deterministic workload estimates, not proven runtime classes. "
        "Confidence is LOW because the pilot is bounded and does not validate polygon "
        "topology during feature extraction. The raster-work proxy is the outer "
        "bounding-box cell count multiplied by total region-ring vertices; it is a "
        "conservative operation proxy for repeated rasterization, not measured CPU work.",
        "",
        "Coverage-relation counts and total coverage-representation memory are left "
        "unknown: they depend on raster topology, hash-table overhead, route lengths, "
        "and process/runtime behavior. The coordinate-payload byte field is only a "
        "lower bound. Actual peak process-tree RSS and child CPU time are reported "
        "separately for pilot runs.",
        "",
        f"The pilot had {calibration['timed_out_runs']} timed-out runs. These are "
        "right-censored and excluded from runtime correlation; runs without an "
        "accepted validation level are also excluded.",
        "",
        "## Pilot outcome",
        "",
        "| Instance | Estimated tier | Algorithm | Status | Validation | Wall seconds | CPU seconds | Peak RSS MiB |",
        "|---|---|---|---|---|---:|---:|---:|",
    ])
    for row in profiles:
        if not row.get("empirical_status"):
            continue
        rss = row.get("peak_process_tree_rss_bytes")
        lines.append(
            f"| {row['instance_uid']} | {row['estimated_tier']} | "
            f"{row.get('selected_algorithm', '')} | {row['empirical_status']} | "
            f"{row.get('validation_level') or 'none'} | "
            f"{row.get('elapsed_seconds', '')} | {row.get('cpu_seconds', '')} | "
            f"{rss / (1024 * 1024):.1f} |" if isinstance(rss, (int, float)) else
            f"| {row['instance_uid']} | {row['estimated_tier']} | "
            f"{row.get('selected_algorithm', '')} | {row['empirical_status']} | "
            f"{row.get('validation_level') or 'none'} | "
            f"{row.get('elapsed_seconds', '')} | {row.get('cpu_seconds', '')} | unavailable |"
        )
    lines.extend([
        "",
        "## Classification reasons",
        "",
        "| Instance | Tier | Confidence | Reason |",
        "|---|---|---|---|",
    ])
    for row in profiles:
        lines.append(
            f"| {row['instance_uid']} | {row['estimated_tier']} | "
            f"{row['classification_confidence']} | {row['classification_reason']} |"
        )
    lines.extend([
        "",
        "## Calibration limits",
        "",
        f"Pilot environment: `{hardware['platform']}`, `{hardware['processor'] or 'processor unknown'}`. "
        "The pilot samples a deterministic size-stratified subset; it is not a representative "
        "hardware-independent benchmark. Runs that time out, exceed memory, fail, or lack "
        "validation are excluded from runtime correlation and remain visible in the profile. "
        "No thresholds are automatically fitted from this small pilot. A correlation "
        "computed only among successful runs is descriptive; timeouts are not treated "
        "as exact runtimes.",
        "",
        "Automatic algorithm selection uses the explicit `automatic_algorithm_by_tier` "
        "mapping in the profiler configuration. Defaults select `hybrid` for every tier "
        "because this pilot does not establish a quality/runtime-optimal tier policy.",
        "",
    ])
    return "\n".join(lines)


def _new_output_dir(path: Path | None) -> Path:
    if path is None:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = ROOT / "build/profiles" / f"run-{stamp}-{os.getpid()}"
    if path.exists():
        raise ValueError(f"profile output already exists; refusing to overwrite: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, default=ROOT / "data/test")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--pilot", action="store_true",
                        help="run a bounded pilot after extracting estimates")
    parser.add_argument("--pilot-max-instances", type=int, default=12)
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument("--algorithm", default="auto",
                        help="algorithm name or auto (tier mapping; default: auto)")
    parser.add_argument("--timeout", type=float, default=3.0,
                        help="pilot wall-clock limit per solver run in seconds")
    parser.add_argument("--memory-limit-mib", type=int, default=1024)
    parser.add_argument("--official", action="store_true",
                        help="require official pyutils validation for pilot outcomes")
    args = parser.parse_args()
    try:
        thresholds = load_thresholds(args.thresholds.resolve())
    except ValueError as error:
        parser.error(str(error))
    if not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    paths = sorted(args.instances.glob("*.instance.json"))
    if not paths:
        parser.error(f"no *.instance.json files found in {args.instances}")
    if args.pilot_max_instances < 1:
        parser.error("--pilot-max-instances must be positive")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.memory_limit_mib < 1:
        parser.error("--memory-limit-mib must be positive")
    if args.pilot and (not args.solver.is_file() or not os.access(args.solver, os.X_OK)):
        parser.error(f"solver executable not found or not executable: {args.solver}")
    if args.official:
        try:
            import cgshop2027_pyutils  # noqa: F401
        except ImportError:
            parser.error("--official requires cgshop2027_pyutils in this Python interpreter")
    if args.algorithm != "auto" and args.algorithm not in ALGORITHMS:
        parser.error(f"unsupported algorithm: {args.algorithm}")

    profiles = []
    for path in paths:
        try:
            features = extract_features(path)
            category = classify(features, thresholds)
            row = {
                **features,
                "path": str(path.resolve()),
                "estimated_tier": category["tier"],
                "classification_reason": category["reason"],
                "classification_confidence": category["confidence"],
                "threshold_version": thresholds["threshold_version"],
            }
            row["selected_algorithm"] = select_algorithm(
                row["estimated_tier"], args.algorithm, thresholds
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            row = {
                "instance_uid": path.name,
                "path": str(path.resolve()),
                "estimated_tier": "UNKNOWN",
                "classification_reason": str(error),
                "classification_confidence": "LOW",
                "threshold_version": thresholds["threshold_version"],
                "selected_algorithm": select_algorithm(
                    "UNKNOWN", args.algorithm, thresholds
                ),
                "estimated_total_coverage_memory_bytes": None,
                "measured_features": {},
                "derived_exact_features": {},
                "estimated_features": {
                    "estimated_anchor_count": None,
                    "estimated_coverage_candidate_pairs": None,
                    "estimated_raster_point_tests": None,
                    "estimated_coordinate_payload_bytes_lower_bound": None,
                    "estimated_total_coverage_memory_bytes": None,
                },
            }
        profiles.append(row)

    pilot_rows: list[dict[str, Any]] = []
    if args.pilot:
        selected = select_pilot_instances(profiles, args.pilot_max_instances)
        with tempfile.TemporaryDirectory(prefix="cgshop-profile-pilot-") as temp:
            work = Path(temp)
            for index, row in enumerate(selected):
                output = work / f"{index:04d}.solution.json"
                result = run_pilot(
                    args.solver.resolve(), Path(row["path"]), output,
                    row["selected_algorithm"], args.timeout,
                    args.memory_limit_mib, args.official,
                )
                row.update(result)
                pilot_rows.append(row)
                print(
                    f"{row['instance_uid']}\t{row['estimated_tier']}\t"
                    f"{row['selected_algorithm']}\t{row['empirical_status']}\t"
                    f"{row.get('elapsed_seconds', 0):.3f}s"
                )

    try:
        output_dir = _new_output_dir(args.output_dir.resolve() if args.output_dir else None)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    calibration = _calibration_metrics(profiles)
    hardware = _hardware_context()
    report = {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "threshold_version": thresholds["threshold_version"],
        "thresholds": thresholds,
        "classification_kind": "pre_solve_estimate",
        "pilot": {
            "requested": args.pilot,
            "instances_run": len(pilot_rows),
            "algorithm_request": args.algorithm,
            "timeout_seconds": args.timeout if args.pilot else None,
            "memory_limit_mib": args.memory_limit_mib if args.pilot else None,
            "official_validation_requested": args.official,
            "memory_sampling_interval_seconds": 0.05,
            "peak_rss_note": "sampled peak; null if the process exited before the first sample",
            "cpu_measurement": "sampled cumulative process-tree CPU from ps where available",
            "memory_enforcement": "sampled aggregate process-tree RSS watchdog",
        },
        "hardware": hardware,
        "calibration": calibration,
        "instances": profiles,
    }
    (output_dir / "profile.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(profiles, output_dir / "profile.tsv")
    (output_dir / "summary.md").write_text(
        _summary(profiles, thresholds, pilot_rows, hardware),
        encoding="utf-8",
    )
    if args.pilot:
        _plot_svg(pilot_rows, output_dir / "runtime-vs-raster-work.svg")
    print(f"profiled {len(profiles)} instances; results: {output_dir}")
    print(f"pilot outcomes: {len(pilot_rows)}; successful: "
          f"{sum(row.get('empirical_status') == 'ok' for row in pilot_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
