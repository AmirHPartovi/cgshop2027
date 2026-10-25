#!/usr/bin/env python3
"""Test deterministic workload-tier partitioning without touching dataset files."""

import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from profile_instances import DEFAULT_THRESHOLDS, load_thresholds
from classify_contest_instances import (
    CLASSIFICATION_VERSION,
    classify_dataset,
    create_inventory,
)


def row(uid, raster, coverage, anchors=100):
    features = {
        "instance_uid": uid,
        "estimated_raster_point_tests": raster,
        "estimated_coverage_candidate_pairs": coverage,
        "estimated_anchor_count": anchors,
        "estimated_ip_kont_columns_upper_bound": 10,
        "estimated_ip_kont_variables_upper_bound": 10,
        "estimated_ip_kont_constraints_upper_bound": 12,
        "number_of_cutters": 1,
        "boundary_vertices": 4,
        "file_bytes": 100,
    }
    return {"features": features}


class ContestInstanceClassificationTests(unittest.TestCase):
    def test_relative_tiers_are_balanced_and_uid_breaks_exact_ties(self):
        rows = [
            row(uid, 100, 200)
            for uid in ("uid-h", "uid-g", "uid-f", "uid-e",
                        "uid-d", "uid-c", "uid-b", "uid-a")
        ]
        method, tiers, report = classify_dataset(
            rows, load_thresholds(DEFAULT_THRESHOLDS)
        )
        self.assertEqual(method, "relative_workload")
        self.assertEqual(report["classification_version"], CLASSIFICATION_VERSION)
        self.assertEqual(report["cut_indices_zero_based"], [2, 5])
        self.assertEqual(
            {tier: list(tiers.values()).count(tier)
             for tier in ("LIGHT", "MEDIUM", "HEAVY")},
            {"LIGHT": 2, "MEDIUM": 3, "HEAVY": 3},
        )
        self.assertEqual(tiers["uid-a"], "LIGHT")
        self.assertEqual(tiers["uid-b"], "LIGHT")
        self.assertEqual(tiers["uid-f"], "HEAVY")

    def test_existing_fixed_thresholds_are_kept_when_all_tiers_are_populated(self):
        rows = (
            [row(f"light-{i}", 1, 1, anchors=1) for i in range(10)]
            + [row(f"medium-{i}", 20_000_000, 1, anchors=100_000)
               for i in range(10)]
            + [row(f"heavy-{i}", 2_000_000_000, 1, anchors=1_000_000)
               for i in range(10)]
        )
        method, tiers, report = classify_dataset(
            rows, load_thresholds(DEFAULT_THRESHOLDS)
        )
        self.assertEqual(method, "fixed_thresholds")
        self.assertEqual(report["fixed_threshold_counts"], {
            "LIGHT": 10, "MEDIUM": 10, "HEAVY": 10
        })
        self.assertEqual(set(tiers.values()), {"LIGHT", "MEDIUM", "HEAVY"})

    def test_missing_official_dataset_does_not_fall_back(self):
        with tempfile.TemporaryDirectory(prefix="missing-contest-inputs-") as temp:
            absent = Path(temp) / "instances"
            with self.assertRaisesRegex(ValueError, "official input directory is missing"):
                create_inventory(absent, Path(temp) / "output")


if __name__ == "__main__":
    unittest.main()
