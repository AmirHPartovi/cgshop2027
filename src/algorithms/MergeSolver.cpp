#include "algorithms/MergeSolver.h"

#include "algorithms/BaseAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"

#include <algorithm>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <tuple>

namespace cgshop2027 {
namespace {
int64_t distance(Point left, Point right) {
    return std::llabs(static_cast<int64_t>(left.x) - right.x) +
           std::llabs(static_cast<int64_t>(left.y) - right.y);
}

int64_t openLength(const std::vector<Point>& route) {
    int64_t result = 0;
    for (size_t i = 1; i < route.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        result += distance(route[i - 1U], route[i]);
    }
    return result;
}

struct MergedRoute {
    std::vector<Point> points;
    int64_t openLength{0};

    int64_t closedLength() const {
        if (points.empty()) return 0;
        return openLength + distance(points.back(), points.front());
    }
};

}  // namespace

MergeResult MergeSolver::merge(
    const Problem& problem,
    const std::vector<LocalSubproblemResult>& localResults) const {
    MergeResult result;
    const size_t cutters = static_cast<size_t>(problem.numberOfCutters);
    if (cutters == 0U) {
        result.status = "NO_CUTTERS";
        return result;
    }
    std::vector<MergedRoute> routes(cutters);
    result.cutterAllocations.assign(localResults.size(), cutters);

    for (size_t region = 0; region < localResults.size(); ++region) {
        ExecutionControl::instance().checkpoint();
        const auto& local = localResults[region];
        if (local.options.empty()) {
            result.status = "LOCAL_NO_INCUMBENT";
            return result;
        }
        bool found = false;
        size_t bestCutter = 0;
        size_t bestOption = 0;
        bool bestReverse = false;
        int64_t bestSpan = std::numeric_limits<int64_t>::max();
        int64_t bestTotal = std::numeric_limits<int64_t>::max();
        for (size_t cutter = 0; cutter < cutters; ++cutter) {
            for (size_t optionIndex = 0;
                 optionIndex < local.options.size(); ++optionIndex) {
                const auto& option = local.options[optionIndex];
                if (option.route.empty()) continue;
                const int64_t fragmentOpen = openLength(option.route);
                for (int reverse = 0; reverse < 2; ++reverse) {
                    ExecutionControl::instance().checkpoint();
                    const Point fragmentStart = reverse == 0
                        ? option.route.front() : option.route.back();
                    const Point fragmentEnd = reverse == 0
                        ? option.route.back() : option.route.front();
                    int64_t candidateOpen = fragmentOpen;
                    if (!routes[cutter].points.empty()) {
                        candidateOpen += routes[cutter].openLength +
                            distance(routes[cutter].points.back(), fragmentStart);
                    }
                    const int64_t candidateSpan = candidateOpen +
                        distance(fragmentEnd,
                                 routes[cutter].points.empty()
                                     ? fragmentStart
                                     : routes[cutter].points.front());
                    int64_t globalSpan = candidateSpan;
                    int64_t totalLength = candidateSpan;
                    for (size_t other = 0; other < cutters; ++other) {
                        if (other == cutter) continue;
                        const int64_t span = routes[other].closedLength();
                        globalSpan = std::max(globalSpan, span);
                        totalLength += span;
                    }
                    if (!found || globalSpan < bestSpan ||
                        (globalSpan == bestSpan && totalLength < bestTotal) ||
                        (globalSpan == bestSpan && totalLength == bestTotal &&
                         std::tuple<size_t, size_t, bool>(
                             cutter, optionIndex, reverse != 0) <
                             std::tuple<size_t, size_t, bool>(
                                 bestCutter, bestOption, bestReverse))) {
                        found = true;
                        bestSpan = globalSpan;
                        bestTotal = totalLength;
                        bestCutter = cutter;
                        bestOption = optionIndex;
                        bestReverse = reverse != 0;
                    }
                }
            }
        }
        if (!found) {
            result.status = "NO_MERGE_OPTION";
            return result;
        }

        const auto& chosen = local.options[bestOption].route;
        auto& destination = routes[bestCutter];
        const Point start = bestReverse ? chosen.back() : chosen.front();
        if (destination.points.empty()) {
            destination.points = chosen;
            if (bestReverse) std::reverse(destination.points.begin(), destination.points.end());
            destination.openLength = openLength(chosen);
        } else {
            destination.openLength += distance(destination.points.back(), start) +
                                      openLength(chosen);
            if (bestReverse) {
                destination.points.insert(destination.points.end(),
                                          chosen.rbegin(), chosen.rend());
            } else {
                destination.points.insert(destination.points.end(),
                                          chosen.begin(), chosen.end());
            }
        }
        result.cutterAllocations[region] = bestCutter;
    }

    std::vector<std::vector<Point>> groups;
    groups.reserve(cutters);
    for (auto& route : routes) groups.push_back(std::move(route.points));
    result.solution = BaseAlgorithm::makeSolution(problem, groups);
    std::string error;
    if (!result.solution.validate(problem, &error)) {
        result.solution = {};
        result.status = "GLOBAL_VALIDATION_FAILED";
        return result;
    }
    result.makespan = solutionMakespan(result.solution);
    result.status = "FEASIBLE_HEURISTIC_MERGE";
    return result;
}

}  // namespace cgshop2027
