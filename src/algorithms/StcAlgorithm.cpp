#include "algorithms/StcAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

#include <utility>

namespace cgshop2027 {
Solution StcAlgorithm::solve(double timeoutSeconds) {
    LogScope logScope("algorithm.stc", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_, {TourConstruction::spanningTreeWalk(anchors)});
    const std::string routeScope = problem_.numberOfCutters > 1
        ? "single_route_with_stationary_padding" : "single_route";
    return finishCandidate(
        std::move(solution), "stc", timeoutSeconds, routeScope);
}
}  // namespace cgshop2027
