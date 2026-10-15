#!/usr/bin/env python3
"""Create a machine-readable comparison of all available solution artifacts."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from solution_metrics import makespan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solutions", type=Path, default=Path("build/candidates"))
    parser.add_argument("--output", type=Path, default=Path("build/results.tsv"))
    args = parser.parse_args()
    rows: list[tuple[str, str, str, str, str]] = []
    for path in sorted(args.solutions.glob("*.solution.json")):
        name = path.name.removesuffix(".solution.json")
        pieces = name.split(".")
        instance = pieces[0]
        algorithm = ".".join(pieces[1:]) or "unknown"
        started = time.monotonic()
        try:
            solution = json.loads(path.read_text())
            score = str(makespan(solution))
            status = "parsed"
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            score = ""
            status = "invalid-json"
        elapsed = f"{time.monotonic() - started:.6f}"
        rows.append((instance, algorithm, status, score, elapsed))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "instance_uid\talgorithm\tstatus\tmakespan\tanalysis_seconds\tsolution_path\n"
        + "\n".join("\t".join((*row, str(args.solutions / f"{row[0]}.{row[1]}.solution.json")))
                    for row in rows)
        + "\n"
    )
    print(f"wrote {len(rows)} solution rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
