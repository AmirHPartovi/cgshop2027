#include "algorithms/LnsMultiCutterAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "utils/Logger.h"

#include <chrono>

namespace cgshop2027 {
Solution LnsMultiCutterAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.lns", "solve");
    const auto start = std::chrono::steady_clock::now();
    Solution initial = FredericksonSplitAlgorithm(problem_).solve(timeoutSeconds);
    Solution solution = TourConstruction::improveLns(problem_, initial, start, timeoutSeconds);
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    return solution;
}
}  // namespace cgshop2027
