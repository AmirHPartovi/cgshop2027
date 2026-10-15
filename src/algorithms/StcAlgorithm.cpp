#include "algorithms/StcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

namespace cgshop2027 {
Solution StcAlgorithm::solve(double) {
    LogScope scope("algorithm.stc", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_, {TourConstruction::spanningTreeWalk(anchors)});
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve();
    }
    return solution;
}
}  // namespace cgshop2027
