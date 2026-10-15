#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TspCovAlgorithm.h"
#include "algorithms/TourConstruction.h"

#include <chrono>

namespace cgshop2027 {
Solution TspCovAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.tsp-cov", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution =
        makeSolution(problem_,
                     {TourConstruction::tspCov(anchors, start, timeoutSeconds)});
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    return solution;
}
}  // namespace cgshop2027
