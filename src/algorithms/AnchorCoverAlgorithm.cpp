#include "algorithms/AnchorCoverAlgorithm.h"
#include "core/ExecutionControl.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <unordered_set>
#include <utility>

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
            for (size_t i = 0; i < centers.size(); ++i) {
                if ((i & 0x3ffU) == 0U)
                    ExecutionControl::instance().checkpoint();
                if (!used[i]) groups[i % groups.size()].push_back(centers[i]);
            }
            break;
        }
        size_t best = centers.size();
        size_t bestGain = 0;
        for (size_t i = 0; i < centers.size(); ++i) {
            if ((i & 0x3fU) == 0U)
                ExecutionControl::instance().checkpoint();
            if ((i & 0x3fU) == 0U && timedOut(start, timeoutSeconds)) break;
            if (used[i]) continue;
            size_t gain = 0;
            size_t shapeVisits = 0;
            for (const Point cell : shape) {
                if ((shapeVisits++ & 0x3ffU) == 0U)
                    ExecutionControl::instance().checkpoint();
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
        size_t shapeVisits = 0;
        for (const Point cell : shape) {
            if ((shapeVisits++ & 0x3ffU) == 0U)
                ExecutionControl::instance().checkpoint();
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
    return finishCandidate(std::move(solution), "anchor-cover", timeoutSeconds);
}

}  // namespace cgshop2027
