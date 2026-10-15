#include "algorithms/LocalSearch.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <chrono>
#include <utility>

namespace cgshop2027 {
LocalSearch::LocalSearch(const Problem& problem, Solution initial)
    : BaseAlgorithm(problem), initial_(std::move(initial)) {}

Solution LocalSearch::solve(double timeoutSeconds) {
    LogScope scope("algorithm.local-search", "solve");
    const auto start = std::chrono::steady_clock::now();
    Solution best = initial_;
    std::string error;
    bool toursAreClosed = best.tours.size() ==
                          static_cast<size_t>(problem_.numberOfCutters);
    if (toursAreClosed) {
        for (const auto& tour : best.tours)
            toursAreClosed = toursAreClosed && validTour(tour);
    }
    if (!toursAreClosed || !best.validate(problem_, &error)) {
        if (error.empty()) error = "initial candidate has an incorrect number or shape of tours";
        best = {};
        best.instanceUid = problem_.instanceUid;
        best.contentType = "CGSHOP2027_Solution";
        best.meta["local_search_initial_candidate_error"] = error;
        return finishCandidate(
            std::move(best), "local", timeoutSeconds,
            "local_improvement_of_initial_candidate");
    }
    const auto& parameters = runtimeConfig().algorithmParameters;
    try {
        best = TourConstruction::improveLns(
            problem_, best, start, timeoutSeconds,
            parameters.lnsIterations, runtimeConfig().randomSeed,
            parameters.lnsMaxAnchors, parameters.lnsMaxMoveAnchors);
    } catch (const ExecutionCancelled&) {
        best.meta["lns_termination_reason"] = "cancelled_before_search";
        best.meta["lns_candidates_evaluated"] = "0";
        best.meta["lns_moves_accepted"] = "0";
        best.meta["lns_accepted_moves_with_total_increase"] = "0";
        best.meta["lns_infeasible_candidates"] = "0";
        best.meta["lns_iterations_completed"] = "0";
        best.meta["lns_improved"] = "false";
        best.meta["lns_runtime_seconds"] = std::to_string(
            std::chrono::duration<double>(std::chrono::steady_clock::now() - start)
                .count());
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        return best;
    }
    if (ExecutionControl::instance().cancelled()) {
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        return best;
    }
    return finishCandidate(
        std::move(best), "local", timeoutSeconds,
        "anchor_assignment_reconstruction");
}
}  // namespace cgshop2027
