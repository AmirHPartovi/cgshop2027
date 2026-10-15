#include "algorithms/PartitioningAlgorithm.h"
#include "core/ExecutionControl.h"
#include "utils/Logger.h"

#include <algorithm>

namespace cgshop2027 {
Solution PartitioningAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.partition", "solve");
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);
    // A serpentine ordering is connected in the cell grid and gives balanced parts.
    std::sort(centers.begin(), centers.end(), [](Point a, Point b) {
        return a.y == b.y ? (((a.y & 1) == 0) ? a.x < b.x : a.x > b.x) : a.y < b.y;
    });
    for (size_t i = 0; i < centers.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        groups[i * groups.size() / std::max<size_t>(1, centers.size())].push_back(centers[i]);
    }
    return finishCandidate(
        makeSolution(problem_, groups), "partition", timeoutSeconds,
        "multi_cutter_partition");
}
}  // namespace cgshop2027
