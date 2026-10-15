#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "utils/Logger.h"

#include <chrono>
#include <utility>

namespace cgshop2027 {
Solution ColumnGenerationAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.column-generation", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_,
                        TourConstruction::columnGenerationTours(
                            anchors, problem_.numberOfCutters, start, timeoutSeconds));
    return finishCandidate(
        std::move(solution), "column-gen", timeoutSeconds,
        "multi_cutter_greedy_growth");
}
}  // namespace cgshop2027
