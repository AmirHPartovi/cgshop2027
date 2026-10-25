#!/usr/bin/env python3
"""Smoke-test the supported public APIs of cgshop2027-pyutils."""

import tempfile
import unittest
from pathlib import Path

from cgshop2027_pyutils.io import read_instance, read_solution
from cgshop2027_pyutils.schemas import CGSHOP2027Solution, CutterTour
from cgshop2027_pyutils.verify import (
    SolutionValidator,
    check_for_errors,
)
from cgshop2027_pyutils.visualize import create_solution_plot
from cgshop2027_pyutils.zip import ZipSolutionIterator, ZipWriter


ROOT = Path(__file__).resolve().parents[1]
INSTANCE_PATH = ROOT / "tests/fixtures/instances/tiny-square.instance.json"
SOLUTION_PATH = ROOT / "tests/fixtures/solutions/tiny-square.solution.json"


class OfficialPyutilsCompatibilityTests(unittest.TestCase):
    def test_official_parse_validate_schema_archive_and_plot_apis(self):
        instance = read_instance(INSTANCE_PATH)
        fixture_solution = read_solution(SOLUTION_PATH)
        self.assertEqual(instance.instance_uid, "tiny-square")
        self.assertEqual(fixture_solution.instance_uid, instance.instance_uid)
        self.assertEqual(check_for_errors(instance, fixture_solution), [])
        self.assertEqual(
            SolutionValidator(instance).check_for_errors(fixture_solution), []
        )

        solution = CGSHOP2027Solution(
            instance_uid=instance.instance_uid,
            tours=[
                CutterTour(
                    x=[0, 1, 1, 0],
                    y=[0, 0, 1, 1],
                )
            ],
        )
        self.assertEqual(check_for_errors(instance, solution), [])
        encoded = solution.model_dump_json()
        decoded = CGSHOP2027Solution.model_validate_json(encoded)
        self.assertEqual(decoded.max_tour_length, 4)
        self.assertEqual(decoded.model_dump(), solution.model_dump())

        with tempfile.TemporaryDirectory(prefix="cgshop-pyutils-compat-") as temp:
            archive_path = Path(temp) / "solutions.zip"
            with ZipWriter(archive_path) as writer:
                writer.add_solution(decoded)
            loaded = list(ZipSolutionIterator(archive_path))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(
                loaded[0].model_dump(exclude={"meta"}),
                decoded.model_dump(exclude={"meta"}),
            )
            self.assertEqual(check_for_errors(instance, loaded[0]), [])

            figure = create_solution_plot(instance, loaded[0])
            try:
                plot_path = Path(temp) / "solution.png"
                figure.savefig(plot_path)
                self.assertTrue(plot_path.is_file())
                self.assertGreater(plot_path.stat().st_size, 0)
            finally:
                import matplotlib.pyplot as plt

                plt.close(figure)


if __name__ == "__main__":
    unittest.main()
