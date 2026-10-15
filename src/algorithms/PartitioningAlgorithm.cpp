#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"

#include <algorithm>

namespace cgshop2027 {
Solution PartitioningAlgorithm::solve(double) {
    LogScope scope("algorithm.partition", "solve");
    const auto cells = problem_.regionCells();
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);
    // A serpentine ordering is connected in the cell grid and gives balanced parts.
    std::sort(centers.begin(), centers.end(), [](Point a, Point b) {
        return a.y == b.y ? (((a.y & 1) == 0) ? a.x < b.x : a.x > b.x) : a.y < b.y;
    });
    for (size_t i = 0; i < centers.size(); ++i)
        groups[i * groups.size() / std::max<size_t>(1, centers.size())].push_back(centers[i]);
    (void)cells;
    return makeSolution(problem_, groups);
}
}  // namespace cgshop2027
