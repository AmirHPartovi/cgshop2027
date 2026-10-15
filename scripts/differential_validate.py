#!/usr/bin/env python3
"""Compare internal C++ checks with the official cgshop2027-pyutils verifier."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _outside_excursion(solution: dict[str, Any], instance: dict[str, Any]) -> None:
    tour = solution["tours"][0]
    points = list(zip(tour["x"], tour["y"]))
    first = points[0]
    last = points[-1]
    outer = instance["region_to_cover"]["outer_boundary"]
    outside_y = max(max(tour["y"]), max(outer["y"])) + 10
    connector = (first[0], last[1])
    outside = (first[0], outside_y)
    extension = []
    if connector != last:
        extension.append(connector)
    if outside != (extension[-1] if extension else last):
        extension.append(outside)
    points.extend(extension)
    tour["x"] = [point[0] for point in points]
    tour["y"] = [point[1] for point in points]


def _overlapping_trajectories(solution: dict[str, Any]) -> None:
    tours = solution["tours"]
    if len(tours) < 2:
        return
    all_x = [x for tour in tours for x in tour["x"]]
    all_y = [y for tour in tours for y in tour["y"]]
    shared = (max(all_x) + 10, max(all_y) + 10)
    for tour in tours:
        points = list(zip(tour["x"], tour["y"]))
        first = points[0]
        elbow = (shared[0], first[1])
        prefix = [first]
        if elbow != first:
            prefix.append(elbow)
        if shared != prefix[-1]:
            prefix.append(shared)
        if elbow != prefix[-1]:
            prefix.append(elbow)
        if first != prefix[-1]:
            prefix.append(first)
        points = prefix + points[1:]
        tour["x"] = [point[0] for point in points]
        tour["y"] = [point[1] for point in points]


def _has_turns(solution: dict[str, Any]) -> bool:
    for tour in solution["tours"]:
        points = list(zip(tour["x"], tour["y"]))
        if len(points) < 3:
            continue
        directions = []
        for start, end in zip(points, [*points[1:], points[0]]):
            direction = (end[0] - start[0], end[1] - start[1])
            if direction != (0, 0):
                directions.append((direction[0] != 0, direction[0] > 0, direction[1] > 0))
        if any(directions[i] != directions[i - 1] for i in range(len(directions))):
            return True
    return False


def candidate_cases(
    baseline: dict[str, Any], instance: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = [("generated", copy.deepcopy(baseline))]

    outside = copy.deepcopy(baseline)
    _outside_excursion(outside, instance)
    cases.append(("outside-region-trajectory", outside))

    if _has_turns(baseline):
        cases.append(("turns-and-implicit-closure", copy.deepcopy(baseline)))

    swept = copy.deepcopy(baseline)
    cases.append(("swept-cutter-coverage", swept))

    if len(baseline["tours"]) > 1:
        overlap = copy.deepcopy(baseline)
        _overlapping_trajectories(overlap)
        cases.append(("overlapping-cutter-trajectories", overlap))

    wrong_uid = copy.deepcopy(baseline)
    wrong_uid["instance_uid"] = "differential-wrong-uid"
    cases.append(("wrong-instance-uid", wrong_uid))

    wrong_count = copy.deepcopy(baseline)
    if len(wrong_count["tours"]) > 1:
        wrong_count["tours"].pop()
    else:
        wrong_count["tours"].append(copy.deepcopy(wrong_count["tours"][0]))
    cases.append(("wrong-cutter-count", wrong_count))

    nonrectilinear = copy.deepcopy(baseline)
    first_tour = nonrectilinear["tours"][0]
    first_tour["x"] = [0, 1]
    first_tour["y"] = [0, 1]
    cases.append(("nonrectilinear-edge", nonrectilinear))

    uncovered = copy.deepcopy(baseline)
    for tour in uncovered["tours"]:
        tour["x"] = [100000]
        tour["y"] = [100000]
    cases.append(("uncovered-region", uncovered))

    repeated_close = copy.deepcopy(baseline)
    first_tour = repeated_close["tours"][0]
    if first_tour["x"]:
        first_tour["x"].append(first_tour["x"][0])
        first_tour["y"].append(first_tour["y"][0])
    cases.append(("repeated-closing-point", repeated_close))

    empty_tour = copy.deepcopy(baseline)
    empty_tour["tours"][0] = {"x": [], "y": []}
    cases.append(("empty-tour", empty_tour))
    return cases


def _internal_result(checker: Path, instance: Path, solution: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(checker), str(instance), str(solution)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"internal checker failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"internal checker returned invalid JSON: {error}") from error
    if not isinstance(result, dict) or not isinstance(result.get("instance_valid"), bool):
        raise RuntimeError("internal checker returned an invalid result object")
    return result


def _official_result(instance: Any, solution_path: Path) -> dict[str, Any]:
    from cgshop2027_pyutils.io import read_solution
    from cgshop2027_pyutils.verify import check_for_errors

    try:
        solution = read_solution(solution_path)
        errors = check_for_errors(instance, solution)
        return {
            "valid": not errors,
            "makespan": solution.max_tour_length if not errors else None,
            "errors": [str(error) for error in errors],
        }
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"valid": False, "makespan": None, "errors": [str(error)]}


def _new_results_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = root / f"differential-{timestamp}-{os.getpid()}"
    candidate.mkdir(exist_ok=False)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instances", type=Path, default=ROOT / "tests/fixtures/instances"
    )
    parser.add_argument("--solver", type=Path, default=ROOT / "build/bin/solver")
    parser.add_argument(
        "--internal-checker",
        type=Path,
        default=ROOT / "build/bin/internal_solution_check",
    )
    parser.add_argument(
        "--results-root", type=Path, default=ROOT / "build/test-results"
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    try:
        from cgshop2027_pyutils.io import read_instance
        from cgshop2027_pyutils.verify import check_for_errors
    except ImportError as error:
        print(
            f"ERROR: official cgshop2027-pyutils dependency unavailable: {error}",
            file=sys.stderr,
        )
        return 2

    for executable in (args.solver, args.internal_checker):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            print(f"ERROR: required executable is missing or not executable: {executable}",
                  file=sys.stderr)
            return 2
    if not args.instances.is_dir():
        print(f"ERROR: instance directory does not exist: {args.instances}", file=sys.stderr)
        return 2
    instance_paths = sorted(args.instances.glob("*.instance.json"))
    if not instance_paths:
        print(f"ERROR: no *.instance.json fixtures found in {args.instances}",
              file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("ERROR: --timeout must be positive", file=sys.stderr)
        return 2

    results_dir = _new_results_dir(args.results_root)
    candidates_dir = results_dir / "candidates"
    candidates_dir.mkdir()
    saved_instances_dir = results_dir / "instances"
    saved_instances_dir.mkdir()
    rows: list[dict[str, Any]] = []
    mismatch_count = 0
    instance_count = 0
    official_count = 0
    try:
        for instance_path in instance_paths:
            uid = instance_path.name.removesuffix(".instance.json")
            saved_instance_path = saved_instances_dir / instance_path.name
            saved_instance_path.write_bytes(instance_path.read_bytes())
            try:
                official_instance = read_instance(instance_path)
            except Exception as error:
                raise RuntimeError(
                    f"official instance loading failed for {instance_path}: {error}"
                ) from error
            instance_count += 1

            baseline_path = candidates_dir / f"{uid}.generated.solution.json"
            generated = subprocess.run(
                [
                    str(args.solver),
                    "-i",
                    str(instance_path),
                    "-o",
                    str(baseline_path),
                    "-a",
                    "partition",
                    "-t",
                    str(args.timeout),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=args.timeout + 10,
            )
            if generated.returncode != 0 or not baseline_path.is_file():
                raise RuntimeError(
                    f"solver failed for {instance_path} ({generated.returncode}): "
                    f"{generated.stderr.strip()}"
                )
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            internal_baseline = _internal_result(
                args.internal_checker, instance_path, baseline_path
            )
            if not internal_baseline.get("instance_valid"):
                raise RuntimeError(
                    f"internal instance validation failed for {instance_path}: "
                    f"{internal_baseline.get('instance_error', 'unknown error')}"
                )
            if not internal_baseline.get("solution_valid"):
                raise RuntimeError(
                    f"solver candidate is internally invalid for {instance_path}: "
                    f"{internal_baseline.get('solution_error', 'unknown error')}"
                )

            cases = candidate_cases(baseline, json.loads(instance_path.read_text()))
            for case_name, candidate in cases:
                candidate_path = candidates_dir / f"{uid}.{case_name}.solution.json"
                candidate_path.write_text(
                    json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                internal = _internal_result(
                    args.internal_checker, instance_path, candidate_path
                )
                if not internal.get("instance_valid"):
                    raise RuntimeError(
                        f"internal instance validation failed for {instance_path}: "
                        f"{internal.get('instance_error', 'unknown error')}"
                    )
                official = _official_result(official_instance, candidate_path)
                official_count += 1
                internal_valid = internal.get("solution_valid")
                if not isinstance(internal_valid, bool):
                    raise RuntimeError(
                        f"internal checker omitted solution validity for {candidate_path}"
                    )
                score_mismatch = (
                    internal_valid
                    and official["valid"]
                    and internal.get("makespan") != official["makespan"]
                )
                agrees = internal_valid == official["valid"] and not score_mismatch
                row = {
                    "instance": str(instance_path),
                    "saved_instance": str(saved_instance_path),
                    "case": case_name,
                    "candidate": str(candidate_path),
                    "internal_valid": internal_valid,
                    "internal_makespan": internal.get("makespan"),
                    "internal_error": internal.get("solution_error"),
                    "official_valid": official["valid"],
                    "official_makespan": official["makespan"],
                    "official_errors": official["errors"],
                    "agrees": agrees,
                }
                rows.append(row)
                if not agrees:
                    mismatch_count += 1
                    print(
                        f"MISMATCH {uid}/{case_name}: internal={internal_valid} "
                        f"official={official['valid']} "
                        f"internal_makespan={internal.get('makespan')} "
                        f"official_makespan={official['makespan']}",
                        file=sys.stderr,
                    )

        report = {
            "official_dependency": "cgshop2027-pyutils",
            "official_verification_skipped": False,
            "instances_checked": instance_count,
            "candidates_checked": len(rows),
            "official_checks": official_count,
            "agreements": len(rows) - mismatch_count,
            "mismatches": mismatch_count,
            "internal_valid_candidates": sum(row["internal_valid"] for row in rows),
            "internal_invalid_candidates": sum(not row["internal_valid"] for row in rows),
            "official_valid_candidates": sum(row["official_valid"] for row in rows),
            "official_invalid_candidates": sum(not row["official_valid"] for row in rows),
            "cases_by_name": {
                name: sum(row["case"] == name for row in rows)
                for name in sorted({row["case"] for row in rows})
            },
            "results": rows,
        }
        required_cases = {
            "outside-region-trajectory",
            "overlapping-cutter-trajectories",
            "repeated-closing-point",
            "swept-cutter-coverage",
            "turns-and-implicit-closure",
        }
        missing_cases = required_cases - set(report["cases_by_name"])
        if missing_cases:
            raise RuntimeError(
                "differential fixtures did not exercise required cases: "
                + ", ".join(sorted(missing_cases))
            )
        report_path = results_dir / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: differential validation aborted: {error}", file=sys.stderr)
        print(f"Artifacts retained at {results_dir}", file=sys.stderr)
        return 2

    print(
        f"Differential validation: {instance_count} instances, {len(rows)} candidates, "
        f"{official_count} official checks, {len(rows) - mismatch_count} agreements, "
        f"{mismatch_count} mismatches."
    )
    print(
        f"Internal: {report['internal_valid_candidates']} valid, "
        f"{report['internal_invalid_candidates']} invalid; official: "
        f"{report['official_valid_candidates']} valid, "
        f"{report['official_invalid_candidates']} invalid."
    )
    print(f"Results: {results_dir}")
    if official_count != len(rows):
        print("ERROR: not every candidate received official verification", file=sys.stderr)
        return 2
    if mismatch_count:
        print("Differential validation FAILED; mismatch artifacts were retained.")
        return 1
    print("Differential validation PASSED with official verification enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
