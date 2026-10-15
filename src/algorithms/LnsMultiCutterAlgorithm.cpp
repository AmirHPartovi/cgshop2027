#include "algorithms/LnsMultiCutterAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <chrono>

namespace cgshop2027 {
Solution LnsMultiCutterAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.lns", "solve");
    const auto start = std::chrono::steady_clock::now();
    Solution initial = FredericksonSplitAlgorithm(problem_).solve(timeoutSeconds);
    const auto initialImplementation = initial.meta.count("algorithm_implementation")
        ? initial.meta.at("algorithm_implementation") : "frederickson";
    const auto initialSource = initial.meta.count("candidate_source")
        ? initial.meta.at("candidate_source") : "frederickson";
    Solution solution;
    try {
        solution = TourConstruction::improveLns(
            problem_, initial, start, timeoutSeconds,
            runtimeConfig().algorithmParameters.lnsIterations,
            runtimeConfig().randomSeed,
            runtimeConfig().algorithmParameters.lnsMaxAnchors,
            runtimeConfig().algorithmParameters.lnsMaxMoveAnchors);
    } catch (const ExecutionCancelled&) {
        initial.meta["execution_status"] =
            "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        initial.meta["candidate_source"] = initialSource;
        initial.meta["algorithm_implementation"] = initialImplementation;
        initial.meta["requested_algorithm"] = "lns";
        initial.meta["requested_route_assignment_scope"] =
            "local_search_from_initial_tour";
        initial.meta["effective_route_assignment_scope"] =
            "local_search_from_initial_tour";
        initial.meta["lns_accepted_moves_with_total_increase"] = "0";
        initial.meta["lns_candidates_evaluated"] = "0";
        initial.meta["lns_infeasible_candidates"] = "0";
        initial.meta["lns_iterations_completed"] = "0";
        initial.meta["lns_moves_accepted"] = "0";
        initial.meta["lns_improved"] = "false";
        initial.meta["lns_termination_reason"] = "cancelled_before_search";
        initial.meta["lns_runtime_seconds"] = "0";
        return initial;
    }
    const bool timedOut = ExecutionControl::instance().cancelled();
    if (timedOut) {
        for (const auto& item : solution.meta) {
            if (item.first.rfind("lns_", 0) == 0U) initial.meta[item.first] = item.second;
        }
        initial.meta["execution_status"] =
            "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        initial.meta["candidate_source"] = initialSource;
        initial.meta["lns_initial_candidate_source"] = initialSource;
        initial.meta["algorithm_implementation"] = initialImplementation;
        initial.meta["requested_algorithm"] = "lns";
        return initial;
    }
    const bool improvedIncumbent =
        solutionMakespan(solution) < solutionMakespan(initial);
    solution = finishCandidate(
        std::move(solution), "lns", timeoutSeconds,
        "local_search_from_initial_tour");
    solution.meta["lns_initial_candidate_source"] = initialSource;
    if (timedOut) {
        solution.meta["execution_status"] =
            "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        solution.meta["lns_termination_reason"] = "cooperative deadline reached";
    }
    if (!improvedIncumbent) {
        solution.meta["algorithm_implementation"] = initialImplementation;
        solution.meta["candidate_source"] = initialSource;
    }
    return solution;
}
}  // namespace cgshop2027
