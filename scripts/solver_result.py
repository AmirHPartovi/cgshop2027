"""Typed Python view and validation for the C++ solver result sidecar."""

from __future__ import annotations

import json
import math
from enum import Enum
from pathlib import Path
from typing import TypedDict, cast


class CandidateValidationStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


class OfficialValidationStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class SolverCompletionStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    INFEASIBLE = "infeasible"
    TIMED_OUT_WITH_INCUMBENT = "timed_out_with_incumbent"
    TIMED_OUT_WITHOUT_INCUMBENT = "timed_out_without_incumbent"
    FEASIBLE_NOT_PROVEN = "feasible_not_proven"
    OPTIMAL = "optimal"


class SolverResultReport(TypedDict):
    schema_version: int
    solver_mode: str
    candidate_exists: bool
    candidate_solution_path: str | None
    internal_validation_status: str
    official_validation_status: str
    solver_completion_status: str
    optimality_proved: bool
    optimality_model: str | None
    optimality_objective: str | None
    algorithm_implementation: str
    candidate_source: str
    runtime_seconds: float
    termination_reason: str


def validate_solver_result(value: object) -> SolverResultReport:
    if not isinstance(value, dict):
        raise ValueError("solver result must be a JSON object")
    required = set(SolverResultReport.__annotations__)
    if set(value) != required:
        raise ValueError("solver result fields do not match schema_version 1")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported solver result schema_version")
    if not isinstance(value["solver_mode"], str):
        raise ValueError("solver_mode must be a string")
    if not isinstance(value["candidate_exists"], bool):
        raise ValueError("candidate_exists must be boolean")
    if value["candidate_solution_path"] is not None and not isinstance(
        value["candidate_solution_path"], str
    ):
        raise ValueError("candidate_solution_path must be a string or null")
    try:
        internal = CandidateValidationStatus(value["internal_validation_status"])
        official = OfficialValidationStatus(value["official_validation_status"])
        completion = SolverCompletionStatus(value["solver_completion_status"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"solver result contains an unknown status: {error}") from error
    if not isinstance(value["optimality_proved"], bool):
        raise ValueError("optimality_proved must be boolean")
    if value["optimality_proved"] != (
        completion is SolverCompletionStatus.OPTIMAL
    ):
        raise ValueError("optimality_proved must agree with solver_completion_status")
    for name in ("optimality_model", "optimality_objective"):
        if value[name] is not None and not isinstance(value[name], str):
            raise ValueError(f"{name} must be a string or null")
    if value["optimality_proved"] and (
        not value["optimality_model"] or not value["optimality_objective"]
    ):
        raise ValueError("optimal result must identify its model and objective")
    for name in (
        "algorithm_implementation", "candidate_source", "termination_reason"
    ):
        if not isinstance(value[name], str):
            raise ValueError(f"{name} must be a string")
    runtime = value["runtime_seconds"]
    if (isinstance(runtime, bool) or not isinstance(runtime, (int, float)) or
            not math.isfinite(runtime) or runtime < 0):
        raise ValueError("runtime_seconds must be finite and nonnegative")

    has_candidate = value["candidate_exists"]
    if not has_candidate and internal is CandidateValidationStatus.PASSED:
        raise ValueError("internal validation cannot pass without a candidate")
    if completion in {
        SolverCompletionStatus.TIMED_OUT_WITH_INCUMBENT,
        SolverCompletionStatus.FEASIBLE_NOT_PROVEN,
        SolverCompletionStatus.OPTIMAL,
    } and (not has_candidate or internal is not CandidateValidationStatus.PASSED):
        raise ValueError(
            f"{completion.value} requires an internally validated candidate"
        )
    if completion in {
        SolverCompletionStatus.UNAVAILABLE,
        SolverCompletionStatus.INFEASIBLE,
        SolverCompletionStatus.TIMED_OUT_WITHOUT_INCUMBENT,
    } and has_candidate:
        raise ValueError(f"{completion.value} cannot contain a candidate")
    if official is OfficialValidationStatus.PASSED and (
        not has_candidate or internal is not CandidateValidationStatus.PASSED
    ):
        raise ValueError("official validation cannot pass without an internally valid candidate")
    if value["candidate_solution_path"] is not None and not has_candidate:
        raise ValueError("candidate path cannot be set when candidate_exists is false")
    return cast(SolverResultReport, value)


def read_solver_result(path: Path) -> SolverResultReport:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read solver result report {path}: {error}") from error
    return validate_solver_result(value)
