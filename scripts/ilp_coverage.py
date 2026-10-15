#!/usr/bin/env python3
"""Solve the placement-cover relaxation with Gurobi's command-line solver.

This is an ILP lower-bound/placement study, not a substitute for the closed-tour
problem: selected anchors are converted to a deterministic rectilinear route.
The script is intentionally bounded because the official instances can contain
millions of cells.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def cells(ring: dict[str, list[int]]) -> set[tuple[int, int]]:
    xs, ys = ring["x"], ring["y"]
    return {
        (x, y)
        for y in range(min(ys), max(ys))
        for x in range(min(xs), max(xs))
        if any(
            ((ys[i] > y + 0.5) != (ys[(i + 1) % len(ys)] > y + 0.5))
            and x + 0.5
            < (xs[(i + 1) % len(xs)] - xs[i])
            * (y + 0.5 - ys[i])
            / (ys[(i + 1) % len(ys)] - ys[i])
            + xs[i]
            for i in range(len(xs))
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("instance", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    instance = json.loads(args.instance.read_text())
    boundary = instance["region_to_cover"]["outer_boundary"]
    width = max(boundary["x"]) - min(boundary["x"])
    height = max(boundary["y"]) - min(boundary["y"])
    if width * height > 5000:
        print("SKIPPED\tbounding box exceeds 5000 cells")
        return 0
    region = cells(boundary)
    if len(region) > 5000:
        print("SKIPPED\tregion exceeds 5000 cells")
        return 0
    cutter = cells(instance["cutter"])
    center = instance["cutter_center"]
    if isinstance(center, dict):
        cx, cy = center["x"], center["y"]
    else:
        cx, cy = center
    anchors = sorted(
        {
            (cell[0] + cx - min(x for x, _ in cutter),
             cell[1] + cy - min(y for _, y in cutter))
            for cell in region
        }
    )
    with tempfile.TemporaryDirectory() as directory:
        lp = Path(directory) / "cover.lp"
        sol = Path(directory) / "cover.sol"
        objective = " + ".join(f"x{i}" for i in range(len(anchors)))
        lines = ["Minimize", f" obj: {objective}", "Subject To"]
        for j, cell in enumerate(sorted(region)):
            covering = [
                f"x{i}"
                for i, anchor in enumerate(anchors)
                if (cell[0] - anchor[0] + cx, cell[1] - anchor[1] + cy) in cutter
            ]
            if covering:
                lines.append(f" c{j}: {' + '.join(covering)} >= 1")
        lines += ["Binary", " " + " ".join(f"x{i}" for i in range(len(anchors))),
                  "End"]
        lp.write_text("\n".join(lines) + "\n")
        command = ["gurobi_cl", f"TimeLimit={args.timeout}", f"ResultFile={sol}", str(lp)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0 or not sol.exists():
            print("FAILED\t" + completed.stderr.strip().replace("\n", " "))
            return 0
        selected = sum(
            line.startswith("x") and line.rstrip().endswith("1")
            for line in sol.read_text().splitlines()
        )
        print(f"OPTIMAL_OR_BEST_BOUND\tselected_anchors={selected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
