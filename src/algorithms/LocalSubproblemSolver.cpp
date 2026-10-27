#include "algorithms/LocalSubproblemSolver.h"

#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

namespace cgshop2027 {
namespace {
Point coverageAnchor(const Problem& problem, Point cell, Point cutterCell) {
    const int64_t x = static_cast<int64_t>(cell.x) + problem.cutterCenter.x -
                      cutterCell.x;
    const int64_t y = static_cast<int64_t>(cell.y) + problem.cutterCenter.y -
                      cutterCell.y;
    if (x < std::numeric_limits<int>::min() ||
        x > std::numeric_limits<int>::max() ||
        y < std::numeric_limits<int>::min() ||
        y > std::numeric_limits<int>::max()) {
        throw std::overflow_error("decomposition coverage anchor exceeds coordinate range");
    }
    return {static_cast<int>(x), static_cast<int>(y)};
}

}  // namespace

LocalSubproblemResult LocalSubproblemSolver::solve(
    const Problem& problem, const RegionSubproblem& subproblem) const {
    ExecutionControl::instance().checkpoint();
    LocalSubproblemResult result;
    result.subproblemId = subproblem.id;
    result.exact = false;
    result.status = "HEURISTIC_OPTIONS_AVAILABLE";
    if (subproblem.targetCells.empty()) {
        result.status = "NO_TARGET_CELLS";
        return result;
    }
    std::vector<Point> anchors = subproblem.coverageAnchors;
    if (anchors.empty()) {
        const auto cutter = problem.cutterCells();
        if (cutter.empty()) {
            result.status = "NO_CUTTER_CELLS";
            return result;
        }
        const Point reference = *std::min_element(cutter.begin(), cutter.end());
        anchors.reserve(subproblem.targetCells.size());
        for (size_t i = 0; i < subproblem.targetCells.size(); ++i) {
            if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
            anchors.push_back(coverageAnchor(
                problem, subproblem.targetCells[i], reference));
        }
    }
    std::sort(anchors.begin(), anchors.end());
    anchors.erase(std::unique(anchors.begin(), anchors.end()), anchors.end());

    std::vector<std::pair<std::string, std::vector<Point>>> alternatives;
    alternatives.emplace_back("boustrophedon", TourConstruction::boustrophedon(anchors));
    alternatives.emplace_back("spanning_tree_walk", TourConstruction::spanningTreeWalk(anchors));
    for (auto& alternative : alternatives) {
        ExecutionControl::instance().checkpoint();
        const auto duplicate = std::find_if(
            result.options.begin(), result.options.end(),
            [&](const LocalRouteOption& option) {
                return option.route == alternative.second;
            });
        if (duplicate != result.options.end()) continue;
        const int64_t length = TourConstruction::closedLength(alternative.second);
        result.options.push_back({
            std::move(alternative.second),
            length,
            std::move(alternative.first),
        });
    }
    if (result.options.empty()) {
        result.status = "NO_LOCAL_CANDIDATE";
        return result;
    }
    std::sort(result.options.begin(), result.options.end(),
              [](const LocalRouteOption& left, const LocalRouteOption& right) {
                  if (left.closedLength != right.closedLength)
                      return left.closedLength < right.closedLength;
                  return left.source < right.source;
              });
    return result;
}

}  // namespace cgshop2027
