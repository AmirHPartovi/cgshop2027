#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

namespace cgshop2027 {
Solution BoustrophedonAlgorithm::solve(double) {
    LogScope scope("algorithm.boustrophedon", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_, {TourConstruction::boustrophedon(anchors)});
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve();
    }
    return solution;
}
}  // namespace cgshop2027
