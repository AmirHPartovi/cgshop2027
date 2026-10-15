#!/usr/bin/env python3
"""Validate every candidate with pyutils27 and emit a comparison TSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from cgshop2027_pyutils.io import read_instance, read_solution
from cgshop2027_pyutils.verify import check_for_errors


def length(solution: object) -> int:
    return max(
        (
            sum(
                abs(a - b) + abs(c - d)
                for (a, c), (b, d) in zip(
                    zip(tour.x, tour.y), zip([*tour.x[1:], tour.x[0]],
                                              [*tour.y[1:], tour.y[0]]))
            )
            for tour in solution.tours
        ),
        default=0,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=Path, default=Path("data/test"))
    parser.add_argument("--solutions", type=Path, default=Path("build/candidates"))
    parser.add_argument("--output", type=Path, default=Path("build/evaluation.tsv"))
    args = parser.parse_args()
    rows = ["instance_uid\talgorithm\tvalid\tmakespan\terror"]
    for instance_path in sorted(args.instances.glob("*.instance.json")):
        uid = instance_path.name.removesuffix(".instance.json")
        instance = read_instance(instance_path)
        candidates = sorted(args.solutions.glob(f"{uid}*.solution.json"))
        for candidate in candidates:
            stem = candidate.name.removeprefix(uid + ".")
            algorithm = stem[: -len(".solution.json")] or "reference"
            try:
                solution = read_solution(candidate)
                errors = check_for_errors(instance, solution)
                rows.append(
                    f"{uid}\t{algorithm}\t{not errors}\t{length(solution)}\t"
                    f"{' '.join(errors)}"
                )
            except (OSError, ValueError, TypeError) as error:
                rows.append(f"{uid}\t{algorithm}\tFalse\t\t{error}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(rows) + "\n")
    print(f"wrote {len(rows) - 1} official evaluation rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
