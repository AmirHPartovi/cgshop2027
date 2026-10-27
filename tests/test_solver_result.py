#!/usr/bin/env python3
"""Validate the shared solver-result status and candidate contract."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from solver_result import validate_solver_result  # noqa: E402


def result(**overrides):
    value = {
        "schema_version": 1,
        "solver_mode": "heuristic",
        "candidate_exists": False,
        "candidate_solution_path": None,
        "internal_validation_status": "not_run",
        "official_validation_status": "not_requested",
        "solver_completion_status": "unavailable",
        "optimality_proved": False,
        "optimality_model": None,
        "optimality_objective": None,
        "algorithm_implementation": "",
        "candidate_source": "",
        "runtime_seconds": 0.0,
        "termination_reason": "backend unavailable",
    }
    value.update(overrides)
    return value


class SolverResultTests(unittest.TestCase):
    def test_unavailable_and_timeout_without_incumbent_are_distinct(self):
        unavailable = validate_solver_result(result(solver_mode="ip-kont"))
        self.assertEqual(unavailable["solver_completion_status"], "unavailable")
        timed_out = validate_solver_result(result(
            solver_completion_status="timed_out_without_incumbent",
            termination_reason="deadline reached",
        ))
        self.assertNotEqual(
            unavailable["solver_completion_status"],
            timed_out["solver_completion_status"],
        )

    def test_valid_incumbent_requires_passed_internal_validation(self):
        valid = result(
            candidate_exists=True,
            candidate_solution_path="candidate.solution.json",
            internal_validation_status="passed",
            solver_completion_status="timed_out_with_incumbent",
            algorithm_implementation="partition",
            candidate_source="partition_fallback",
        )
        self.assertEqual(
            validate_solver_result(valid)["candidate_source"], "partition_fallback"
        )
        with self.assertRaisesRegex(ValueError, "requires an internally validated"):
            validate_solver_result({
                **valid,
                "internal_validation_status": "failed",
            })

    def test_optimal_requires_proof_scope_and_infeasible_has_no_candidate(self):
        optimal = result(
            candidate_exists=True,
            internal_validation_status="passed",
            solver_completion_status="optimal",
            optimality_proved=True,
            optimality_model="verified-route-milp-v1",
            optimality_objective="closed-tour-makespan",
        )
        self.assertTrue(validate_solver_result(optimal)["optimality_proved"])
        with self.assertRaisesRegex(ValueError, "identify its model and objective"):
            validate_solver_result({
                **optimal,
                "optimality_objective": None,
            })
        with self.assertRaisesRegex(ValueError, "cannot contain a candidate"):
            validate_solver_result(result(
                solver_completion_status="infeasible",
                candidate_exists=True,
            ))


if __name__ == "__main__":
    unittest.main()
