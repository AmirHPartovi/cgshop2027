#pragma once

#include "core/Solution.h"

#include <optional>
#include <string>

namespace cgshop2027 {

enum class CandidateValidationStatus {
    NotRun,
    Passed,
    Failed,
};

enum class OfficialValidationStatus {
    NotRequested,
    Passed,
    Failed,
    Unavailable,
};

enum class SolverCompletionStatus {
    Unavailable,
    Failed,
    Infeasible,
    TimedOutWithIncumbent,
    TimedOutWithoutIncumbent,
    FeasibleNotProven,
    Optimal,
};

struct SolverResult {
    std::string solverMode;
    std::optional<Solution> candidate;
    CandidateValidationStatus internalValidation{CandidateValidationStatus::NotRun};
    OfficialValidationStatus officialValidation{OfficialValidationStatus::NotRequested};
    SolverCompletionStatus completion{SolverCompletionStatus::Failed};
    bool optimalityProved{false};
    std::string optimalityModel;
    std::string optimalityObjective;
    std::string algorithmImplementation;
    std::string candidateSource;
    double runtimeSeconds{0.0};
    std::string terminationReason;

    bool hasCandidate() const { return candidate.has_value(); }
    void validate() const;
    std::string toJson(const std::string& candidatePath = {}) const;
};

const char* toString(CandidateValidationStatus status);
const char* toString(OfficialValidationStatus status);
const char* toString(SolverCompletionStatus status);

}  // namespace cgshop2027
