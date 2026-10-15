#include "utils/Logger.h"
#include "algorithms/StripAlgorithm.h"
#include "core/ExecutionControl.h"

#include <algorithm>
#include <utility>

namespace cgshop2027 {
Solution StripAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.strip", "solve");
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);
    std::sort(centers.begin(), centers.end(), [](Point a, Point b) {
        return a.y == b.y ? a.x < b.x : a.y < b.y;
    });
    for (size_t i = 0; i < centers.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        groups[i * groups.size() / std::max<size_t>(1, centers.size())].push_back(centers[i]);
    }
    Solution solution = makeSolution(problem_, groups);
    return finishCandidate(std::move(solution), "strip", timeoutSeconds);
}
}  // namespace cgshop2027
