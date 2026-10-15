#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/RegionPartitionAssignAlgorithm.h"
#include "algorithms/TourConstruction.h"

namespace cgshop2027 {
Solution RegionPartitionAssignAlgorithm::solve(double) {
    LogScope scope("algorithm.region-partition", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_, TourConstruction::recursiveBisectionTours(
                                      anchors, problem_.numberOfCutters));
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve();
    }
    return solution;
}
}  // namespace cgshop2027
