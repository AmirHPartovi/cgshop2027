#!/usr/bin/env python3
"""Render swept coverage, cutter geometry, and closed cutter-center routes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from visualize_solution import render_svg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--algorithm-id", default="unknown")
    parser.add_argument("--status", default="VALID_FEASIBLE; OFFICIAL_CHECKER_UNAVAILABLE")
    parser.add_argument("--animate", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = args.output or args.solution.with_suffix(".svg")
    if output.resolve() in {args.instance.resolve(), args.solution.resolve()}:
        parser.error(f"visualization output must not overwrite input: {output}")
    if output.exists() and not args.overwrite:
        parser.error(f"refusing to overwrite visualization: {output}")
    try:
        instance = json.loads(args.instance.read_text(encoding="utf-8"))
        solution = json.loads(args.solution.read_text(encoding="utf-8"))
        output.write_text(
            render_svg(
                instance,
                solution,
                args.algorithm_id,
                args.status,
                animated=args.animate,
                title_override=args.title or None,
            ),
            encoding="utf-8",
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
