#!/usr/bin/env python3
"""Tests swept-coverage snapshots against the C++ internal verifier."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from visualize_solution import (  # noqa: E402
    coverage_model,
    render_svg,
    safe_filename_component,
    render_png,
)

INSTANCE = json.loads(
    (ROOT / "tests/fixtures/instances/tiny-square.instance.json").read_text()
)
CPP_CHECKER = Path(sys.argv.pop(1)) if len(sys.argv) > 1 else None


def solution(tours):
    return {
        "content_type": "CGSHOP2027_Solution",
        "instance_uid": INSTANCE["instance_uid"],
        "tours": tours,
    }


class VisualizationTests(unittest.TestCase):
    def setUp(self):
        self.valid_solution = solution([
            {"x": [0, 1, 1, 0], "y": [0, 0, 1, 1]}
        ])
        self.invalid_solution = solution([
            {"x": [0, 1], "y": [0, 0]}
        ])

    def test_coverage_matches_cpp_checker_for_valid_and_uncovered_routes(self):
        checker = self._checker()
        with tempfile.TemporaryDirectory() as directory:
            instance_path = Path(directory) / "instance.json"
            solution_path = Path(directory) / "solution.json"
            instance_path.write_text(json.dumps(INSTANCE))
            for candidate, expected in (
                (self.valid_solution, True),
                (self.invalid_solution, False),
            ):
                solution_path.write_text(json.dumps(candidate))
                checked = subprocess.run(
                    [checker, str(instance_path), str(solution_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                cpp_valid = json.loads(checked.stdout)["solution_valid"]
                python_valid = coverage_model(INSTANCE, candidate)["valid"]
                self.assertEqual(python_valid, expected)
                self.assertEqual(cpp_valid, expected)

    def test_snapshot_shows_routes_lengths_status_and_uncovered_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = render_svg(
                INSTANCE,
                self.invalid_solution,
                "anchor-cover",
                "OFFICIAL_INVALID",
                animated=True,
            )
            self.assertIn("anchor-cover", svg)
            self.assertIn("OFFICIAL_INVALID", svg)
            self.assertIn("INVALID: UNCOVERED CELLS", svg)
            self.assertIn("uncovered (2)", svg)
            self.assertIn("cutter-center trajectory", svg)
            self.assertIn("<animateMotion", svg)
            ET.fromstring(svg)

            png = root / "invalid.png"
            report = render_png(INSTANCE, self.invalid_solution, png, "INVALID")
            png_data = png.read_bytes()
            self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn(b"tiny-square | unknown | INVALID", png_data)
            self.assertIn(b"uncovered_cells=2", png_data)
            self.assertFalse(report["coverage_valid"])
            self.assertEqual(report["uncovered_cell_count"], 2)
            self.assertEqual(report["route_lengths"], [2])
            self.assertEqual(report["makespan"], 2)

    def test_cli_refuses_overwrite_and_writes_svg_and_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instance_path = root / "instance.json"
            solution_path = root / "solution.json"
            png_path = root / "snapshot.png"
            svg_path = root / "snapshot.svg"
            instance_path.write_text(json.dumps(INSTANCE))
            solution_path.write_text(json.dumps(self.valid_solution))
            visualizer = ROOT / "scripts/visualize_solution.py"
            command = [
                sys.executable, str(visualizer), str(instance_path),
                str(solution_path), "--output", str(png_path),
                "--algorithm-id", "anchor-cover", "--status", "OFFICIAL_VALID",
                "--svg", str(svg_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(png_path.is_file())
            self.assertIn("anchor-cover", svg_path.read_text())
            blocked = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("refusing to overwrite", blocked.stderr)

    def test_overlap_is_marked_and_trial_names_do_not_alias(self):
        two_cutters = copy.deepcopy(INSTANCE)
        two_cutters["number_of_cutters"] = 2
        two_cutters["cutter"] = {
            "x": [0, 2, 2, 0],
            "y": [0, 0, 2, 2],
        }
        candidate = solution([{"x": [0], "y": [0]}, {"x": [0], "y": [0]}])
        model = coverage_model(two_cutters, candidate)
        self.assertTrue(model["valid"])
        self.assertEqual(len(model["overlap_cells"]), 4)
        svg = render_svg(two_cutters, candidate, "lns", "VALID_FEASIBLE")
        self.assertIn("overlap (4)", svg)
        names = {
            f"{safe_filename_component(INSTANCE['instance_uid'])}."
            f"{safe_filename_component(algorithm)}.rep-{repetition:04}.seed-{seed}.svg"
            for algorithm, repetition, seed in (
                ("anchor-cover", 0, 7),
                ("lns", 0, 7),
                ("anchor-cover", 1, 7),
                ("anchor-cover", 0, 8),
            )
        }
        self.assertEqual(len(names), 4)
        self.assertNotEqual(
            safe_filename_component("a/b"), safe_filename_component("a_b")
        )
        self.assertEqual(
            safe_filename_component("anchor-cover"),
            safe_filename_component("anchor-cover"),
        )

    def test_region_with_hole_excludes_hole_cells(self):
        instance = copy.deepcopy(INSTANCE)
        instance["region_to_cover"]["outer_boundary"] = {
            "x": [0, 3, 3, 0], "y": [0, 0, 3, 3]
        }
        instance["region_to_cover"]["inner_boundaries"] = [{
            "x": [1, 1, 2, 2], "y": [1, 2, 2, 1]
        }]
        instance["cutter"] = {
            "x": [0, 1, 1, 0], "y": [0, 0, 1, 1]
        }
        instance["cutter_center"] = [0, 0]
        instance["number_of_cutters"] = 1
        model = coverage_model(instance, solution([{
            "x": [0, 1, 2, 2, 1, 0],
            "y": [0, 0, 0, 2, 2, 2],
        }]))
        self.assertEqual(len(model["region_cells"]), 8)
        self.assertNotIn((1, 1), model["region_cells"])
        self.assertTrue(model["valid"])

    @staticmethod
    def _checker():
        if CPP_CHECKER is not None and CPP_CHECKER.is_file():
            return str(CPP_CHECKER)
        candidates = [
            ROOT / "build/bin/internal_solution_check",
            ROOT / "build/Debug/bin/internal_solution_check",
            ROOT / "build/Release/bin/internal_solution_check",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        raise unittest.SkipTest("internal_solution_check executable is not built")


if __name__ == "__main__":
    unittest.main()
