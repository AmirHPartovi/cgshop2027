#include "algorithms/BalancedGreedyRouteAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"

#include <chrono>
#include <limits>

namespace cgshop2027 {

Solution BalancedGreedyRouteAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.balanced-greedy", "solve");
    const auto start = std::chrono::steady_clock::now();
    auto centers = coverageCenters(problem_);
    std::vector<std::vector<Point>> groups(
        static_cast<size_t>(problem_.numberOfCutters));
    if (groups.empty()) return makeSolution(problem_, groups);
    std::vector<Point> current(groups.size(), problem_.cutterCenter);
    std::vector<double> lengths(groups.size(), 0.0);
    std::vector<bool> used(centers.size(), false);
    size_t remaining = centers.size();
    while (remaining != 0U) {
        size_t group = 0;
        for (size_t i = 1; i < groups.size(); ++i)
            if (lengths[i] < lengths[group]) group = i;
        size_t best = centers.size();
        double score = std::numeric_limits<double>::infinity();
        for (size_t i = 0; i < centers.size(); ++i) {
            if (used[i]) continue;
            const double distance = static_cast<double>(
                current[group].manhattanDistance(centers[i]));
            const double scoreForCenter = distance + lengths[group] * 0.15;
            if (best == centers.size() || scoreForCenter < score ||
                (scoreForCenter == score && centers[i] < centers[best])) {
                best = i;
                score = scoreForCenter;
            }
        }
        if (best == centers.size()) break;
        groups[group].push_back(centers[best]);
        lengths[group] += static_cast<double>(
            current[group].manhattanDistance(centers[best]));
        current[group] = centers[best];
        used[best] = true;
        --remaining;
        if (timedOut(start, timeoutSeconds)) {
            for (size_t i = 0; i < centers.size(); ++i)
                if (!used[i]) groups[i % groups.size()].push_back(centers[i]);
            break;
        }
    }
    Solution solution = makeSolution(problem_, groups);
    std::string error;
    if (!solution.validate(problem_, &error)) {
        return PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    return solution;
}

}
