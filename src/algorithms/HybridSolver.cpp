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
    consider(BoustrophedonAlgorithm(problem_).solve(remaining()));
    consider(StcAlgorithm(problem_).solve(remaining()));
    consider(FredericksonSplitAlgorithm(problem_).solve(remaining()));
    consider(MstcAlgorithm(problem_).solve(remaining()));
    consider(RegionPartitionAssignAlgorithm(problem_).solve(remaining()));
    consider(IlpAlgorithm(problem_).solve(remaining()));
    consider(ColumnGenerationAlgorithm(problem_).solve(remaining()));
    if (TourConstruction::coveringAnchors(problem_).size() <= 2500U)
        consider(TspCovAlgorithm(problem_).solve(remaining()));
    if (candidates.empty())
        return PartitioningAlgorithm(problem_).solve(remaining());
    Solution best = candidates.front();
    int bestSpan = TourConstruction::closedLength(best.tours.front().points);
    for (const Tour& tour : best.tours)
        bestSpan = std::max(bestSpan, TourConstruction::closedLength(tour.points));
    for (const Solution& candidate : candidates) {
        int span = 0;
        for (const Tour& tour : candidate.tours)
            span = std::max(span, TourConstruction::closedLength(tour.points));
        if (span < bestSpan) {
            best = candidate;
            bestSpan = span;
        }
    }
    best.meta["area_lower_bound"] = std::to_string(TourConstruction::areaLowerBound(problem_));
    best.meta["constructive_makespan"] = std::to_string(bestSpan);
    Solution improved =
        TourConstruction::improveLns(problem_, best, start, timeoutSeconds);
    std::string error;
    if (!improved.validate(problem_, &error)) {
        Logger::instance().warning("solver.hybrid",
                                   "LNS result invalid; retaining constructive best");
        return best;
    }
    Logger::instance().info("solver.hybrid", "completed candidates=" +
                                                 std::to_string(candidates.size()) +
                                                 " makespan=" +
                                                 std::to_string(bestSpan));
    return improved;
}
}  // namespace cgshop2027
