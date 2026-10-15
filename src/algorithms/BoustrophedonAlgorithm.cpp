#include "algorithms/BoustrophedonAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

#include <utility>

namespace cgshop2027 {
Solution BoustrophedonAlgorithm::solve(double timeoutSeconds) {
    LogScope logScope("algorithm.boustrophedon", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_, {TourConstruction::boustrophedon(anchors)});
    const std::string routeScope = problem_.numberOfCutters > 1
        ? "single_route_with_stationary_padding" : "single_route";
    return finishCandidate(
        std::move(solution), "boustrophedon", timeoutSeconds, routeScope);
}
}  // namespace cgshop2027
