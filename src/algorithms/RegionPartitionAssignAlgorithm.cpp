#include "utils/Logger.h"
#include "algorithms/RegionPartitionAssignAlgorithm.h"
#include "algorithms/TourConstruction.h"

#include <utility>

namespace cgshop2027 {
Solution RegionPartitionAssignAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.region-partition", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_, TourConstruction::recursiveBisectionTours(
                                      anchors, problem_.numberOfCutters));
    return finishCandidate(
        std::move(solution), "region-partition", timeoutSeconds);
}
}  // namespace cgshop2027
