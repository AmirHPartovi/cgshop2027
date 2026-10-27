#include "algorithms/HybridSolver.h"

#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/MstcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <exception>
#include <functional>
#include <string>
#include <utility>
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
        return name != "ilp" &&
               std::find(config.heuristicPortfolio.begin(),
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

    struct Candidate {
        Solution solution;
        int64_t makespan;
    };
    std::vector<Candidate> candidates;
    std::vector<std::string> attempted;
    std::vector<std::string> failures;
    auto attempt = [&](const std::string& name, auto&& generate) {
        if (timeoutSeconds >= 0.0 && remaining() <= 0.0) return false;
        if (ExecutionControl::instance().cancelled()) return false;
        attempted.push_back(name);
        try {
            Solution candidate = generate();
            std::string error;
            if (!candidate.validate(problem_, &error)) {
                failures.push_back(name + ": invalid candidate: " + error);
                Logger::instance().warning(
                    "solver.hybrid", name + " candidate failed validation: " + error);
                return true;
            }
            const int64_t span = solutionMakespan(candidate);
            candidates.push_back({std::move(candidate), span});
            Logger::instance().debug(
                "solver.hybrid", "accepted " + name +
                                     " candidate makespan=" +
                                     std::to_string(span));
        } catch (const ExecutionCancelled&) {
            Logger::instance().warning(
                "solver.hybrid", "deadline reached; retaining the best validated incumbent");
            return false;
        } catch (const std::exception& error) {
            failures.push_back(name + ": " + error.what());
            Logger::instance().warning(
                "solver.hybrid", name + " candidate failed: " + error.what());
        }
        return true;
    };

    // A cheap partition candidate establishes an incumbent before optional search.
    if (!attempt("partition", [&] {
            return PartitioningAlgorithm(problem_).solve(remaining());
        }) && candidates.empty()) {
        throw ExecutionCancelled();
    }

    const std::vector<std::pair<std::string, std::function<Solution(double)>>> builders{
        {"frederickson", [&](double budget) {
             return FredericksonSplitAlgorithm(problem_).solve(budget);
         }},
        {"mstc", [&](double budget) {
             return MstcAlgorithm(problem_).solve(budget);
         }},
        {"connected-growth", [&](double budget) {
             return ConnectedGrowthAlgorithm(problem_, "hybrid").solve(budget);
         }},
    };
    for (const auto& builder : builders) {
        if (!selected(builder.first)) continue;
        if (!attempt(builder.first, [&] { return builder.second(remaining()); })) {
            break;
        }
    }

    if (candidates.empty()) {
        throw std::runtime_error(
            "heuristic portfolio produced no internally validated candidate");
    }

    const auto bestIt = std::min_element(
        candidates.begin(), candidates.end(),
        [](const Candidate& left, const Candidate& right) {
            return left.makespan < right.makespan;
        });
    Solution best = bestIt->solution;
    const int64_t bestSpan = bestIt->makespan;
    const std::string selectedAlgorithm =
        best.meta.count("requested_algorithm") != 0U
            ? best.meta.at("requested_algorithm")
            : best.meta.count("algorithm_implementation") != 0U
                  ? best.meta.at("algorithm_implementation")
                  : "unknown";
    best.meta["requested_algorithm"] = "hybrid";
    best.meta["portfolio_selected_algorithm"] = selectedAlgorithm;
    std::string generationOrder;
    for (const std::string& name : attempted) {
        if (!generationOrder.empty()) generationOrder += ',';
        generationOrder += name;
    }
    best.meta["candidate_generation_order"] = generationOrder;
    best.meta["constructive_makespan"] = std::to_string(bestSpan);
    best.meta["portfolio_attempted_builders"] = std::to_string(attempted.size());
    best.meta["portfolio_failed_builders"] = std::to_string(failures.size());
    for (size_t i = 0; i < failures.size(); ++i) {
        best.meta["portfolio_failure_" + std::to_string(i)] = failures[i];
    }

    if (ExecutionControl::instance().cancelled() ||
        (timeoutSeconds >= 0.0 && remaining() <= 0.0)) {
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        return best;
    }

    const auto lnsStarted = std::chrono::steady_clock::now();
    Solution improved;
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
        return best;
    }

    for (const auto& item : improved.meta) {
        if (item.first.rfind("lns_", 0) == 0U) best.meta[item.first] = item.second;
    }
    auto markLnsIncumbent = [&](Solution& incumbent) {
        incumbent.meta["requested_algorithm"] = "hybrid";
        incumbent.meta["portfolio_selected_algorithm"] = selectedAlgorithm;
        incumbent.meta["candidate_generation_order"] = generationOrder;
        incumbent.meta["algorithm_implementation"] = "hybrid";
        incumbent.meta["candidate_source"] = "hybrid_lns_improvement";
        incumbent.meta["improvement_status"] = "accepted_before_deadline";
        incumbent.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
    };
    if (ExecutionControl::instance().cancelled() ||
        (timeoutSeconds >= 0.0 && remaining() <= 0.0)) {
        // LNS validates every accepted move and returns its best validated incumbent.
        if (improved.meta.count("lns_improved") != 0U &&
            improved.meta.at("lns_improved") == "true") {
            markLnsIncumbent(improved);
            return improved;
        }
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        return best;
    }

    std::string error;
    bool improvedValid = false;
    try {
        improvedValid = improved.validate(problem_, &error);
    } catch (const ExecutionCancelled&) {
        if (improved.meta.count("lns_improved") != 0U &&
            improved.meta.at("lns_improved") == "true") {
            markLnsIncumbent(improved);
            return improved;
        }
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
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
        if (improved.meta.count("lns_improved") != 0U &&
            improved.meta.at("lns_improved") == "true") {
            markLnsIncumbent(improved);
            return improved;
        }
        best.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        return best;
    }
    if (improvedMakespan >= bestSpan) {
        best.meta["improvement_status"] = "no_strict_makespan_improvement";
        return best;
    }
    improved.meta["requested_algorithm"] = "hybrid";
    improved.meta["portfolio_selected_algorithm"] = selectedAlgorithm;
    improved.meta["candidate_generation_order"] = generationOrder;
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
