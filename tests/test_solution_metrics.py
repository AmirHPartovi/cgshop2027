#!/usr/bin/env python3
"""Unit tests for canonical closed-tour objective scoring."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from solution_metrics import makespan, tour_length


class SolutionMetricsTests(unittest.TestCase):
    def test_one_point_stationary_tour(self) -> None:
        self.assertEqual(tour_length({"x": [7], "y": [-3]}), 0)

    def test_closed_length_includes_last_to_first_edge(self) -> None:
        self.assertEqual(
            tour_length(
                {"x": [0, 2, 2, 0], "y": [0, 0, 2, 2]}
            ),
            8,
        )

    def test_makespan_is_longest_closed_tour(self) -> None:
        solution = {
            "content_type": "CGSHOP2027_Solution",
            "instance_uid": "metrics",
            "tours": [
                {"x": [0], "y": [0]},
                {"x": [0, 2, 2, 0], "y": [0, 0, 2, 2]},
            ],
        }
        self.assertEqual(makespan(solution), 8)

    def test_invalid_empty_or_nonrectilinear_data_is_rejected(self) -> None:
        for tour in (
            {"x": [], "y": []},
            {"x": [0, 1], "y": [0]},
            {"x": [0, 1], "y": [0, 1]},
            {"x": [0, 1, 0], "y": [0, 0, 0]},
            {"x": [True], "y": [0]},
        ):
            with self.subTest(tour=tour), self.assertRaises(ValueError):
                tour_length(tour)

    def test_invalid_solution_shape_and_empty_tours_are_rejected(self) -> None:
        for solution in (
            [],
            {"content_type": "wrong", "instance_uid": "x", "tours": []},
            {
                "content_type": "CGSHOP2027_Solution",
                "instance_uid": "x",
                "tours": [],
            },
        ):
            with self.subTest(solution=solution), self.assertRaises(ValueError):
                makespan(solution)


if __name__ == "__main__":
    unittest.main()
