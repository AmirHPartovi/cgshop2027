#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "utils/Logger.h"

#include <chrono>
#include <utility>

namespace cgshop2027 {
ConnectedGrowthAlgorithm::ConnectedGrowthAlgorithm(const Problem& problem,
                                                   std::string requestedAlgorithm)
    : BaseAlgorithm(problem), requestedAlgorithm_(std::move(requestedAlgorithm)) {}

Solution ConnectedGrowthAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.connected-growth", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    const auto result = TourConstruction::connectedGrowthTours(
        anchors, problem_.numberOfCutters, start, timeoutSeconds);
    Solution solution = finishCandidate(
        makeSolution(problem_, result.tours), "connected-growth", timeoutSeconds,
        "connected_growth_budget_search");
    solution.meta["requested_algorithm"] = requestedAlgorithm_;
    solution.meta["connected_growth_search_status"] =
        result.timedOut ? "TIMEOUT_UNKNOWN"
                        : (result.budgetChecks > 0 ? "COMPLETED" : "NOT_RUN");
    solution.meta["connected_growth_budget_checks"] =
        std::to_string(result.budgetChecks);
    if (result.timedOut)
        solution.meta["connected_growth_termination_reason"] =
            "budget feasibility search interrupted; retained baseline candidate";
    return solution;
}
}  // namespace cgshop2027
