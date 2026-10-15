#!/usr/bin/env python3
"""Render validated swept cutter coverage, trajectories, and cutter geometry."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import struct
import zlib
from pathlib import Path
from typing import Any

from solution_metrics import makespan, tour_length


COLORS = (
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
    "#ff7f00", "#a65628", "#f781bf", "#555555",
)
RGB_COLORS = (
    (228, 26, 28), (55, 126, 184), (77, 175, 74), (152, 78, 163),
    (255, 127, 0), (166, 86, 40), (247, 129, 191), (85, 85, 85),
)
COVERAGE_COLORS = (
    (250, 190, 193), (180, 211, 242), (185, 226, 188), (218, 194, 226),
    (255, 221, 177), (223, 197, 180), (247, 203, 229), (205, 205, 205),
)
BACKGROUND = (250, 250, 248)
REGION_COLOR = (217, 226, 236)
UNCOVERED_COLOR = (255, 45, 45)
OVERLAP_COLOR = (185, 120, 210)
MAX_CELLS = 2_000_000
MAX_ROUTE_STEPS = 10_000_000
MAX_COVERAGE_OPERATIONS = 30_000_000


def _ring(item: Any, label: str) -> list[tuple[int, int]]:
    if not isinstance(item, dict):
        raise ValueError(f"{label} must be an object")
    xs, ys = item.get("x"), item.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        raise ValueError(f"{label} x and y must be equally sized arrays")
    points = []
    for x, y in zip(xs, ys):
        if (isinstance(x, bool) or not isinstance(x, int) or
                isinstance(y, bool) or not isinstance(y, int)):
            raise ValueError(f"{label} coordinates must be integers")
        points.append((x, y))
    if len(points) < 4:
        raise ValueError(f"{label} must have at least four vertices")
    if points[0] == points[-1]:
        raise ValueError(f"{label} must not repeat its implicit closing vertex")
    if any(a == b or (a[0] != b[0] and a[1] != b[1])
           for a, b in zip(points, points[1:] + points[:1])):
        raise ValueError(f"{label} must be simple rectilinear ring data")
    return points


def _inside(x: float, y: float, ring: list[tuple[int, int]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > y) != (previous[1] > y):
            crossing = (
                (previous[0] - current[0]) * (y - current[1]) /
                (previous[1] - current[1]) + current[0]
            )
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _raster(rings: list[list[tuple[int, int]]], label: str) -> set[tuple[int, int]]:
    min_x = min(x for ring in rings for x, _ in ring)
    max_x = max(x for ring in rings for x, _ in ring)
    min_y = min(y for ring in rings for _, y in ring)
    max_y = max(y for ring in rings for _, y in ring)
    area_bound = (max_x - min_x) * (max_y - min_y)
    if area_bound > MAX_CELLS:
        raise ValueError(
            f"{label} raster bounding box ({area_bound} cells) exceeds the "
            f"visualization limit of {MAX_CELLS}"
        )
    cells = set()
    for y in range(min_y, max_y):
        center_y = y + 0.5
        for x in range(min_x, max_x):
            center_x = x + 0.5
            if _inside(center_x, center_y, rings[0]) and not any(
                _inside(center_x, center_y, hole) for hole in rings[1:]
            ):
                cells.add((x, y))
    if not cells:
        raise ValueError(f"{label} has no rasterized cells")
    return cells


def _tour_points(tour: Any, index: int) -> list[tuple[int, int]]:
    if not isinstance(tour, dict):
        raise ValueError(f"tour {index} must be an object")
    xs, ys = tour.get("x"), tour.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        raise ValueError(f"tour {index} x and y must be equally sized arrays")
    points = []
    for x, y in zip(xs, ys):
        if (isinstance(x, bool) or not isinstance(x, int) or
                isinstance(y, bool) or not isinstance(y, int)):
            raise ValueError(f"tour {index} coordinates must be integers")
        points.append((x, y))
    if not points:
        raise ValueError(f"tour {index} must not be empty")
    return points


def coverage_model(instance: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    """Return exact integer-cell coverage corresponding to Problem::isCovered."""
    if not isinstance(instance, dict) or not isinstance(solution, dict):
        raise ValueError("instance and solution must be JSON objects")
    if instance.get("content_type") != "CGSHOP2027_Instance":
        raise ValueError("unsupported instance content_type")
    if solution.get("content_type") != "CGSHOP2027_Solution":
        raise ValueError("unsupported solution content_type")
    uid = instance.get("instance_uid")
    if not isinstance(uid, str) or solution.get("instance_uid") != uid:
        raise ValueError("solution instance_uid does not match instance")
    cutters = instance.get("number_of_cutters")
    if isinstance(cutters, bool) or not isinstance(cutters, int) or cutters < 1:
        raise ValueError("number_of_cutters must be a positive integer")
    center = instance.get("cutter_center")
    if (not isinstance(center, list) or len(center) != 2 or
            any(isinstance(value, bool) or not isinstance(value, int)
                for value in center)):
        raise ValueError("cutter_center must contain two integer coordinates")
    region_data = instance.get("region_to_cover")
    if not isinstance(region_data, dict):
        raise ValueError("region_to_cover must be an object")
    region_rings = [_ring(region_data.get("outer_boundary"), "outer boundary")]
    holes = region_data.get("inner_boundaries", [])
    if not isinstance(holes, list):
        raise ValueError("inner_boundaries must be an array")
    region_rings.extend(_ring(hole, f"inner boundary {index}")
                        for index, hole in enumerate(holes))
    cutter = _ring(instance.get("cutter"), "cutter")
    region_cells = _raster(region_rings, "region")
    cutter_cells = _raster([cutter], "cutter")
    tours_value = solution.get("tours")
    if not isinstance(tours_value, list) or len(tours_value) != cutters:
        raise ValueError("solution tour count does not match number_of_cutters")
    tours = [_tour_points(tour, index) for index, tour in enumerate(tours_value)]

    segment_steps = 0
    for tour in tours:
        if len(tour) > 1 and any(a == b for a, b in zip(tour, tour[1:] + tour[:1])):
            raise ValueError("tour contains an immediately repeated point")
        segment_steps += sum(
            abs(end[0] - start[0]) + abs(end[1] - start[1])
            for start, end in zip(tour, tour[1:] + tour[:1])
        )
    if segment_steps > MAX_ROUTE_STEPS:
        raise ValueError(
            f"route traversal ({segment_steps} lattice steps) exceeds "
            f"visualization limit {MAX_ROUTE_STEPS}"
        )
    if max(segment_steps, len(tours)) * len(cutter_cells) > MAX_COVERAGE_OPERATIONS:
        raise ValueError(
            "swept coverage exceeds visualization work limit "
            f"{MAX_COVERAGE_OPERATIONS}"
        )

    owners: dict[tuple[int, int], set[int]] = {}
    all_centers: list[list[tuple[int, int]]] = []
    for cutter_index, tour in enumerate(tours):
        centers: list[tuple[int, int]] = []
        edge_count = len(tour) if len(tour) > 1 else 1
        for edge_index in range(edge_count):
            start = tour[edge_index]
            end = tour[(edge_index + 1) % len(tour)] if len(tour) > 1 else start
            if start[0] != end[0] and start[1] != end[1]:
                raise ValueError(f"tour {cutter_index} contains a non-rectilinear edge")
            length = abs(end[0] - start[0]) + abs(end[1] - start[1])
            dx = 0 if start[0] == end[0] else (1 if end[0] > start[0] else -1)
            dy = 0 if start[1] == end[1] else (1 if end[1] > start[1] else -1)
            for step in range(length + 1):
                point = (start[0] + dx * step, start[1] + dy * step)
                if not centers or centers[-1] != point:
                    centers.append(point)
                for cell_x, cell_y in cutter_cells:
                    covered_cell = (
                        point[0] + cell_x - center[0],
                        point[1] + cell_y - center[1],
                    )
                    owners.setdefault(covered_cell, set()).add(cutter_index)
        all_centers.append(centers)

    covered_cells = set(owners)
    uncovered_cells = region_cells - covered_cells
    overlap_cells = {
        cell for cell, covering_cutters in owners.items()
        if cell in region_cells and len(covering_cutters) > 1
    }
    coverage_counts = [
        sum(index in owners.get(cell, set()) for cell in region_cells)
        for index in range(len(tours))
    ]
    route_lengths = [tour_length(tour_value) for tour_value in tours_value]
    return {
        "region_cells": region_cells,
        "cutter_cells": cutter_cells,
        "covered_cells": covered_cells,
        "uncovered_cells": uncovered_cells,
        "overlap_cells": overlap_cells,
        "owners": owners,
        "tours": tours,
        "centers": all_centers,
        "route_lengths": route_lengths,
        "coverage_counts_by_cutter": coverage_counts,
        "makespan": max(route_lengths),
        "valid": not uncovered_cells,
    }


def _safe(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or "item"


def safe_filename_component(value: str) -> str:
    readable = _safe(value)[:96]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"


def _grid_bounds(model: dict[str, Any]) -> tuple[int, int, int, int]:
    cells = set(model["region_cells"]) | set(model["covered_cells"])
    cells.update(point for tour in model["tours"] for point in tour)
    if not cells:
        return 0, 1, 0, 1
    min_x = min(x for x, _ in cells)
    max_x = max(x for x, _ in cells) + 1
    min_y = min(y for _, y in cells)
    max_y = max(y for _, y in cells) + 1
    return min_x, max_x, min_y, max_y


def render_svg(
    instance: dict[str, Any],
    solution: dict[str, Any],
    algorithm_id: str,
    status: str,
    animated: bool = False,
    title_override: str | None = None,
) -> str:
    model = coverage_model(instance, solution)
    if len(model["region_cells"]) > 200_000:
        raise ValueError("SVG snapshot exceeds the 200,000-region-cell limit")
    min_x, max_x, min_y, max_y = _grid_bounds(model)
    width_cells, height_cells = max_x - min_x, max_y - min_y
    scale = min(32.0, 1200.0 / max(width_cells, 1), 900.0 / max(height_cells, 1))
    scale = max(scale, 0.5)
    pad = 28
    width = max(
        math.ceil(width_cells * scale) + 2 * pad,
        pad + 560 + len(model["tours"]) * 110,
    )
    height = math.ceil(height_cells * scale) + 2 * pad + 65

    def tx(x: float) -> float:
        return pad + (x - min_x) * scale

    def ty(y: float) -> float:
        return pad + (max_y - y) * scale

    status_text = (
        "COVERAGE VALID"
        if model["valid"] else "COVERAGE INVALID: UNCOVERED CELLS"
    )
    title = title_override or (
        f"{instance['instance_uid']} | {algorithm_id} | {status} | "
        f"{status_text} | makespan={model['makespan']}"
    )
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<rect width='100%' height='100%' fill='#fafaf8'/>",
        f"<text x='{pad}' y='20' font-family='sans-serif' font-size='13' "
        f"font-weight='bold'>{html.escape(title)}</text>",
    ]
    for (x, y) in sorted(model["region_cells"]):
        svg.append(
            f"<rect x='{tx(x):.2f}' y='{ty(y+1):.2f}' width='{scale:.2f}' "
            f"height='{scale:.2f}' fill='#d9e2ec' stroke='#bbc7d3' stroke-width='.3'/>"
        )
    for cell in sorted(model["region_cells"]):
        covering = model["owners"].get(cell, set())
        if len(covering) == 1:
            x, y = cell
            color = COLORS[next(iter(covering)) % len(COLORS)]
            svg.append(
                f"<rect x='{tx(x):.2f}' y='{ty(y+1):.2f}' width='{scale:.2f}' "
                f"height='{scale:.2f}' fill='{color}' fill-opacity='.34' "
                "stroke='none'/>"
            )
    for cell in sorted(model["covered_cells"] - model["region_cells"]):
        x, y = cell
        svg.append(
            f"<rect x='{tx(x):.2f}' y='{ty(y+1):.2f}' width='{scale:.2f}' "
            f"height='{scale:.2f}' fill='#ffe2b8' stroke='#e4a84b' stroke-width='.3'/>"
        )
    for cell in sorted(model["overlap_cells"]):
        x, y = cell
        svg.append(
            f"<rect x='{tx(x):.2f}' y='{ty(y+1):.2f}' width='{scale:.2f}' "
            f"height='{scale:.2f}' fill='#d8a9df' stroke='#8f549b' stroke-width='.5'/>"
        )
    for cell in sorted(model["uncovered_cells"]):
        x, y = cell
        svg.append(
            f"<rect x='{tx(x):.2f}' y='{ty(y+1):.2f}' width='{scale:.2f}' "
            f"height='{scale:.2f}' fill='#ff2d2d' stroke='#9d0000' stroke-width='.7'/>"
        )

    cutter = _ring(instance.get("cutter"), "cutter")
    cutter_center = instance["cutter_center"]
    for index, tour in enumerate(model["tours"]):
        color = COLORS[index % len(COLORS)]
        points = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in tour)
        if len(tour) == 1:
            svg.append(
                f"<circle cx='{tx(tour[0][0]):.2f}' cy='{ty(tour[0][1]):.2f}' "
                f"r='{max(1.4, scale*.12):.2f}' fill='{color}'/>"
            )
        else:
            svg.append(
                f"<polyline points='{points} {tx(tour[0][0]):.2f},{ty(tour[0][1]):.2f}' "
                f"fill='none' stroke='{color}' stroke-width='{max(1.2, scale*.1):.2f}' "
                "stroke-dasharray='5 2' opacity='.9'/>"
            )
        first = tour[0]
        cutter_points = " ".join(
            f"{tx(first[0] + x - cutter_center[0]):.2f},"
            f"{ty(first[1] + y - cutter_center[1]):.2f}"
            for x, y in cutter
        )
        svg.append(
            f"<polygon points='{cutter_points}' fill='{color}' fill-opacity='.24' "
            f"stroke='{color}' stroke-width='1.5'><title>Cutter {index+1} geometry "
            "at first center position</title></polygon>"
        )
        if animated and len(tour) > 1:
            path_points = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in tour)
            path_points += f" {tx(tour[0][0]):.2f},{ty(tour[0][1]):.2f}"
            route_id = f"trajectory-{index}"
            svg.append(
                f"<polyline id='{route_id}' points='{path_points}' fill='none' "
                f"stroke='none'/>"
            )
            svg.append(
                f"<polygon points='{cutter_points}' fill='{color}' fill-opacity='.6' "
                f"stroke='{color}' stroke-width='1.5'><animateMotion dur='8s' "
                "repeatCount='indefinite' rotate='0'><mpath "
                f"xlink:href='#{route_id}'/></animateMotion></polygon>"
            )
        center = first
        svg.append(
            f"<circle cx='{tx(center[0]):.2f}' cy='{ty(center[1]):.2f}' "
            f"r='{max(2, scale*.16):.2f}' fill='{color}' stroke='white' "
            "stroke-width='1'><title>Start / cutter center</title></circle>"
        )
    legend_y = height - 27
    svg.append(
        f"<rect x='{pad}' y='{legend_y-12}' width='12' height='12' fill='#d9e2ec'/>"
        f"<text x='{pad+16}' y='{legend_y-2}' font-family='sans-serif' font-size='10'>"
        "target region</text>"
        f"<rect x='{pad+100}' y='{legend_y-12}' width='12' height='12' fill='#ff2d2d'/>"
        f"<text x='{pad+116}' y='{legend_y-2}' font-family='sans-serif' font-size='10'>"
        f"uncovered ({len(model['uncovered_cells'])})</text>"
        f"<rect x='{pad+238}' y='{legend_y-12}' width='12' height='12' fill='#d8a9df'/>"
        f"<text x='{pad+254}' y='{legend_y-2}' font-family='sans-serif' font-size='10'>"
        f"overlap ({len(model['overlap_cells'])})</text>"
        f"<line x1='{pad+360}' y1='{legend_y-6}' x2='{pad+386}' y2='{legend_y-6}' "
        "stroke='#333' stroke-width='2' stroke-dasharray='5 2'/>"
        f"<text x='{pad+392}' y='{legend_y-2}' font-family='sans-serif' font-size='10'>"
        "cutter-center trajectory (closed); coverage colors match cutter routes</text>"
    )
    for index, length in enumerate(model["route_lengths"]):
        svg.append(
            f"<text x='{pad+560+index*110}' y='{legend_y-2}' "
            f"font-family='sans-serif' font-size='10' fill='{COLORS[index % len(COLORS)]}'>"
            f"cutter {index+1}: L={length}, cells="
            f"{model['coverage_counts_by_cutter'][index]}</text>"
        )
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + kind + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def render_png(
    instance: dict[str, Any],
    solution: dict[str, Any],
    output: Path,
    status: str = "unknown",
    algorithm_id: str = "unknown",
) -> dict[str, Any]:
    model = coverage_model(instance, solution)
    min_x, max_x, min_y, max_y = _grid_bounds(model)
    width_cells, height_cells = max_x - min_x, max_y - min_y
    scale = max(1, min(6, 1200 // max(width_cells, 1), 900 // max(height_cells, 1)))
    pad = 12
    width = max(1, width_cells * scale + pad * 2)
    height = max(1, height_cells * scale + pad * 2)
    if width * height > 1_500_000:
        raise ValueError("PNG raster exceeds the 1.5-million-pixel safety limit")
    pixels = bytearray(BACKGROUND * (width * height))

    def pixel_bounds(cell: tuple[int, int]) -> tuple[int, int, int, int]:
        x, y = cell
        px = pad + (x - min_x) * scale
        py = pad + (max_y - y - 1) * scale
        return px, py, px + scale, py + scale

    def fill_cell(cell: tuple[int, int], color: tuple[int, int, int]) -> None:
        x0, y0, x1, y1 = pixel_bounds(cell)
        row = bytes(color) * (x1 - x0)
        for py in range(y0, y1):
            start = (py * width + x0) * 3
            pixels[start:start + len(row)] = row

    for cell in model["region_cells"]:
        fill_cell(cell, REGION_COLOR)
    for cell in model["region_cells"]:
        covering = model["owners"].get(cell, set())
        if len(covering) == 1:
            fill_cell(cell, COVERAGE_COLORS[next(iter(covering)) % len(COVERAGE_COLORS)])
    for cell in model["covered_cells"] - model["region_cells"]:
        fill_cell(cell, (255, 226, 184))
    for cell in model["overlap_cells"]:
        fill_cell(cell, OVERLAP_COLOR)
    for cell in model["uncovered_cells"]:
        fill_cell(cell, UNCOVERED_COLOR)

    def set_pixel(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)

    def transformed(point: tuple[int, int]) -> tuple[int, int]:
        return (
            pad + (point[0] - min_x) * scale,
            pad + (max_y - point[1]) * scale,
        )

    for index, tour in enumerate(model["tours"]):
        path = [transformed(point) for point in tour]
        if len(path) == 1:
            set_pixel(*path[0], RGB_COLORS[index % len(RGB_COLORS)])
            continue
        color = RGB_COLORS[index % len(RGB_COLORS)]
        for start, end in zip(path, path[1:] + path[:1]):
            x0, y0 = start
            x1, y1 = end
            dx, dy = abs(x1 - x0), -abs(y1 - y0)
            sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
            error = dx + dy
            while True:
                set_pixel(x0, y0, color)
                if (x0, y0) == (x1, y1):
                    break
                twice = 2 * error
                if twice >= dy:
                    error += dy
                    x0 += sx
                if twice <= dx:
                    error += dx
                    y0 += sy

    raw = b"".join(
        b"\x00" + bytes(pixels[row * width * 3:(row + 1) * width * 3])
        for row in range(height)
    )
    title = (
        f"{instance['instance_uid']} | {algorithm_id} | {status} | "
        f"{'COVERAGE VALID' if model['valid'] else 'COVERAGE INVALID: UNCOVERED CELLS'} | "
        f"makespan={model['makespan']}"
    )
    description = (
        f"route_lengths={model['route_lengths']}; "
        f"region_cells_covered_by_cutter={model['coverage_counts_by_cutter']}; "
        f"uncovered_cells={len(model['uncovered_cells'])}; "
        f"overlap_cells={len(model['overlap_cells'])}; "
        "cell colors match the cutter route colors"
    )
    output.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"tEXt", b"Title\x00" + title.encode("utf-8"))
        + _png_chunk(b"tEXt", b"Description\x00" + description.encode("utf-8"))
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )
    return {
        "coverage_valid": model["valid"],
        "uncovered_cell_count": len(model["uncovered_cells"]),
        "overlap_cell_count": len(model["overlap_cells"]),
        "route_lengths": model["route_lengths"],
        "coverage_counts_by_cutter": model["coverage_counts_by_cutter"],
        "makespan": model["makespan"],
        "status": status,
        "algorithm_id": algorithm_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="output PNG path")
    parser.add_argument("--algorithm-id", default="unknown")
    parser.add_argument("--status", default="unknown",
                        help="trial/validation status shown on SVG/animation")
    parser.add_argument("--svg", type=Path,
                        help="optional descriptive SVG snapshot output")
    parser.add_argument("--animate", type=Path,
                        help="optional animated SVG output")
    parser.add_argument("--report", type=Path,
                        help="optional JSON visualization validation report")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    outputs = [args.output, args.svg, args.animate, args.report]
    selected = [path for path in outputs if path is not None]
    for path in selected:
        if path.resolve() in {args.instance.resolve(), args.solution.resolve()}:
            parser.error(f"visualization output must not overwrite input: {path}")
        if path.exists() and not args.overwrite:
            parser.error(f"refusing to overwrite visualization: {path}")
    try:
        instance = json.loads(args.instance.read_text(encoding="utf-8"))
        solution = json.loads(args.solution.read_text(encoding="utf-8"))
        model = coverage_model(instance, solution)
        report = render_png(
            instance, solution, args.output, args.status, args.algorithm_id
        )
        report["algorithm_id"] = args.algorithm_id
        report["uncovered_cells"] = [list(cell) for cell in sorted(model["uncovered_cells"])]
        if args.svg:
            args.svg.write_text(
                render_svg(instance, solution, args.algorithm_id, args.status),
                encoding="utf-8",
            )
        if args.animate:
            args.animate.write_text(
                render_svg(
                    instance, solution, args.algorithm_id, args.status, animated=True
                ),
                encoding="utf-8",
            )
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(
        f"wrote {args.output}: {'valid coverage' if model['valid'] else 'INVALID coverage'}, "
        f"uncovered={len(model['uncovered_cells'])}, makespan={model['makespan']}"
    )
    return 0 if model["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
