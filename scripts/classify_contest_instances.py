#!/usr/bin/env python3
"""Inventory and deterministically tier the official local contest instances."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cgshop2027_pyutils.io import read_instance

from profile_instances import (
    DEFAULT_THRESHOLDS,
    classify as classify_fixed,
    extract_features,
    load_thresholds,
)
from runtime_config import ROOT


CLASSIFICATION_VERSION = "cgshop-contest-relative-workload-v1"
TIERS = ("LIGHT", "MEDIUM", "HEAVY")
MIN_FIXED_TIER_SHARE = 0.10
CLASSIFICATION_FEATURE_ORDER = (
    "estimated_raster_point_tests",
    "estimated_coverage_candidate_pairs",
    "estimated_anchor_count",
    "estimated_ip_kont_columns_upper_bound",
    "estimated_ip_kont_variables_upper_bound",
    "estimated_ip_kont_constraints_upper_bound",
    "number_of_cutters",
    "boundary_vertices",
    "file_bytes",
    "instance_uid",
)
FEATURE_COLUMNS = (
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
)
MANIFEST_COLUMNS = (
    "instance_uid",
    "relative_source_path",
    "sha256",
    "tier",
    *FEATURE_COLUMNS,
    "estimated_workload_score",
    "classification_method",
    "classification_version",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feature_value(features: dict[str, Any], key: str) -> Any:
    value = features.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"classification feature {key} is missing or invalid")
    return value


def workload_key(features: dict[str, Any]) -> tuple[Any, ...]:
    values = tuple(
        _feature_value(features, name)
        for name in CLASSIFICATION_FEATURE_ORDER
    )
    if not isinstance(values[-1], str) or not values[-1]:
        raise ValueError("instance_uid must be a nonempty string")
    if any(not isinstance(value, int) for value in values[:-1]):
        raise ValueError("numeric workload features must be integers")
    return values


def classify_dataset(
    rows: list[dict[str, Any]],
    thresholds: dict[str, Any],
    thresholds_path: Path = DEFAULT_THRESHOLDS,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Use fixed tiers only when each class has a nontrivial dataset share."""
    if not rows:
        raise ValueError("cannot classify an empty instance dataset")
    fixed = {
        row["features"]["instance_uid"]: classify_fixed(row["features"], thresholds)
        for row in rows
    }
    fixed_counts = Counter(result["tier"] for result in fixed.values())
    minimum_count = max(1, math.ceil(len(rows) * MIN_FIXED_TIER_SHARE))
    if all(fixed_counts[tier] >= minimum_count for tier in TIERS):
        return (
            "fixed_thresholds",
            {
                uid: result["tier"]
                for uid, result in fixed.items()
            },
            {
                "classification_version": thresholds["threshold_version"],
                "method": "existing fixed workload thresholds",
                "thresholds_path": (
                    thresholds_path.resolve().relative_to(ROOT).as_posix()
                    if thresholds_path.resolve().is_relative_to(ROOT)
                    else str(thresholds_path.resolve())
                ),
                "minimum_fixed_tier_share": MIN_FIXED_TIER_SHARE,
                "fixed_threshold_counts": {
                    tier: fixed_counts[tier] for tier in TIERS
                },
                "minimum_meaningful_tier_count": minimum_count,
                "minimum_fixed_tier_share": MIN_FIXED_TIER_SHARE,
            },
        )

    ordered = sorted(rows, key=lambda row: workload_key(row["features"]))
    count = len(ordered)
    first_cut = count // 3
    second_cut = (2 * count) // 3
    if count >= 3 and (first_cut == 0 or second_cut <= first_cut or second_cut >= count):
        raise ValueError("cannot produce three nonempty relative tiers")
    cuts = (first_cut, second_cut)
    tiers_by_uid: dict[str, str] = {}
    for index, row in enumerate(ordered):
        tier = TIERS[0] if index < cuts[0] else (
            TIERS[1] if index < cuts[1] else TIERS[2]
        )
        tiers_by_uid[row["features"]["instance_uid"]] = tier

    def boundary(index: int) -> dict[str, Any] | None:
        if index <= 0 or index >= count:
            return None
        previous = ordered[index - 1]["features"]
        following = ordered[index]["features"]
        return {
            "last_in_lower_tier": {
                key: previous[key] for key in CLASSIFICATION_FEATURE_ORDER
            },
            "first_in_upper_tier": {
                key: following[key] for key in CLASSIFICATION_FEATURE_ORDER
            },
        }

    return (
        "relative_workload",
        tiers_by_uid,
        {
            "classification_version": CLASSIFICATION_VERSION,
            "method": (
                "ascending lexicographic ordering by estimated raster point tests, "
                "estimated coverage candidate pairs, then deterministic secondary "
                "workload features; instance_uid is the final tie-breaker; split "
                "at floor(n/3) and floor(2n/3)"
            ),
            "feature_order": list(CLASSIFICATION_FEATURE_ORDER),
            "cut_indices_zero_based": list(cuts),
            "cut_points": {
                "LIGHT_to_MEDIUM": boundary(cuts[0]),
                "MEDIUM_to_HEAVY": boundary(cuts[1]),
            },
            "fixed_threshold_counts": {
                tier: fixed_counts[tier] for tier in TIERS
            },
            "minimum_meaningful_tier_count": minimum_count,
            "relative_tiers_are_runtime_or_memory_guarantees": False,
            "relative_tiers_description": (
                "approximate workload-rank groups derived from geometric estimates"
            ),
        },
    )


def _read_inputs(instances_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    candidates = sorted(instances_dir.rglob("*.instance.json"))
    if not candidates:
        raise ValueError(
            f"official input directory contains no *.instance.json files: {instances_dir}"
        )
    failures: list[dict[str, str]] = []
    before_hashes: dict[str, str] = {}
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink():
            failures.append({
                "relative_source_path": relative,
                "error": "symlinked instance files are not included",
            })
            continue
        try:
            path.resolve().relative_to(instances_dir.resolve())
            before_hashes[relative] = sha256_file(path)
        except (OSError, ValueError) as error:
            failures.append({
                "relative_source_path": relative,
                "error": f"input path or hash error: {error}",
            })

    rows: list[dict[str, Any]] = []
    uids: dict[str, str] = {}
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in before_hashes:
            continue
        try:
            instance = read_instance(path)
            if instance.content_type != "CGSHOP2027_Instance":
                raise ValueError(
                    f"unexpected content_type: {instance.content_type!r}"
                )
            uid = instance.instance_uid
            if not isinstance(uid, str) or not uid:
                raise ValueError("official parser returned an empty instance_uid")
            required_fields = (
                "region_to_cover", "cutter", "cutter_center", "number_of_cutters"
            )
            missing = [
                field for field in required_fields
                if not hasattr(instance, field) or getattr(instance, field) is None
            ]
            if missing:
                raise ValueError(
                    "official instance schema omitted required fields: "
                    + ", ".join(missing)
                )
            if uid in uids:
                raise ValueError(
                    f"duplicate instance_uid {uid!r}; first seen in {uids[uid]}"
                )
            uids[uid] = relative
            features = extract_features(path)
            if features["instance_uid"] != uid:
                raise ValueError(
                    "official parser UID differs from profiler-extracted UID"
                )
            rows.append({
                "instance_uid": uid,
                "relative_source_path": relative,
                "sha256": before_hashes[relative],
                "features": features,
            })
        except Exception as error:
            failures.append({
                "relative_source_path": relative,
                "error": f"{type(error).__name__}: {error}",
            })

    after_hashes: dict[str, str] = {}
    for relative in before_hashes:
        try:
            after_hashes[relative] = sha256_file(ROOT / relative)
        except OSError as error:
            failures.append({
                "relative_source_path": relative,
                "error": f"post-processing hash error: {error}",
            })
    changed = [
        relative for relative, initial in before_hashes.items()
        if after_hashes.get(relative) != initial
    ]
    if changed:
        failures.extend({
            "relative_source_path": relative,
            "error": "source SHA-256 changed during processing",
        } for relative in changed)
    integrity = [
        {
            "relative_source_path": relative,
            "sha256_before": before_hashes[relative],
            "sha256_after": after_hashes.get(relative),
            "unchanged": after_hashes.get(relative) == before_hashes[relative],
        }
        for relative in sorted(before_hashes)
    ]
    return rows, failures, integrity


def _safe_run_dir(output_root: Path, instances_dir: Path) -> Path:
    output_root = output_root.resolve()
    dataset_root = instances_dir.resolve()
    if output_root == dataset_root or output_root.is_relative_to(dataset_root):
        raise ValueError(
            f"output root must be outside the source dataset: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = output_root / f"instance-classification-{run_id}-{os.getpid()}"
    run_dir.mkdir(exist_ok=False)
    return run_dir


def _manifest_rows(
    rows: list[dict[str, Any]],
    tiers_by_uid: dict[str, str],
    method: str,
) -> list[dict[str, Any]]:
    result = []
    for row in sorted(rows, key=lambda item: item["instance_uid"]):
        features = row["features"]
        result.append({
            "instance_uid": row["instance_uid"],
            "relative_source_path": row["relative_source_path"],
            "sha256": row["sha256"],
            "tier": tiers_by_uid.get(row["instance_uid"], ""),
            **{key: features.get(key) for key in FEATURE_COLUMNS},
            "estimated_workload_score": json.dumps([
                features["estimated_raster_point_tests"],
                features["estimated_coverage_candidate_pairs"],
            ], separators=(",", ":")),
            "classification_method": method,
            "classification_version": (
                CLASSIFICATION_VERSION if method == "relative_workload"
                else "cgshop-instance-work-v1"
            ),
        })
    return result


def _write_summary(
    output: Path,
    run_id: str,
    input_dir: Path,
    manifest_rows: list[dict[str, Any]],
    classification: dict[str, Any],
    failures: list[dict[str, str]],
    complete: bool,
) -> None:
    counts = Counter(row["tier"] for row in manifest_rows)
    lines = [
        "# Contest instance classification",
        "",
        f"- Run ID: `{run_id}`",
        f"- Source collection: `{input_dir.relative_to(ROOT).as_posix()}`",
        f"- Classification complete: **{str(complete).lower()}**",
        f"- Classified instances: **{len(manifest_rows)}**",
        f"- Malformed, duplicate, or integrity errors: **{len(failures)}**",
        f"- Method: `{classification['method']}`",
        f"- Version: `{classification['classification_version']}`",
        "",
        "## Tier counts",
        "",
        "| Tier | Instances |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {tier} | {counts[tier]} |" for tier in TIERS)
    lines.extend(["", "## Ordering and cut points", ""])
    if classification["method"] == "relative_workload":
        lines.extend([
            "Instances are ordered by estimated raster point tests, then estimated "
            "coverage candidate pairs, followed by the deterministic secondary "
            "features listed in `profile.json`; `instance_uid` is the final "
            "tie-breaker. Groups use indices `[0, floor(n/3))`, "
            "`[floor(n/3), floor(2n/3))`, and `[floor(2n/3), n)`.",
            "",
            "These are relative workload tiers derived from geometric estimates; "
            "they do not guarantee runtime or memory behavior.",
            "",
            f"- LIGHT → MEDIUM cut: `{json.dumps(classification['cut_points']['LIGHT_to_MEDIUM'], sort_keys=True)}`",
            f"- MEDIUM → HEAVY cut: `{json.dumps(classification['cut_points']['MEDIUM_to_HEAVY'], sort_keys=True)}`",
        ])
    else:
        lines.extend([
            "The existing fixed thresholds were retained because all tiers meet "
            f"the recorded minimum share ({MIN_FIXED_TIER_SHARE:.0%}).",
            "",
            f"- Fixed threshold counts: `{json.dumps(classification['fixed_threshold_counts'], sort_keys=True)}`",
        ])
    lines.extend(["", "## Input issues", ""])
    if failures:
        lines.extend(
            f"- `{item['relative_source_path']}`: {item['error']}"
            for item in failures
        )
    else:
        lines.append("None.")
    lines.extend([
        "",
        "## Artifacts",
        "",
        "- `instance-manifest.tsv`",
        "- `profile.json`",
        "- `tiers/LIGHT.txt`, `tiers/MEDIUM.txt`, `tiers/HEAVY.txt`",
        "",
    ])
    (output / "classification-summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def create_inventory(
    instances_dir: Path,
    output_root: Path,
    thresholds_path: Path = DEFAULT_THRESHOLDS,
) -> tuple[Path, dict[str, Any]]:
    instances_dir = instances_dir.resolve()
    if not instances_dir.is_dir():
        raise ValueError(
            f"official input directory is missing: {instances_dir}; "
            "refusing to fall back to data/test or fixtures"
        )
    if not instances_dir.is_relative_to(ROOT / "data/instances"):
        raise ValueError(
            "selected inputs must be under the intended real contest directory "
            f"{(ROOT / 'data/instances').as_posix()}"
        )
    thresholds = load_thresholds(thresholds_path)
    rows, failures, integrity = _read_inputs(instances_dir)
    duplicate_uids = len({row["instance_uid"] for row in rows}) != len(rows)
    complete = not failures and not duplicate_uids
    classification: dict[str, Any] = {
        "method": "not_run",
        "classification_version": CLASSIFICATION_VERSION,
    }
    tiers_by_uid: dict[str, str] = {}
    if complete:
        method, tiers_by_uid, classification = classify_dataset(
            rows, thresholds, thresholds_path
        )
        classification["method"] = method
    manifest_rows = _manifest_rows(rows, tiers_by_uid, classification["method"])
    output = _safe_run_dir(output_root, instances_dir)
    run_id = output.name.removeprefix("instance-classification-")

    with (output / "instance-manifest.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=MANIFEST_COLUMNS, delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    (output / "tiers").mkdir()
    for tier in TIERS:
        tier_paths = [
            row["relative_source_path"]
            for row in manifest_rows if row["tier"] == tier
        ]
        (output / "tiers" / f"{tier}.txt").write_text(
            "".join(path + "\n" for path in sorted(tier_paths)),
            encoding="utf-8",
        )

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "classification_complete": complete,
        "source_directory": instances_dir.relative_to(ROOT).as_posix(),
        "selected_instance_count": len(rows),
        "source_candidate_count": len(integrity),
        "unique_uid_count": len({row["instance_uid"] for row in rows}),
        "malformed_duplicate_or_integrity_error_count": len(failures),
        "malformed_duplicate_or_integrity_errors": failures,
        "classification": classification,
        "thresholds": thresholds,
        "features": {
            "source": "scripts/profile_instances.py::extract_features",
            "classification_feature_order": list(CLASSIFICATION_FEATURE_ORDER),
            "manifest_feature_columns": list(FEATURE_COLUMNS),
            "estimated_workload_score": (
                "ordered pair [estimated_raster_point_tests, "
                "estimated_coverage_candidate_pairs]"
            ),
        },
        "tier_counts": {
            tier: sum(row["tier"] == tier for row in manifest_rows)
            for tier in TIERS
        },
        "input_integrity": {
            "all_hashes_unchanged": all(item["unchanged"] for item in integrity),
            "files": integrity,
        },
        "instances": [
            {
                **{
                    key: row[key] for key in (
                        "instance_uid", "relative_source_path", "sha256", "tier",
                        "estimated_workload_score", "classification_method",
                        "classification_version",
                    )
                },
                "features": {
                    key: row[key] for key in FEATURE_COLUMNS
                },
            }
            for row in manifest_rows
        ],
    }
    (output / "profile.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary(
        output, run_id, instances_dir, manifest_rows, classification, failures, complete
    )
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instances", type=Path, default=ROOT / "data/instances",
        help="official real contest inputs (default: data/instances)",
    )
    parser.add_argument(
        "--thresholds", type=Path, default=DEFAULT_THRESHOLDS,
        help="existing fixed profiler threshold config",
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "build/cgshop2027-study",
        help="parent for a new collision-safe classification run directory",
    )
    args = parser.parse_args()
    try:
        output, report = create_inventory(
            args.instances, args.output_root, args.thresholds
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(
        f"classified {report['selected_instance_count']} official instances; "
        f"tiers={json.dumps(report['tier_counts'], sort_keys=True)}; "
        f"errors={report['malformed_duplicate_or_integrity_error_count']}; "
        f"complete={str(report['classification_complete']).lower()}; "
        f"results={output}"
    )
    return 0 if report["classification_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
