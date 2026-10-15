#!/usr/bin/env python3
"""Render an instance polygon and cutter tours as an SVG plot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


COLORS = (
    "#e41a1c",
    "#377eb8",
    "#4daf4a",
    "#984ea3",
    "#ff7f00",
    "#a65628",
    "#f781bf",
    "#999999",
)


def polygon_points(item: dict) -> list[tuple[int, int]]:
    return list(zip(item["x"], item["y"]))


def tour_length(tour: dict) -> int:
    points = polygon_points(tour)
    if len(points) < 2:
        return 0
    return sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(points, points[1:] + points[:1])
    )


def bounds(instance: dict, solution: dict) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    region = instance["region_to_cover"]
    for x, y in polygon_points(region["outer_boundary"]):
        xs.append(x)
        ys.append(y)
    for tour in solution.get("tours", []):
        xs.extend(tour["x"])
        ys.extend(tour["y"])
    return min(xs), min(ys), max(xs), max(ys)


def poly_attr(points: list[tuple[int, int]]) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("instance", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    instance = json.loads(args.instance.read_text())
    solution = json.loads(args.solution.read_text())
    min_x, min_y, max_x, max_y = bounds(instance, solution)
    pad = 2
    width = max(max_x - min_x + 2 * pad, 1)
    height = max(max_y - min_y + 2 * pad, 1)
    makespan = max((tour_length(tour) for tour in solution.get("tours", [])), default=0)
    title = args.title or f"{instance.get('instance_uid', '')}  makespan={makespan}"
    output = args.output
    if output is None:
        output = args.solution.with_suffix(".svg")

    def tx(x: int) -> float:
        return x - min_x + pad

    def ty(y: int) -> float:
        return max_y - y + pad

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{min(1100, 18 * width)}" height="{min(800, 18 * height)}">',
        "<rect width='100%' height='100%' fill='#f7f7f4'/>",
    ]
    region = instance["region_to_cover"]
    outer = [(tx(x), ty(y)) for x, y in polygon_points(region["outer_boundary"])]
    svg.append(
        f'<polygon points="{poly_attr(outer)}" fill="#d9e2ec" stroke="#243b53" '
        'stroke-width="0.08" fill-rule="evenodd">'
    )
    holes = []
    for hole in region.get("inner_boundaries", []):
        holes.append([(tx(x), ty(y)) for x, y in polygon_points(hole)])
        svg.append(f'<polygon points="{poly_attr(holes[-1])}"/>')
    svg.append("</polygon>")
    for hole in holes:
        svg.append(
            f'<polygon points="{poly_attr(hole)}" fill="#f7f7f4" stroke="#829ab1" '
            'stroke-width="0.05"/>'
        )
    for index, tour in enumerate(solution.get("tours", [])):
        points = [(tx(x), ty(y)) for x, y in polygon_points(tour)]
        if not points:
            continue
        color = COLORS[index % len(COLORS)]
        closed = points + points[:1]
        svg.append(
            f'<polyline points="{poly_attr(closed)}" fill="none" stroke="{color}" '
            f'stroke-width="0.12" stroke-linejoin="round" opacity="0.95"/>'
        )
        svg.append(
            f'<circle cx="{points[0][0]}" cy="{points[0][1]}" r="0.22" fill="{color}"/>'
        )
    svg.append(
        f'<text x="{pad}" y="1.2" font-size="1.1" font-family="sans-serif" fill="#102a43">'
        f"{title}</text>"
    )
    svg.append("</svg>")
    output.write_text("\n".join(svg) + "\n")
    print(f"wrote {output} (makespan={makespan})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
