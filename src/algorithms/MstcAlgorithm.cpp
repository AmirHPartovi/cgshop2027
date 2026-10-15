#include "algorithms/MstcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

namespace cgshop2027 {
Solution MstcAlgorithm::solve(double) {
    LogScope scope("algorithm.mstc", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_,
                        TourConstruction::mstc(anchors, problem_.numberOfCutters));
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve();
    }
    return solution;
}
}  // namespace cgshop2027
