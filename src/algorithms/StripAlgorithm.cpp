#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/StripAlgorithm.h"

#include <algorithm>

namespace cgshop2027 {
Solution StripAlgorithm::solve(double) {
    LogScope scope("algorithm.strip", "solve");
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);
    std::sort(centers.begin(), centers.end(), [](Point a, Point b) {
        return a.y == b.y ? a.x < b.x : a.y < b.y;
    });
    for (size_t i = 0; i < centers.size(); ++i)
        groups[i * groups.size() / std::max<size_t>(1, centers.size())].push_back(centers[i]);
    Solution solution = makeSolution(problem_, groups);
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve();
    }
    return solution;
}
}  // namespace cgshop2027
