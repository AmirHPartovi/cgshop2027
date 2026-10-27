#include "core/SolverResult.h"

#include "io/Json.h"

#include <cmath>
#include <stdexcept>

namespace cgshop2027 {

const char* toString(CandidateValidationStatus status) {
    switch (status) {
        case CandidateValidationStatus::NotRun: return "not_run";
        case CandidateValidationStatus::Passed: return "passed";
        case CandidateValidationStatus::Failed: return "failed";
    }
    throw std::runtime_error("unknown internal-validation status");
}

const char* toString(OfficialValidationStatus status) {
    switch (status) {
        case OfficialValidationStatus::NotRequested: return "not_requested";
        case OfficialValidationStatus::Passed: return "passed";
        case OfficialValidationStatus::Failed: return "failed";
        case OfficialValidationStatus::Unavailable: return "unavailable";
    }
    throw std::runtime_error("unknown official-validation status");
}

const char* toString(SolverCompletionStatus status) {
    switch (status) {
        case SolverCompletionStatus::Unavailable: return "unavailable";
        case SolverCompletionStatus::Failed: return "failed";
        case SolverCompletionStatus::Infeasible: return "infeasible";
        case SolverCompletionStatus::TimedOutWithIncumbent:
            return "timed_out_with_incumbent";
        case SolverCompletionStatus::TimedOutWithoutIncumbent:
            return "timed_out_without_incumbent";
        case SolverCompletionStatus::FeasibleNotProven:
            return "feasible_not_proven";
        case SolverCompletionStatus::Optimal: return "optimal";
    }
    throw std::runtime_error("unknown solver-completion status");
}

void SolverResult::validate() const {
    if (!std::isfinite(runtimeSeconds) || runtimeSeconds < 0.0) {
        throw std::runtime_error("solver result runtime must be finite and nonnegative");
    }
    if (optimalityProved != (completion == SolverCompletionStatus::Optimal)) {
        throw std::runtime_error(
            "optimality proof flag must agree with solver completion status");
    }
    if (optimalityProved &&
        (optimalityModel.empty() || optimalityObjective.empty())) {
        throw std::runtime_error(
            "an optimal result must identify its proven model and objective");
    }
    if (!candidate && internalValidation == CandidateValidationStatus::Passed) {
        throw std::runtime_error(
            "internal validation cannot pass without a candidate");
    }
    if ((completion == SolverCompletionStatus::Unavailable ||
         completion == SolverCompletionStatus::Infeasible ||
         completion == SolverCompletionStatus::TimedOutWithoutIncumbent) &&
        candidate) {
        throw std::runtime_error(
            "completion status without an incumbent cannot contain a candidate");
    }
    if (completion == SolverCompletionStatus::TimedOutWithIncumbent &&
        (!candidate || internalValidation != CandidateValidationStatus::Passed)) {
        throw std::runtime_error(
            "timed_out_with_incumbent requires an internally validated candidate");
    }
    if (completion == SolverCompletionStatus::TimedOutWithoutIncumbent &&
        candidate) {
        throw std::runtime_error(
            "timed_out_without_incumbent cannot contain a candidate");
    }
    if (completion == SolverCompletionStatus::FeasibleNotProven &&
        (!candidate || internalValidation != CandidateValidationStatus::Passed)) {
        throw std::runtime_error(
            "feasible_not_proven requires an internally validated candidate");
    }
    if (completion == SolverCompletionStatus::Optimal &&
        (!candidate || internalValidation != CandidateValidationStatus::Passed)) {
        throw std::runtime_error(
            "optimal requires an internally validated candidate");
    }
    if (officialValidation == OfficialValidationStatus::Passed &&
        (!candidate || internalValidation != CandidateValidationStatus::Passed)) {
        throw std::runtime_error(
            "official validation cannot pass without an internally valid candidate");
    }
}

std::string SolverResult::toJson(const std::string& candidatePath) const {
    validate();
    const auto quote = [](const std::string& value) {
        return json::escapeString(value);
    };
    const std::string path = candidate && !candidatePath.empty()
                                 ? quote(candidatePath)
                                 : "null";
    const std::string proofModel = optimalityModel.empty()
                                       ? "null" : quote(optimalityModel);
    const std::string proofObjective = optimalityObjective.empty()
                                           ? "null" : quote(optimalityObjective);
    return "{\n"
           "  \"schema_version\": 1,\n"
           "  \"solver_mode\": " + quote(solverMode) + ",\n"
           "  \"candidate_exists\": " + std::string(candidate ? "true" : "false") + ",\n"
           "  \"candidate_solution_path\": " + path + ",\n"
           "  \"internal_validation_status\": " +
           quote(toString(internalValidation)) + ",\n"
           "  \"official_validation_status\": " +
           quote(toString(officialValidation)) + ",\n"
           "  \"solver_completion_status\": " + quote(toString(completion)) + ",\n"
           "  \"optimality_proved\": " + (optimalityProved ? "true" : "false") + ",\n"
           "  \"optimality_model\": " + proofModel + ",\n"
           "  \"optimality_objective\": " + proofObjective + ",\n"
           "  \"algorithm_implementation\": " + quote(algorithmImplementation) + ",\n"
           "  \"candidate_source\": " + quote(candidateSource) + ",\n"
           "  \"runtime_seconds\": " + std::to_string(runtimeSeconds) + ",\n"
           "  \"termination_reason\": " + quote(terminationReason) + "\n"
           "}\n";
}

}  // namespace cgshop2027
