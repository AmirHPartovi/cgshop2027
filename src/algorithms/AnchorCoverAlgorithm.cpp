#include "algorithms/AnchorCoverAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <unordered_set>

namespace cgshop2027 {

Solution AnchorCoverAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.anchor-cover", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto target = problem_.regionCells();
    const auto shape = problem_.cutterCells();
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(
        static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);

    std::unordered_set<Point, PointHash> covered;
    std::vector<bool> used(centers.size(), false);
    std::vector<double> load(groups.size(), 0.0);
    std::vector<Point> last(groups.size(), problem_.cutterCenter);
    size_t remaining = centers.size();
    while (remaining != 0U) {
        if (timedOut(start, timeoutSeconds)) {
            for (size_t i = 0; i < centers.size(); ++i)
                if (!used[i]) groups[i % groups.size()].push_back(centers[i]);
            break;
        }
        size_t best = centers.size();
        size_t bestGain = 0;
        for (size_t i = 0; i < centers.size(); ++i) {
            if (timedOut(start, timeoutSeconds)) break;
            if (used[i]) continue;
            size_t gain = 0;
            for (const Point cell : shape) {
                const Point coveredCell{centers[i].x + cell.x - problem_.cutterCenter.x,
                                        centers[i].y + cell.y - problem_.cutterCenter.y};
                if (target.count(coveredCell) != 0U && covered.count(coveredCell) == 0U)
                    ++gain;
            }
            if (best == centers.size() || gain > bestGain ||
                (gain == bestGain && centers[i] < centers[best])) {
                best = i;
                bestGain = gain;
            }
        }
        if (best == centers.size()) break;
        size_t group = 0;
        for (size_t i = 1; i < groups.size(); ++i)
            if (load[i] < load[group]) group = i;
        groups[group].push_back(centers[best]);
        for (const Point cell : shape) {
            const Point coveredCell{centers[best].x + cell.x - problem_.cutterCenter.x,
                                    centers[best].y + cell.y - problem_.cutterCenter.y};
            if (target.count(coveredCell) != 0U) covered.insert(coveredCell);
        }
        load[group] += static_cast<double>(last[group].manhattanDistance(centers[best]));
        last[group] = centers[best];
        used[best] = true;
        --remaining;
    }
    Solution solution = makeSolution(problem_, groups);
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    return solution;
}

}  // namespace cgshop2027
