#!/usr/bin/env python3
"""Tests separating feasible incumbents from bounds and certified optima."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from reference_comparison import compare_instance_results, comparison_tsv  # noqa: E402


class ReferenceComparisonTests(unittest.TestCase):
    def test_incumbent_never_becomes_an_optimum_or_lower_bound(self):
        rows = [
            {
                "instance_uid": "case-a",
                "algorithm": "partition",
                "repetition": 0,
                "status": "ok",
                "makespan": 12,
                "validation_level": "official",
                "official_validated": True,
            },
            {
                "instance_uid": "case-a",
                "algorithm": "ilp",
                "repetition": 0,
                "status": "ok",
                "makespan": 9,
                "validation_level": "internal_cpp",
                "official_validated": False,
                "candidate_kind": "heuristic_fallback_from_ip_kont_surrogate",
                "ilp_backend": "partition-fallback",
                "ip_kont_status": "ERROR",
                "ip_kont_raw_status": "UNKNOWN",
                "ip_kont_runtime_seconds": 0.25,
                "seconds": 0.5,
                "ip_kont_termination_reason": "surrogate solve completed",
                "ip_kont_model": "vertical_column_assignment_surrogate",
                "ip_kont_variable_count": 17,
                "ip_kont_constraint_count": 7,
                "ip_kont_exact_for_original_objective": False,
                "ip_kont_solver_log": "KONT error log",
            },
            {
                "instance_uid": "case-a",
                "algorithm": "boustrophedon",
                "repetition": 0,
                "status": "timeout",
                "makespan": None,
                "validation_level": None,
                "official_validated": False,
            },
        ]
        result = compare_instance_results(rows)[0]
        self.assertEqual(result["best_validated_feasible_makespan"], 9)
        self.assertEqual(
            result["best_validated_algorithm"], "partition fallback (ilp wrapper)"
        )
        self.assertEqual(result["best_officially_validated_feasible_makespan"], 12)
        self.assertIsNone(result["certified_optimum_makespan"])
        self.assertIsNone(result["exact_agreement"])
        self.assertIsNone(result["ip_kont_lower_bound"])
        self.assertFalse(result["ip_kont_lower_bound_valid"])
        self.assertIsNone(result["relative_gap_to_valid_lower_bound"])
        self.assertEqual(result["best_known_upper_bound"], 9)
        self.assertEqual(result["ip_kont_solver_status"], "ERROR")
        self.assertEqual(result["ip_kont_raw_status"], "UNKNOWN")
        self.assertFalse(result["ip_kont_proof_completed"])
        self.assertEqual(result["ip_kont_solver_log"], "KONT error log")

    def test_kont_optimal_status_is_not_original_objective_proof(self):
        result = compare_instance_results([{
            "instance_uid": "case-optimal-surrogate",
            "algorithm": "ilp",
            "repetition": 0,
            "status": "ok",
            "makespan": 8,
            "validation_level": "official",
            "official_validated": True,
            "candidate_kind": "ip_kont_surrogate_incumbent",
            "ip_kont_status": "FEASIBLE_NOT_PROVEN",
            "ip_kont_raw_status": "KONT status: OPTIMAL",
            "ip_kont_runtime_seconds": 0.1,
            "ip_kont_exact_for_original_objective": False,
        }])[0]
        self.assertEqual(result["ip_kont_solver_status"], "FEASIBLE_NOT_PROVEN")
        self.assertEqual(result["ip_kont_raw_status"], "KONT status: OPTIMAL")
        self.assertFalse(result["ip_kont_proof_completed"])
        self.assertIsNone(result["certified_optimum_makespan"])
        self.assertEqual(
            result["best_validated_algorithm"], "ilp (IP-KONT surrogate candidate)"
        )

    def test_valid_proof_sources_enable_gap_and_optimum_comparisons(self):
        rows = [{
            "instance_uid": "case-with-reference",
            "algorithm": "partition",
            "repetition": 0,
            "status": "ok",
            "makespan": 9,
            "validation_level": "official",
            "official_validated": True,
        }]
        reference = {
            "optimality_certified": True,
            "formulation_exact_for_original_objective": True,
            "solution_validated": True,
            "objective_matched": True,
            "certified_optimum_makespan": 7,
            "certified_optimum_source": "independent exact run",
            "ip_kont_lower_bound_valid": True,
            "ip_kont_lower_bound": 6,
            "ip_kont_lower_bound_source": "validated exact relaxation",
        }
        result = compare_instance_results(
            rows, {"case-with-reference": reference}
        )[0]
        self.assertEqual(result["certified_optimum_makespan"], 7)
        self.assertFalse(result["exact_agreement"])
        self.assertEqual(result["additive_difference_from_optimum"], 2)
        self.assertAlmostEqual(result["relative_difference_from_optimum"], 2 / 7)
        self.assertEqual(result["ip_kont_lower_bound"], 6)
        self.assertAlmostEqual(result["relative_gap_to_valid_lower_bound"], 0.5)

    def test_unverified_optimum_and_lower_bound_claims_are_ignored(self):
        rows = [{
            "instance_uid": "case-untrusted",
            "algorithm": "partition",
            "repetition": 0,
            "status": "ok",
            "makespan": 9,
            "validation_level": "internal_cpp",
            "official_validated": False,
        }]
        reference = {
            "certified_optimum_makespan": 7,
            "certified_optimum_source": "unverified",
            "ip_kont_lower_bound": 6,
            "ip_kont_lower_bound_source": "heuristic estimate",
        }
        result = compare_instance_results(rows, {"case-untrusted": reference})[0]
        self.assertIsNone(result["certified_optimum_makespan"])
        self.assertIsNone(result["ip_kont_lower_bound"])
        self.assertIsNone(result["relative_gap_to_valid_lower_bound"])

    def test_no_algorithm_result_is_not_reported_as_a_zero_case_success(self):
        result = compare_instance_results([{
            "instance_uid": "case-b",
            "algorithm": "ilp",
            "repetition": 0,
            "status": "time_limit",
            "seconds": 2,
            "error": "outer watchdog expired",
            "validation_level": None,
            "official_validated": False,
        }])[0]
        self.assertIsNone(result["best_known_upper_bound"])
        self.assertEqual(result["ip_kont_solver_status"], "TIME_LIMIT_NO_INCUMBENT")
        self.assertFalse(result["ip_kont_proof_completed"])
        self.assertIn("watchdog", result["ip_kont_termination_reason"])

    def test_non_ip_runs_keep_ip_status_not_run(self):
        result = compare_instance_results([{
            "instance_uid": "case-c",
            "algorithm": "partition",
            "repetition": 0,
            "status": "ok",
            "makespan": 3,
            "validation_level": "internal_cpp",
            "official_validated": False,
        }])[0]
        self.assertEqual(result["ip_kont_solver_status"], "NOT_RUN")
        self.assertEqual(result["best_known_upper_bound"], 3)
        self.assertIn("certified_optimum_makespan", comparison_tsv([result]))


if __name__ == "__main__":
    unittest.main()
