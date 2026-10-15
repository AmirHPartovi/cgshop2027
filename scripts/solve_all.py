#!/usr/bin/env python3
"""Solve, validate, plot, and compare every instance with every algorithm."""

from __future__ import annotations

import argparse
import copy
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

from benchmark import process_tree_snapshot
from runtime_config import ROOT, load_runtime_config
from solution_metrics import makespan


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
                ) -> tuple[subprocess.CompletedProcess[str] | None, str | None,
                           dict[str, object]]:
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
        started = time.monotonic()
        peak_rss_kib = None
        process_tree_cpu_seconds = None
        rss_samples = 0
        cpu_samples = 0
        while process.poll() is None:
            if time.monotonic() >= deadline:
                limit_error = f"time_limit: exceeded {timeout:g}s"
                break
            try:
                snapshot = process_tree_snapshot(process.pid)
            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError):
                limit_error = "memory_probe_failed: unable to determine process-tree RSS"
                break
            rss = int(snapshot["rss_kib"])
            if rss > 0:
                peak_rss_kib = max(peak_rss_kib or 0, rss)
                rss_samples += 1
            cpu_value = snapshot.get("cpu_seconds")
            if isinstance(cpu_value, (int, float)):
                process_tree_cpu_seconds = max(
                    process_tree_cpu_seconds or 0.0, float(cpu_value)
                )
                cpu_samples += 1
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
        metrics: dict[str, object] = {
            "wall_seconds": time.monotonic() - started,
            "child_process_tree_cpu_seconds": process_tree_cpu_seconds,
            "peak_process_tree_rss_bytes": (
                peak_rss_kib * 1024 if peak_rss_kib is not None else None
            ),
            "process_tree_rss_sample_count": rss_samples,
            "process_tree_cpu_sample_count": cpu_samples,
            "termination_reason": (
                "wall_clock_timeout" if limit_error and
                limit_error.startswith("time_limit") else
                "process_tree_memory_limit" if limit_error and
                limit_error.startswith("memory_limit") else
                "resource_probe_error" if limit_error else
                f"process_exit_{process.returncode}" if process.returncode != 0 else
                "process_exited"
            ),
            "memory_enforcement": "sampled aggregate process-tree RSS watchdog",
            "cpu_measurement": "sampled cumulative process-tree CPU from ps",
        }
        if limit_error:
            return None, limit_error, metrics
        return subprocess.CompletedProcess(command, process.returncode, "", stderr), None, metrics


def store_resource_metrics(
    row: dict[str, str], metrics: dict[str, object], prefix: str = ""
) -> None:
    for key in (
        "wall_seconds", "child_process_tree_cpu_seconds",
        "peak_process_tree_rss_bytes", "process_tree_rss_sample_count",
        "process_tree_cpu_sample_count", "termination_reason",
    ):
        value = metrics.get(key)
        row[f"{prefix}{key}"] = "null" if value is None else str(value)
    if not prefix and metrics.get("memory_enforcement") is not None:
        row["memory_enforcement"] = str(metrics["memory_enforcement"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and compare all algorithms on all *.instance.json files."
    )
    root = ROOT
    parser.add_argument("--config", type=Path, default=root / "config/default.json")
    parser.add_argument("--solver", type=Path, default=root / "build/bin/solver")
    parser.add_argument("--instances", type=Path, default=root / "data/test")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float,
                        help="compatibility alias setting both timeout limits")
    parser.add_argument(
        "--official-timeout",
        type=float,
        default=30.0,
        help="official-validator timeout per run in seconds (default: 30)",
    )
    parser.add_argument("--memory", type=int, help="per-process limit in MiB")
    parser.add_argument(
        "--master-table",
        type=Path,
        default=None,
        help="wide comparison table path (default: <output>/master-table.tsv)",
    )
    parser.add_argument(
        "--algorithms",
        default=None,
        help="comma-separated algorithm override",
    )
    official_group = parser.add_mutually_exclusive_group()
    official_group.add_argument("--official", dest="official", action="store_true",
                        help="also run cgshop2027_pyutils when installed")
    official_group.add_argument("--no-official", dest="official", action="store_false")
    parser.set_defaults(official=None)
    overwrite_group = parser.add_mutually_exclusive_group()
    overwrite_group.add_argument(
        "--overwrite", dest="overwrite", action="store_true",
        help="allow reusing an existing output directory and replacing its artifacts",
    )
    overwrite_group.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    parser.set_defaults(overwrite=None)
    args = parser.parse_args()
    overrides = {}
    if args.timeout is not None:
        overrides["per_instance_timeout_seconds"] = args.timeout
        overrides["per_algorithm_timeout_seconds"] = args.timeout
    if args.memory is not None:
        overrides["memory_limit_mib"] = args.memory
    if args.algorithms is not None:
        overrides["algorithms"] = [item.strip() for item in args.algorithms.split(",")]
    if args.output is not None:
        overrides["output_directory"] = str(args.output)
    if args.official is not None:
        overrides["official_validation"] = args.official
    if args.overwrite is not None:
        overrides["overwrite_existing"] = args.overwrite
    try:
        requested, effective, adjustments = load_runtime_config(args.config, overrides)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    algorithms = tuple(requested["algorithms"])
    if effective["benchmark_jobs"] != 1:
        parser.error("solve_all is sequential; use benchmark.py for benchmark_jobs > 1")
    if effective["randomized_repetitions"] != 1:
        parser.error("solve_all does not run repetitions; use benchmark.py")
    if args.timeout is None:
        args.timeout = min(effective["per_instance_timeout_seconds"],
                           effective["per_algorithm_timeout_seconds"])
    if args.memory is None:
        args.memory = effective["memory_limit_mib"]
    if args.output is None:
        args.output = root / effective["output_directory"] / "solve-all"
    elif not args.output.is_absolute():
        args.output = root / args.output
    args.overwrite = effective["overwrite_existing"]
    unknown = sorted(set(algorithms) - set(ALGORITHMS))
    if unknown:
        parser.error("unknown algorithms: " + ", ".join(unknown))
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.official_timeout <= 0:
        parser.error("--official-timeout must be positive")
    if args.memory <= 0:
        parser.error("--memory must be positive")
    if not algorithms:
        parser.error("at least one algorithm must be selected")
    if not args.solver.is_file() or not os.access(args.solver, os.X_OK):
        parser.error(f"solver executable not found or not executable: {args.solver}")
    if not args.instances.is_dir():
        parser.error(f"instance directory does not exist: {args.instances}")
    instances = sorted(args.instances.glob("*.instance.json"))
    if not instances:
        parser.error(f"no *.instance.json inputs found in {args.instances}")
    for instance_path in instances:
        try:
            instance = json.loads(instance_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"cannot read valid JSON instance {instance_path}: {error}")
        if not isinstance(instance, dict) or not isinstance(
            instance.get("instance_uid"), str
        ):
            parser.error(f"instance has no string instance_uid: {instance_path}")
    if args.output.exists() and not args.overwrite:
        parser.error(
            f"output directory already exists: {args.output} (pass --overwrite)"
        )
    if args.output.exists() and not args.output.is_dir():
        parser.error(f"output path is not a directory: {args.output}")
    master_table = args.master_table or args.output / "master-table.tsv"
    if master_table.exists() and not args.overwrite:
        parser.error(
            f"master table already exists: {master_table} (pass --overwrite)"
        )
    use_official = effective["official_validation"]
    if use_official and not official_validator_available():
        parser.error(
            "--official requires the cgshop2027_pyutils package in the "
            "selected Python interpreter"
        )
    validate_script = Path(__file__).resolve().with_name("validate.py")
    long_rows: list[dict[str, str]] = []
    args.output.mkdir(parents=True, exist_ok=True)
    config_report = {
        "requested": requested,
        "effective": effective,
        "automatic_adjustments": adjustments,
        "intended_max_active_solver_workers":
            effective["benchmark_jobs"] * effective["threads_per_solver"],
        "memory_enforcement": "sampled process-tree RSS watchdog",
        "official_validation": "enabled" if use_official else "disabled",
    }
    (args.output / "runtime-config.json").write_text(
        json.dumps(config_report, indent=2) + "\n", encoding="utf-8"
    )

    global_deadline = None
    if effective["global_run_deadline_seconds"] is not None:
        global_deadline = time.monotonic() + effective["global_run_deadline_seconds"]

    # Keep the outer loop algorithm-first so every algorithm is evaluated over
    # the complete instance set, while each instance/algorithm run remains
    # independently bounded.
    for algorithm in algorithms:
        for instance_path in instances:
            uid = instance_path.name.removesuffix(".instance.json")
            instance = json.loads(instance_path.read_text())
            solution_path = args.output / f"{uid}.{algorithm}.solution.json"
            figure_path = args.output / f"{uid}.{algorithm}.png"
            run_config_path = Path(str(solution_path) + ".run-config.json")
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
                "config_report": str(run_config_path),
                "time_limit_seconds": str(args.timeout),
                "memory_limit_mib": str(args.memory),
                "error": "",
                "wall_seconds": "null",
                "child_process_tree_cpu_seconds": "null",
                "peak_process_tree_rss_bytes": "null",
                "process_tree_rss_sample_count": "0",
                "process_tree_cpu_sample_count": "0",
                "termination_reason": "not_started",
                "memory_enforcement": "sampled aggregate process-tree RSS watchdog",
                "cpu_measurement": "sampled cumulative process-tree CPU from ps",
                "official_wall_seconds": "null",
                "official_child_process_tree_cpu_seconds": "null",
                "official_peak_process_tree_rss_bytes": "null",
                "official_process_tree_rss_sample_count": "0",
                "official_process_tree_cpu_sample_count": "0",
                "official_termination_reason": "not_run",
            }
            wall_timeout = args.timeout
            if global_deadline is not None:
                remaining = global_deadline - time.monotonic()
                if remaining <= 0:
                    run_effective = copy.deepcopy(effective)
                    run_effective["algorithms"] = [algorithm]
                    run_effective["output_directory"] = str(args.output)
                    run_effective["effective_per_run_wall_clock_timeout_seconds"] = 0
                    run_effective["official_validation"] = use_official
                    run_config_path.write_text(
                        json.dumps({
                            "requested": requested,
                            "effective": run_effective,
                            "automatic_adjustments": adjustments + [
                                "global run deadline expired before this run"
                            ],
                            "memory_enforcement": "sampled process-tree RSS watchdog",
                        }, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    row["status"] = "global_deadline"
                    row["error"] = "global run deadline reached before this run"
                    row["seconds"] = "0.000"
                    long_rows.append(row)
                    print(f"{uid}\t{algorithm}\tglobal_deadline\t")
                    continue
                wall_timeout = min(wall_timeout, remaining)
            run_effective = copy.deepcopy(effective)
            run_effective["algorithms"] = [algorithm]
            run_effective["output_directory"] = str(args.output)
            run_effective["effective_per_run_wall_clock_timeout_seconds"] = wall_timeout
            run_effective["per_instance_timeout_seconds"] = min(
                run_effective["per_instance_timeout_seconds"], wall_timeout
            )
            run_effective["per_algorithm_timeout_seconds"] = min(
                run_effective["per_algorithm_timeout_seconds"], wall_timeout
            )
            finalization_reserve = min(5.0, max(0.25, wall_timeout * 0.2))
            run_effective["cooperative_search_budget_cap_seconds"] = max(
                0.0, wall_timeout - finalization_reserve
            )
            run_effective["finalization_reserve_seconds"] = finalization_reserve
            run_effective["official_validation"] = use_official
            run_config_path.write_text(
                json.dumps({
                    "requested": requested,
                    "effective": run_effective,
                    "automatic_adjustments": adjustments + [
                        f"effective per-run wall-clock timeout is {wall_timeout:g}s",
                        f"cooperative search reserves {finalization_reserve:g}s for validation and output",
                    ],
                    "memory_enforcement": "sampled process-tree RSS watchdog",
                }, indent=2) + "\n",
                encoding="utf-8",
            )
            try:
                if args.overwrite:
                    solution_path.unlink(missing_ok=True)
                    figure_path.unlink(missing_ok=True)
                completed, limit_error, solver_metrics = run_bounded(
                    [str(args.solver), "-i", str(instance_path), "-o",
                     str(solution_path), "-a", algorithm,
                     "--instance-timeout", str(run_effective["per_instance_timeout_seconds"]),
                     "--algorithm-timeout", str(run_effective["per_algorithm_timeout_seconds"]),
                     "--kont-timeout", str(min(effective["ip_kont_timeout_seconds"], wall_timeout)),
                     "--memory-limit-mib", str(effective["memory_limit_mib"]),
                     "--threads-per-solver", str(effective["threads_per_solver"]),
                     "--benchmark-jobs", str(effective["benchmark_jobs"]),
                     "--seed", str(effective["random_seed"]),
                     "--lns-iterations",
                     str(effective["algorithm_parameters"]["lns_iterations"]),
                     "--tsp-max-anchors",
                     str(effective["algorithm_parameters"]["tsp_max_anchors"]),
                     "--two-opt-passes",
                     str(effective["algorithm_parameters"]["two_opt_passes"]),
                     "--exact-policy", effective["exact_solving_policy"],
                     "--exact-max-candidates",
                     str(effective["exact_solver_max_candidates"]),
                     "--portfolio", ",".join(effective["heuristic_portfolio"]),
                     "--tier", "all",
                     "--repetitions", str(effective["randomized_repetitions"]),
                     "--output-dir", str(args.output),
                     "--log-level", effective["logging_verbosity"],
                     *(["--global-deadline",
                        str(effective["global_run_deadline_seconds"])]
                       if effective["global_run_deadline_seconds"] is not None else []),
                     *(["--overwrite"] if args.overwrite else [])],
                    wall_timeout, args.memory,
                )
                store_resource_metrics(row, solver_metrics)
                if limit_error:
                    row["status"] = limit_error.split(":", 1)[0]
                    row["error"] = limit_error
                    raise RuntimeError(limit_error)
                if completed is None:
                    raise RuntimeError("bounded solver returned no process result")
                if completed.returncode != 0:
                    if ("deadline" in completed.stderr.lower() or
                            (completed.returncode < 0 and
                             -completed.returncode == signal.SIGKILL)):
                        row["status"] = "memory_limit"
                        if "deadline" in completed.stderr.lower():
                            row["status"] = "time_limit"
                    else:
                        row["status"] = "failed"
                    row["error"] = completed.stderr.strip()
                    raise RuntimeError(row["error"] or
                                       f"solver exited with {completed.returncode}")
                solution = json.loads(solution_path.read_text())
                row["makespan"] = str(makespan(solution))
                render_png(instance, solution, figure_path)
                if use_official:
                    validation_timeout = args.official_timeout
                    if global_deadline is not None:
                        validation_timeout = min(
                            validation_timeout,
                            max(0.0, global_deadline - time.monotonic()),
                        )
                    if validation_timeout <= 0:
                        limit_error = "global run deadline reached before official validation"
                        official = None
                    else:
                        official, validation_error, validation_metrics = run_bounded(
                            [sys.executable, str(validate_script),
                             str(instance_path), str(solution_path)],
                            validation_timeout, args.memory,
                        )
                        store_resource_metrics(row, validation_metrics, "official_")
                    if official is None:
                        row["status"] = (
                            "global_deadline"
                            if global_deadline is not None and
                            time.monotonic() >= global_deadline
                            else "official_resource_limit"
                        )
                        row["error"] = limit_error if validation_timeout <= 0 else validation_error
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
              "wall_seconds", "child_process_tree_cpu_seconds",
              "peak_process_tree_rss_bytes", "process_tree_rss_sample_count",
              "process_tree_cpu_sample_count", "termination_reason",
              "memory_enforcement", "official_wall_seconds",
              "official_child_process_tree_cpu_seconds",
              "official_peak_process_tree_rss_bytes",
              "official_process_tree_rss_sample_count",
              "official_process_tree_cpu_sample_count",
              "official_termination_reason",
              "solution", "figure", "config_report", "error")
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
