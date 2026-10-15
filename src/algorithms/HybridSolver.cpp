#include "algorithms/HybridSolver.h"

#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/IlpAlgorithm.h"
#include "algorithms/MstcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/RegionPartitionAssignAlgorithm.h"
#include "algorithms/StcAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "algorithms/TspCovAlgorithm.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <string>
#include <vector>

namespace cgshop2027 {
Solution HybridSolver::solve(double timeoutSeconds) {
    LogScope scope("solver.hybrid", "solve");
    Logger::instance().info(
        "solver.hybrid", "starting candidate portfolio timeout=" +
                              std::to_string(timeoutSeconds) + "s");
    const auto start = std::chrono::steady_clock::now();
    const auto& config = runtimeConfig();
    const auto selected = [&](const std::string& name) {
        return std::find(config.heuristicPortfolio.begin(),
                         config.heuristicPortfolio.end(), name) !=
               config.heuristicPortfolio.end();
    };
    auto remaining = [&] {
        if (timeoutSeconds < 0) return -1.0;
        const double used = std::chrono::duration<double>(
                                std::chrono::steady_clock::now() - start)
                                .count();
        return std::max(0.0, timeoutSeconds - used);
    };
    std::vector<Solution> candidates;
    auto consider = [&](Solution solution) {
        std::string error;
        if (solution.validate(problem_, &error)) {
            Logger::instance().debug("solver.hybrid", "accepted candidate");
            candidates.push_back(std::move(solution));
        } else {
            Logger::instance().warning("solver.hybrid",
                                       "rejected invalid candidate: " + error);
        }
    };
    bool cancellationObserved = false;
    auto attempt = [&](auto&& generate) {
        if (cancellationObserved) return;
        try {
            consider(generate());
        } catch (const ExecutionCancelled&) {
            cancellationObserved = true;
            Logger::instance().warning(
                "solver.hybrid", "deadline reached; retaining the best validated incumbent");
        }
    };
    if (selected("boustrophedon"))
        attempt([&] { return BoustrophedonAlgorithm(problem_).solve(remaining()); });
    if (selected("stc"))
        attempt([&] { return StcAlgorithm(problem_).solve(remaining()); });
    if (selected("frederickson"))
        attempt([&] { return FredericksonSplitAlgorithm(problem_).solve(remaining()); });
    if (selected("mstc"))
        attempt([&] { return MstcAlgorithm(problem_).solve(remaining()); });
    if (selected("region-partition"))
        attempt([&] { return RegionPartitionAssignAlgorithm(problem_).solve(remaining()); });
    if (selected("ilp"))
        attempt([&] { return IlpAlgorithm(problem_).solve(remaining()); });
    if (selected("connected-growth") || selected("column-gen"))
        attempt([&] {
            return ConnectedGrowthAlgorithm(problem_, "hybrid").solve(remaining());
        });
    if (selected("tsp-cov"))
        attempt([&] {
            const auto anchors = TourConstruction::coveringAnchors(problem_);
            if (anchors.size() >
                static_cast<size_t>(config.algorithmParameters.tspMaxAnchors)) {
                return Solution{};
            }
            return TspCovAlgorithm(problem_).solve(remaining());
        });
    if (candidates.empty()) {
        Logger::instance().warning(
            "solver.hybrid",
            "portfolio produced no validated candidate; falling back to partition");
        Solution fallback = PartitioningAlgorithm(problem_).solve(remaining());
        fallback.meta["requested_algorithm"] = "hybrid";
        fallback.meta["algorithm_implementation"] = "partition";
        fallback.meta["candidate_source"] = "partition_fallback";
        fallback.meta["fallback_algorithm"] = "partition";
        fallback.meta["fallback_reason"] =
            cancellationObserved
                ? "deadline reached before any portfolio candidate was validated"
                : "no portfolio candidate passed validation";
        if (cancellationObserved) {
            fallback.meta["execution_status"] =
                "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        }
        return fallback;
    }
    Solution best = candidates.front();
    int64_t bestSpan = solutionMakespan(best);
    for (const Solution& candidate : candidates) {
        const int64_t span = solutionMakespan(candidate);
        if (span < bestSpan) {
            best = candidate;
            bestSpan = span;
        }
    }
    const std::string selectedAlgorithm =
        best.meta.count("requested_algorithm") != 0U
            ? best.meta.at("requested_algorithm")
            : best.meta.count("algorithm_implementation") != 0U
                ? best.meta.at("algorithm_implementation") : "unknown";
    best.meta["requested_algorithm"] = "hybrid";
    best.meta["portfolio_selected_algorithm"] = selectedAlgorithm;
    best.meta["constructive_makespan"] = std::to_string(bestSpan);
    if (cancellationObserved || ExecutionControl::instance().cancelled()) {
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        best.meta["candidate_source"] = "hybrid_validated_incumbent";
        return best;
    }
    Solution improved;
    const auto lnsStarted = std::chrono::steady_clock::now();
    try {
        improved = TourConstruction::improveLns(
            problem_, best, start, timeoutSeconds,
            config.algorithmParameters.lnsIterations, config.randomSeed,
            config.algorithmParameters.lnsMaxAnchors,
            config.algorithmParameters.lnsMaxMoveAnchors);
    } catch (const ExecutionCancelled&) {
        best.meta["lns_accepted_moves_with_total_increase"] = "0";
        best.meta["lns_candidates_evaluated"] = "0";
        best.meta["lns_infeasible_candidates"] = "0";
        best.meta["lns_iterations_completed"] = "0";
        best.meta["lns_moves_accepted"] = "0";
        best.meta["lns_improved"] = "false";
        best.meta["lns_termination_reason"] = "cancelled_before_search";
        best.meta["lns_runtime_seconds"] = std::to_string(
            std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                          lnsStarted).count());
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        best.meta["candidate_source"] = "hybrid_validated_incumbent";
        return best;
    }
    if (ExecutionControl::instance().cancelled()) {
        for (const auto& item : improved.meta) {
            if (item.first.rfind("lns_", 0) == 0U) best.meta[item.first] = item.second;
        }
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        best.meta["candidate_source"] = "hybrid_validated_incumbent";
        return best;
    }
    for (const auto& item : improved.meta) {
        if (item.first.rfind("lns_", 0) == 0U) best.meta[item.first] = item.second;
    }
    std::string error;
    bool improvedValid = false;
    try {
        improvedValid = improved.validate(problem_, &error);
    } catch (const ExecutionCancelled&) {
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        best.meta["candidate_source"] = "hybrid_validated_incumbent";
        return best;
    }
    if (!improvedValid) {
        Logger::instance().warning("solver.hybrid",
                                   "LNS result invalid; retaining constructive best");
        best.meta["improvement_status"] = "rejected_invalid";
        best.meta["improvement_fallback_reason"] = error;
        return best;
    }
    int64_t improvedMakespan = 0;
    try {
        improvedMakespan = solutionMakespan(improved);
    } catch (const ExecutionCancelled&) {
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        best.meta["candidate_source"] = "hybrid_validated_incumbent";
        return best;
    }
    if (improvedMakespan >= bestSpan) {
        best.meta["improvement_status"] = "no_strict_makespan_improvement";
        return best;
    }
    improved.meta["requested_algorithm"] = "hybrid";
    improved.meta["portfolio_selected_algorithm"] = selectedAlgorithm;
    improved.meta["candidate_source"] = "hybrid_lns_improvement";
    improved.meta["algorithm_implementation"] = "hybrid";
    improved.meta["improvement_status"] = "accepted";
    Logger::instance().info("solver.hybrid", "completed candidates=" +
                                                 std::to_string(candidates.size()) +
                                                 " makespan=" +
                                                 std::to_string(improvedMakespan));
    return improved;
}
}  // namespace cgshop2027
