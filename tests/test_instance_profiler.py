#!/usr/bin/env python3
"""Regression tests for deterministic instance workload profiling."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from profile_instances import (  # noqa: E402
    classify,
    extract_features,
    load_thresholds,
    select_algorithm,
    select_pilot_instances,
    spearman_rank_correlation,
    _calibration_metrics,
)


class InstanceProfilerTests(unittest.TestCase):
    def test_fixture_features_are_deterministic_and_separate_unknown_memory(self):
        path = ROOT / "tests/fixtures/instances/tiny-hole-multicutter.instance.json"
        first = extract_features(path)
        second = extract_features(path)
        self.assertEqual(first, second)
        self.assertEqual(first["hole_count"], 1)
        self.assertEqual(first["number_of_cutters"], 2)
        self.assertEqual(first["region_cell_count"], 8)
        self.assertEqual(first["estimated_anchor_count"], 8)
        self.assertEqual(first["estimated_coverage_candidate_pairs"], 8)
        self.assertEqual(first["estimated_ip_kont_columns_upper_bound"], 3)
        self.assertEqual(first["estimated_ip_kont_variables_upper_bound"], 6)
        self.assertEqual(first["estimated_ip_kont_constraints_upper_bound"], 5)
        self.assertEqual(first["estimated_total_coverage_memory_bytes"], None)
        self.assertEqual(first["measured_features"]["hole_count"], 1)
        self.assertEqual(first["derived_exact_features"]["region_cell_count"], 8)
        self.assertIsNone(first["estimated_features"]["estimated_total_coverage_memory_bytes"])

    def test_tier_thresholds_and_reason_are_configurable(self):
        thresholds = load_thresholds(ROOT / "config/instance_profiler.json")
        features = {
            "estimated_anchor_count": 11,
            "estimated_raster_point_tests": 101,
        }
        custom = copy.deepcopy(thresholds)
        custom["tiers"]["LIGHT"]["max_estimated_anchor_count"] = 10
        custom["tiers"]["LIGHT"]["max_estimated_raster_point_tests"] = 100
        custom["tiers"]["MEDIUM"]["max_estimated_anchor_count"] = 20
        custom["tiers"]["MEDIUM"]["max_estimated_raster_point_tests"] = 200
        result = classify(features, custom)
        self.assertEqual(result["tier"], "MEDIUM")
        self.assertIn("anchors=11", result["reason"])
        self.assertEqual(result["confidence"], "LOW")

    def test_insufficient_features_are_unknown(self):
        thresholds = load_thresholds(ROOT / "config/instance_profiler.json")
        result = classify({"estimated_anchor_count": None}, thresholds)
        self.assertEqual(result["tier"], "UNKNOWN")

    def test_automatic_algorithm_uses_configured_tier_mapping(self):
        thresholds = load_thresholds(ROOT / "config/instance_profiler.json")
        thresholds["automatic_algorithm_by_tier"]["MEDIUM"] = "partition"
        self.assertEqual(select_algorithm("MEDIUM", "auto", thresholds), "partition")
        self.assertEqual(select_algorithm("MEDIUM", "lns", thresholds), "lns")

    def test_malformed_geometry_fails_feature_extraction(self):
        source = json.loads(
            (ROOT / "tests/fixtures/instances/tiny-square.instance.json").read_text()
        )
        source["cutter"]["x"][1] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.instance.json"
            path.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "rectilinear"):
                extract_features(path)

    def test_pilot_selection_is_deterministic_and_stratified(self):
        rows = [
            {"instance_uid": f"i{index}", "estimated_raster_point_tests": index}
            for index in range(11)
        ]
        selected = select_pilot_instances(rows, 4)
        self.assertEqual([row["instance_uid"] for row in selected],
                         ["i0", "i3", "i7", "i10"])
        self.assertEqual(selected, select_pilot_instances(rows, 4))

    def test_spearman_requires_enough_nonconstant_measurements(self):
        self.assertIsNone(spearman_rank_correlation([1, 2], [2, 1]))
        self.assertIsNone(spearman_rank_correlation([1, 1, 1], [1, 2, 3]))
        self.assertAlmostEqual(
            spearman_rank_correlation([1, 2, 3], [1, 3, 2]), 0.5
        )

    def test_calibration_does_not_claim_tier_validation_from_one_tier(self):
        rows = [
            {
                "estimated_tier": "LIGHT",
                "estimated_raster_point_tests": index,
                "elapsed_seconds": index,
                "empirical_status": "ok",
                "validation_level": "official",
            }
            for index in (1, 2, 3)
        ]
        rows.append({"empirical_status": "timeout"})
        report = _calibration_metrics(rows)
        self.assertEqual(report["successful_validated_runs"], 3)
        self.assertEqual(report["successful_tiers"], ["LIGHT"])
        self.assertEqual(report["timed_out_runs"], 1)
        self.assertIn("insufficient", report["threshold_validation_status"])


if __name__ == "__main__":
    unittest.main()
