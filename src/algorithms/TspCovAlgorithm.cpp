#include "utils/Logger.h"
#include "algorithms/TspCovAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/RuntimeConfig.h"

#include <chrono>
#include <utility>

namespace cgshop2027 {
Solution TspCovAlgorithm::solve(double timeoutSeconds) {
    LogScope logScope("algorithm.tsp-cov", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_,
                     {TourConstruction::tspCov(
                         anchors, start, timeoutSeconds,
                         runtimeConfig().algorithmParameters.tspMaxAnchors,
                         runtimeConfig().algorithmParameters.twoOptPasses)});
    const std::string routeScope = problem_.numberOfCutters > 1
        ? "single_route_with_stationary_padding" : "single_route";
    return finishCandidate(
        std::move(solution), "tsp-cov", timeoutSeconds, routeScope);
}
}  // namespace cgshop2027
