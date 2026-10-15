#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "utils/Logger.h"

#include <chrono>

namespace cgshop2027 {
Solution ColumnGenerationAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.column-generation", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_,
                        TourConstruction::columnGenerationTours(
                            anchors, problem_.numberOfCutters, start, timeoutSeconds));
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    return solution;
}
}  // namespace cgshop2027
