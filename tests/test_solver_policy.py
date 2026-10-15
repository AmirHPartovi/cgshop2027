#!/usr/bin/env python3
"""Tests for automatic tier policy and validated candidate selection."""

import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from solver_policy import build_plan, select_candidate  # noqa: E402

FIXTURE_THRESHOLDS = ROOT / "tests/fixtures/profiler/thresholds.json"


class SolverPolicyTests(unittest.TestCase):
    def _fixture(self, tier: str) -> Path:
        return ROOT / f"tests/fixtures/profiler/{tier.lower()}.instance.json"

    def test_fixture_selection_and_portfolio_by_tier(self):
        expectations = {
            "LIGHT": ["partition", "boustrophedon", "tsp-cov"],
            "MEDIUM": [
                "partition", "boustrophedon", "frederickson",
                "mstc", "connected-growth", "tsp-cov",
            ],
            "HEAVY": ["partition", "boustrophedon", "stc", "mstc"],
        }
        for tier, portfolio in expectations.items():
            with self.subTest(tier=tier):
                plan = build_plan(
                    self._fixture(tier), thresholds_path=FIXTURE_THRESHOLDS
                )
                self.assertEqual(plan["estimated_tier"], tier)
                self.assertEqual(plan["algorithms_to_run"], portfolio)
                self.assertFalse(plan["exact_method_available"])
                self.assertEqual(plan["exact_method_status"], "unavailable")
                self.assertFalse(plan["ip_kont_surrogate_scheduled"])
                candidates = [
                    {
                        "algorithm": algorithm,
                        "status": "ok",
                        "validation_level": "official",
                        "official_validated": True,
                        "makespan": len(portfolio) - index,
                        "solution": f"/tmp/{tier}-{algorithm}.json",
                        "candidate_kind": "heuristic",
                    }
                    for index, algorithm in enumerate(portfolio)
                ]
                selected = select_candidate(plan, candidates)
                self.assertEqual(selected["status"], "ok")
                self.assertTrue(selected["official_validated"])
                self.assertEqual(selected["selected_algorithm"], portfolio[-1])

    def test_explicit_algorithm_does_not_silently_use_auto(self):
        plan = build_plan(
            self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS,
            forced_algorithm="partition",
        )
        self.assertEqual(plan["requested_policy"], "forced_algorithm")
        self.assertEqual(plan["requested_algorithm"], "partition")
        self.assertEqual(plan["algorithms_to_run"], ["partition"])
        self.assertIn("explicit algorithm", plan["selection_reason"])

    def test_exact_policy_refuses_without_a_valid_exact_method(self):
        with self.assertRaisesRegex(ValueError, "no mathematically exact solver"):
            build_plan(
                self._fixture("light"), thresholds_path=FIXTURE_THRESHOLDS,
                requested_policy="exact",
            )

    def test_ip_kont_is_explicitly_marked_as_non_exact_probe(self):
        plan = build_plan(
            self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS,
            include_ip_kont_surrogate=True,
        )
        self.assertFalse(plan["ip_kont_surrogate_scheduled"])
        self.assertIn("not run", plan["ip_kont_surrogate_reason"])
        self.assertIn("does not optimize", plan["exact_method_reason"])

    def test_surrogate_probe_requires_budget_size_and_runtime_permission(self):
        policy = json.loads(
            (ROOT / "config/auto_policy.json").read_text(encoding="utf-8")
        )
        policy["ip_kont_surrogate_probe"].update({
            "maximum_estimated_column_count": 999,
            "budget_seconds": 0.5,
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(policy))
            blocked = build_plan(
                self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS,
                policy_path=path, include_ip_kont_surrogate=True,
                surrogate_allowed_by_runtime_config=False,
            )
            allowed = build_plan(
                self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS,
                policy_path=path, include_ip_kont_surrogate=True,
                surrogate_allowed_by_runtime_config=True,
            )
            policy["ip_kont_surrogate_probe"]["maximum_estimated_column_count"] = 2_000_000
            path.write_text(json.dumps(policy))
            size_allowed = build_plan(
                self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS,
                policy_path=path, include_ip_kont_surrogate=True,
                surrogate_allowed_by_runtime_config=True,
            )
        self.assertFalse(blocked["ip_kont_surrogate_scheduled"])
        self.assertIn("exceeds configured", allowed["ip_kont_surrogate_reason"])
        self.assertTrue(size_allowed["ip_kont_surrogate_scheduled"])
        self.assertEqual(size_allowed["algorithms_to_run"][-1], "ilp")
        self.assertEqual(size_allowed["ip_kont_surrogate_budget_seconds"], 0.5)

    def test_timed_out_candidate_does_not_displace_official_incumbent(self):
        plan = build_plan(
            self._fixture("light"), thresholds_path=FIXTURE_THRESHOLDS
        )
        candidates = [
            {
                "algorithm": "ilp",
                "status": "timeout",
                "validation_level": None,
                "official_validated": False,
                "candidate_kind": "ip_kont_surrogate",
                "outcome": "surrogate probe timed out",
            },
            {
                "algorithm": "partition",
                "status": "ok",
                "validation_level": "official",
                "official_validated": True,
                "makespan": 8,
                "solution": "/tmp/partition.solution.json",
                "candidate_kind": "heuristic",
            },
            {
                "algorithm": "boustrophedon",
                "status": "timeout",
                "validation_level": None,
                "official_validated": False,
                "outcome": "wall-clock budget exceeded",
            },
            {
                "algorithm": "tsp-cov",
                "status": "official_invalid",
                "validation_level": None,
                "official_validated": False,
                "makespan": 2,
            },
        ]
        selected = select_candidate(plan, candidates)
        self.assertEqual(selected["status"], "ok")
        self.assertEqual(selected["selected_algorithm"], "partition")
        self.assertEqual(selected["selected_makespan"], 8)
        self.assertTrue(selected["official_validated"])
        self.assertFalse(selected["optimality_certified"])
        self.assertEqual(selected["exact_method_status"], "unavailable")

    def test_no_official_candidate_is_a_failure(self):
        plan = build_plan(
            self._fixture("heavy"), thresholds_path=FIXTURE_THRESHOLDS
        )
        selected = select_candidate(plan, [{
            "algorithm": "partition",
            "status": "ok",
            "validation_level": "internal_cpp",
            "official_validated": False,
            "makespan": 4,
        }])
        self.assertEqual(selected["status"], "no_valid_candidate")
        self.assertIsNone(selected["selected_solution"])
        self.assertFalse(selected["official_validated"])

    def test_ip_kont_fallback_remains_a_heuristic_candidate(self):
        plan = build_plan(
            self._fixture("medium"), thresholds_path=FIXTURE_THRESHOLDS
        )
        selected = select_candidate(plan, [{
            "algorithm": "ilp",
            "candidate_kind": "heuristic_fallback_from_ip_kont_surrogate",
            "status": "ok",
            "validation_level": "official",
            "official_validated": True,
            "makespan": 9,
            "solution": "/tmp/fallback.solution.json",
        }])
        self.assertEqual(
            selected["selected_candidate_kind"],
            "heuristic_fallback_from_ip_kont_surrogate",
        )
        self.assertFalse(selected["optimality_certified"])


if __name__ == "__main__":
    unittest.main()
