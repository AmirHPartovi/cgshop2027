#!/usr/bin/env python3
"""Officially validate candidate solutions and emit a comparison TSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=Path, default=ROOT / "data/test")
    parser.add_argument("--solutions", type=Path, default=ROOT / "build/candidates")
    parser.add_argument("--output", type=Path, default=ROOT / "build/evaluation.tsv")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="allow replacing an existing evaluation report",
    )
    args = parser.parse_args()

    try:
        from cgshop2027_pyutils.io import read_instance, read_solution
        from cgshop2027_pyutils.verify import check_for_errors
    except ImportError as error:
        parser.error(f"official validator dependency unavailable: {error}")
    if not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    if not args.solutions.is_dir():
        parser.error(f"solution directory does not exist: {args.solutions}")
    instance_paths = sorted(args.instances.glob("*.instance.json"))
    if not instance_paths:
        parser.error(f"no *.instance.json inputs found in {args.instances}")
    if args.output.exists() and not args.overwrite:
        parser.error(f"output already exists: {args.output} (pass --overwrite)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = ["instance_uid\talgorithm\tvalid\tmakespan\terror"]
    failed = 0
    for instance_path in instance_paths:
        uid = instance_path.name.removesuffix(".instance.json")
        candidates = sorted(args.solutions.glob(f"{uid}*.solution.json"))
        if not candidates:
            rows.append(f"{uid}\t\tFalse\t\tNO_SOLUTION")
            failed += 1
            print(f"FAIL {uid}: no corresponding solution artifact", file=sys.stderr)
            continue
        try:
            instance = read_instance(instance_path)
        except (OSError, ValueError, TypeError, KeyError) as error:
            rows.append(f"{uid}\t\tFalse\t\tINVALID_INSTANCE: {error}")
            failed += len(candidates)
            print(f"FAIL {uid}: invalid instance {instance_path}: {error}",
                  file=sys.stderr)
            continue
        for candidate in candidates:
            stem = candidate.name.removeprefix(uid + ".")
            algorithm = stem[: -len(".solution.json")] or "reference"
            try:
                solution = read_solution(candidate)
                errors = check_for_errors(instance, solution)
                score = solution.max_tour_length if not errors else ""
                valid = not errors
                rows.append(
                    f"{uid}\t{algorithm}\t{valid}\t{score}\t"
                    f"{' '.join(str(error) for error in errors)}"
                )
                if errors:
                    failed += 1
                    print(f"FAIL {uid} {algorithm}: {'; '.join(map(str, errors))}",
                          file=sys.stderr)
            except (OSError, ValueError, TypeError, KeyError) as error:
                rows.append(f"{uid}\t{algorithm}\tFalse\t\t{error}")
                failed += 1
                print(f"FAIL {uid} {algorithm}: {error}", file=sys.stderr)

    args.output.write_text("\n".join(rows) + "\n")
    print(f"wrote {len(rows) - 1} official evaluation rows to {args.output}")
    if failed:
        print(f"official evaluation had {failed} failure(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
