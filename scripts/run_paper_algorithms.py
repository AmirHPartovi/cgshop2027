#!/usr/bin/env python3
"""Run each paper algorithm on selected fixtures, validate, and plot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ALGORITHMS = (
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

INSTANCES = (
    "fpg73_1k_1s2.instance.json",
    "fpg73_1k_3s2.instance.json",
    "srpg_246_821_1s3.instance.json",
)


def tour_length(tour: dict) -> int:
    points = list(zip(tour["x"], tour["y"]))
    if len(points) < 2:
        return 0
    return sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(points, points[1:] + points[:1])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, default=Path("build/bin/solver"))
    parser.add_argument("--instances", type=Path, default=Path("data/test"))
    parser.add_argument("--output", type=Path, default=Path("build/paper-algorithms"))
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    visualize = root / "scripts" / "visualize.py"
    validate = root / "scripts" / "validate.py"
    args.output.mkdir(parents=True, exist_ok=True)
    rows = ["instance_uid\talgorithm\tvalid_cpp\tofficial\tmakespan\tsvg"]
    official_ok = False
    try:
        subprocess.run(
            [sys.executable, "-c", "import cgshop2027_pyutils"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        official_ok = True
    except subprocess.CalledProcessError:
        official_ok = False

    for instance_name in INSTANCES:
        instance = args.instances / instance_name
        if not instance.exists():
            continue
        uid = instance_name.removesuffix(".instance.json")
        for algorithm in ALGORITHMS:
            solution_path = args.output / f"{uid}.{algorithm}.solution.json"
            svg_path = args.output / f"{uid}.{algorithm}.svg"
            command = [
                str(args.solver),
                "-i",
                str(instance),
                "-o",
                str(solution_path),
                "-a",
                algorithm,
                "-t",
                str(args.timeout),
            ]
            cpp_valid = "False"
            official = "skipped"
            makespan = ""
            try:
                subprocess.run(command, check=True, timeout=args.timeout + 15)
                solution = json.loads(solution_path.read_text())
                makespan = str(
                    max((tour_length(tour) for tour in solution["tours"]), default=0)
                )
                cpp_valid = "True"
                subprocess.run(
                    [sys.executable, str(visualize), str(instance), str(solution_path),
                     "-o", str(svg_path), "--title", f"{uid} / {algorithm} / {makespan}"],
                    check=True,
                )
                if official_ok:
                    official_proc = subprocess.run(
                        [sys.executable, str(validate), str(instance), str(solution_path)],
                        check=False,
                    )
                    official = "True" if official_proc.returncode == 0 else "False"
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
                svg_path = Path("")
                print(f"FAIL {uid} {algorithm}: {error}", file=sys.stderr)
            rows.append(
                f"{uid}\t{algorithm}\t{cpp_valid}\t{official}\t{makespan}\t{svg_path}"
            )
            print(f"{uid}\t{algorithm}\t{cpp_valid}\t{official}\t{makespan}")

    table = args.output / "summary.tsv"
    table.write_text("\n".join(rows) + "\n")
    print(f"wrote {table}")
    return 0 if all(row.split("\t")[2] == "True" for row in rows[1:]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
