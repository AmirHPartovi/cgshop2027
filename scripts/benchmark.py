#!/usr/bin/env python3
"""Run every configured algorithm and record the best local result."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def tour_length(tour: dict[str, list[int]]) -> int:
    points = list(zip(tour["x"], tour["y"]))
    if len(points) < 2:
        return 0
    return sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(points, [*points[1:], points[0]])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, default=Path("build/bin/solver"))
    parser.add_argument("--instances", type=Path, default=Path("data/test"))
    parser.add_argument("--output", type=Path, default=Path("build/benchmark.tsv"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    algorithms = (
        "strip",
        "partition",
        "local",
        "anchor-cover",
        "balanced-greedy",
        "boustrophedon",
        "stc",
        "tsp-cov",
        "frederickson",
        "mstc",
        "region-partition",
        "ilp",
        "column-gen",
        "lns",
        "hybrid",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str, str]] = []
    for instance in sorted(args.instances.glob("*.instance.json")):
        uid = instance.name.removesuffix(".instance.json")
        best: tuple[int, str, Path] | None = None
        for algorithm in algorithms:
            output = args.output.parent / f"{uid}.{algorithm}.solution.json"
            command = [
                str(args.solver),
                "-i",
                str(instance),
                "-o",
                str(output),
                "-a",
                algorithm,
                "-t",
                str(args.timeout),
            ]
            try:
                subprocess.run(command, check=True, timeout=args.timeout + 5)
                solution = json.loads(output.read_text())
                score = max((tour_length(tour) for tour in solution["tours"]), default=0)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError):
                continue
            if best is None or score < best[0]:
                best = (score, algorithm, output)
        if best is None:
            rows.append((uid, "FAILED", "", ""))
        else:
            best_path = args.output.parent / f"{uid}.best.solution.json"
            best_path.write_bytes(best[2].read_bytes())
            rows.append((uid, str(best[0]), best[1], str(best_path)))

    args.output.write_text(
        "instance_uid\tmakespan\talgorithm\tbest_solution\n"
        + "\n".join("\t".join(row) for row in rows)
        + "\n"
    )
    print(f"wrote {len(rows)} benchmark rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
