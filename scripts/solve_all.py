#!/usr/bin/env python3
"""Solve, validate, plot, and compare every instance with every algorithm."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path


ALGORITHMS = (
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


def points(item: dict) -> list[tuple[int, int]]:
    return list(zip(item.get("x", []), item.get("y", [])))


def tour_length(tour: dict) -> int:
    path = points(tour)
    if len(path) < 2:
        return 0
    return sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(path, path[1:] + path[:1])
    )


def makespan(solution: dict) -> int:
    return max((tour_length(tour) for tour in solution.get("tours", [])), default=0)


def inside(x: float, y: float, polygon: list[tuple[int, int]]) -> bool:
    result = False
    for index, first in enumerate(polygon):
        second = polygon[index - 1]
        if (first[1] > y) != (second[1] > y):
            crossing = (second[0] - first[0]) * (y - first[1]) / (
                second[1] - first[1]
            ) + first[0]
            if x < crossing:
                result = not result
    return result


def set_pixel(image: bytearray, width: int, height: int, x: int, y: int,
              color: tuple[int, int, int]) -> None:
    if 0 <= x < width and 0 <= y < height:
        offset = (y * width + x) * 3
        image[offset : offset + 3] = bytes(color)


def line(image: bytearray, width: int, height: int, start: tuple[int, int],
         end: tuple[int, int], color: tuple[int, int, int]) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        set_pixel(image, width, height, x0, y0, color)
        if (x0, y0) == (x1, y1):
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + bytes(pixels[row * width * 3 : (row + 1) * width * 3])
        for row in range(height)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def render_png(instance: dict, solution: dict, output: Path) -> None:
    region = instance["region_to_cover"]
    polygons = [points(region["outer_boundary"])] + [
        points(hole) for hole in region.get("inner_boundaries", [])
    ]
    tours = [points(tour) for tour in solution.get("tours", [])]
    all_points = [point for polygon in polygons for point in polygon]
    all_points.extend(point for tour in tours for point in tour)
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)
    scale = min(360 / span_x, 260 / span_y)
    width = max(120, min(360, math.ceil((max_x - min_x + 4) * scale)))
    height = max(90, min(260, math.ceil((max_y - min_y + 4) * scale)))

    def transform(point: tuple[int, int]) -> tuple[int, int]:
        return (
            round((point[0] - min_x + 2) * scale),
            round((max_y - point[1] + 2) * scale),
        )

    pixels = bytearray((248, 249, 247) * (width * height))
    outer = polygons[0]
    holes = polygons[1:]
    for py in range(height):
        for px in range(width):
            x = min_x - 2 + (px + 0.5) / scale
            y = max_y + 2 - (py + 0.5) / scale
            if inside(x, y, outer) and not any(inside(x, y, hole) for hole in holes):
                set_pixel(pixels, width, height, px, py, (217, 226, 236))

    colors = (
        (228, 26, 28), (55, 126, 184), (77, 175, 74), (152, 78, 163),
        (255, 127, 0), (166, 86, 40), (247, 129, 191), (80, 80, 80),
    )
    for index, tour in enumerate(tours):
        if not tour:
            continue
        color = colors[index % len(colors)]
        path = [transform(point) for point in tour]
        for start, end in zip(path, path[1:] + path[:1]):
            line(pixels, width, height, start, end, color)
    write_png(output, width, height, pixels)


def official_validator_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-c", "import cgshop2027_pyutils"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def run_bounded(command: list[str], timeout: float, memory_mb: int
                ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    """Run a solver and stop it when either resource limit is reached."""
    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            start_new_session=(os.name == "posix"),
        )
        deadline = time.monotonic() + timeout
        memory_limit_kib = memory_mb * 1024
        limit_error = None
        while process.poll() is None:
            if time.monotonic() >= deadline:
                limit_error = f"time_limit: exceeded {timeout:g}s"
                break
            try:
                rss = int(subprocess.check_output(
                    ["ps", "-o", "rss=", "-p", str(process.pid)],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip() or "0")
            except (OSError, subprocess.SubprocessError, ValueError):
                rss = 0
            if rss > memory_limit_kib:
                limit_error = f"memory_limit: exceeded {memory_mb} MiB"
                break
            time.sleep(0.05)
        if limit_error:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        process.wait()
        stderr_file.seek(0)
        stderr = stderr_file.read().decode(errors="replace")
        if limit_error:
            return None, limit_error
        return subprocess.CompletedProcess(
            command, process.returncode, "", stderr
        ), None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and compare all algorithms on all *.instance.json files."
    )
    parser.add_argument("--solver", type=Path, default=Path("build/bin/solver"))
    parser.add_argument("--instances", type=Path, default=Path("data/test"))
    parser.add_argument("--output", type=Path, default=Path("build/all-results"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--official-timeout",
        type=float,
        default=30.0,
        help="official-validator timeout per run in seconds (default: 30)",
    )
    parser.add_argument("--memory", type=int, default=2048,
                        help="per-run memory limit in MiB (default: 2048)")
    parser.add_argument(
        "--master-table",
        type=Path,
        default=None,
        help="wide comparison table path (default: <instances>/master-table.tsv)",
    )
    parser.add_argument(
        "--algorithms",
        default=",".join(ALGORITHMS),
        help="comma-separated algorithm names (default: all built-in algorithms)",
    )
    parser.add_argument("--official", action="store_true",
                        help="also run cgshop2027_pyutils when installed")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    algorithms = tuple(
        algorithm.strip()
        for algorithm in args.algorithms.split(",")
        if algorithm.strip()
    )
    unknown = sorted(set(algorithms) - set(ALGORITHMS))
    if unknown:
        parser.error("unknown algorithms: " + ", ".join(unknown))
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.official_timeout <= 0:
        parser.error("--official-timeout must be positive")
    if args.memory <= 0:
        parser.error("--memory must be positive")
    instances = sorted(args.instances.glob("*.instance.json"))
    master_table = args.master_table or args.instances / "master-table.tsv"
    if args.official and not official_validator_available():
        parser.error(
            "--official requires the cgshop2027_pyutils package in the "
            "selected Python interpreter"
        )
    use_official = args.official
    validate_script = Path(__file__).with_name("validate.py")
    long_rows: list[dict[str, str]] = []

    # Keep the outer loop algorithm-first so every algorithm is evaluated over
    # the complete instance set, while each instance/algorithm run remains
    # independently bounded.
    for algorithm in algorithms:
        for instance_path in instances:
            uid = instance_path.name.removesuffix(".instance.json")
            instance = json.loads(instance_path.read_text())
            solution_path = args.output / f"{uid}.{algorithm}.solution.json"
            figure_path = args.output / f"{uid}.{algorithm}.png"
            started = time.monotonic()
            row = {
                "instance_uid": uid,
                "algorithm": algorithm,
                "status": "failed",
                "valid": "false",
                "official_valid": "skipped",
                "makespan": "",
                "seconds": "",
                "solution": str(solution_path),
                "figure": str(figure_path),
                "time_limit_seconds": str(args.timeout),
                "memory_limit_mib": str(args.memory),
                "error": "",
            }
            try:
                solution_path.unlink(missing_ok=True)
                completed, limit_error = run_bounded(
                    [str(args.solver), "-i", str(instance_path), "-o",
                     str(solution_path), "-a", algorithm, "-t", str(args.timeout)],
                    args.timeout, args.memory,
                )
                if limit_error:
                    row["status"] = limit_error.split(":", 1)[0]
                    row["error"] = limit_error
                    raise RuntimeError(limit_error)
                assert completed is not None
                if completed.returncode != 0:
                    if completed.returncode < 0 and -completed.returncode == signal.SIGKILL:
                        row["status"] = "memory_limit"
                    else:
                        row["status"] = "failed"
                    row["error"] = completed.stderr.strip()
                    raise RuntimeError(row["error"] or
                                       f"solver exited with {completed.returncode}")
                solution = json.loads(solution_path.read_text())
                row["makespan"] = str(makespan(solution))
                render_png(instance, solution, figure_path)
                if use_official:
                    try:
                        official = subprocess.run(
                            [sys.executable, str(validate_script),
                             str(instance_path), str(solution_path)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=args.official_timeout,
                        )
                    except subprocess.TimeoutExpired:
                        row["status"] = "official_time_limit"
                        row["error"] = (
                            f"official validator exceeded "
                            f"{args.official_timeout:g}s"
                        )
                        raise RuntimeError(row["error"])
                    row["official_valid"] = str(official.returncode == 0).lower()
                    if official.returncode != 0:
                        row["status"] = "official_invalid"
                        row["error"] = official.stdout.strip()
                        raise RuntimeError(
                            row["error"] or "official validator rejected solution"
                        )
                row["status"] = "ok"
                row["valid"] = "true"
            except subprocess.TimeoutExpired as error:
                row["status"] = "time_limit"
                row["error"] = f"exceeded {args.timeout:g}s"
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError,
                    KeyError, IndexError, ZeroDivisionError) as error:
                if not row["error"]:
                    row["error"] = str(error)
            row["seconds"] = f"{time.monotonic() - started:.3f}"
            long_rows.append(row)
            print(f"{uid}\t{algorithm}\t{row['status']}\t{row['makespan']}")

    fields = ("instance_uid", "algorithm", "status", "valid", "official_valid",
              "makespan", "seconds", "time_limit_seconds", "memory_limit_mib",
              "solution", "figure", "error")
    detailed = args.output / "all-results.tsv"
    detailed.write_text(
        "\t".join(fields) + "\n"
        + "\n".join("\t".join(row[field].replace("\t", " ")
                               for field in fields) for row in long_rows)
        + "\n"
    )

    by_instance = {uid: {} for uid in (row["instance_uid"] for row in long_rows)}
    for row in long_rows:
        by_instance[row["instance_uid"]][row["algorithm"]] = (
            row["makespan"] if row["status"] == "ok" else row["status"].upper()
        )
    master_table.parent.mkdir(parents=True, exist_ok=True)
    master_table.write_text(
        "instance_uid\t" + "\t".join(algorithms) + "\n"
        + "\n".join(
            uid + "\t" + "\t".join(by_instance[uid].get(algorithm, "NOT_RUN")
                                    for algorithm in algorithms)
            for uid in sorted(by_instance)
        )
        + "\n"
    )
    ok = sum(row["status"] == "ok" for row in long_rows)
    print(f"completed {ok}/{len(long_rows)} runs")
    print(f"detailed results: {detailed}")
    print(f"master table: {master_table}")
    return 0 if ok == len(long_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
