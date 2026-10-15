#include "algorithms/BaseAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "core/ExecutionControl.h"
#include "utils/Logger.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <unordered_set>

namespace cgshop2027 {

Tour BaseAlgorithm::makeClosedTour(const std::vector<Point>& input,
                                  Point stationaryCenter) {
    Tour result;
    if (input.empty()) {
        result.points.push_back(stationaryCenter);
        return result;
    }
    std::vector<Point> path;
    path.reserve(input.size());
    size_t visited = 0;
    for (const Point point : input) {
        if ((visited++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (path.empty() || path.back() != point) path.push_back(point);
    }
    if (path.size() > 1U && path.front() == path.back()) path.pop_back();
    if (path.size() == 1U) {
        result.points = std::move(path);
        return result;
    }
    result.points.push_back(path.front());
    for (size_t i = 1; i < path.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        const Point a = result.points.back();
        const Point b = path[i];
        if (a.x != b.x && a.y != b.y) result.points.push_back({b.x, a.y});
        result.points.push_back(b);
    }
    const Point first = path.front();
    const Point last = result.points.back();
    if (last.x != first.x && last.y != first.y) {
        result.points.push_back({first.x, last.y});
    }
    return result;
}

std::vector<Point> BaseAlgorithm::coverageCenters(const Problem& problem) {
    const auto cells = problem.regionCells();
    const auto cutter = problem.cutterCells();
    std::vector<Point> result;
    if (cutter.empty()) return result;
    const Point anchor = *std::min_element(cutter.begin(), cutter.end());
    result.reserve(cells.size());
    size_t visited = 0;
    for (const Point cell : cells) {
        if ((visited++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        result.push_back({cell.x + problem.cutterCenter.x - anchor.x,
                          cell.y + problem.cutterCenter.y - anchor.y});
    }
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    Logger::instance().debug(
        "algorithm", "computed coverage centers=" + std::to_string(result.size()));
    return result;
}

bool BaseAlgorithm::validTour(const Tour& tour) {
    if (tour.points.empty()) return false;
    if (tour.points.size() == 1U) return true;
    for (size_t i = 0; i < tour.points.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        const Point& a = tour.points[i];
        const Point& b = tour.points[(i + 1) % tour.points.size()];
        if (a == b || (a.x != b.x && a.y != b.y)) return false;
    }
    return true;
}

int64_t BaseAlgorithm::tourLength(const Tour& tour) {
    return closedTourLength(tour.points);
}

int64_t BaseAlgorithm::makespan(const Solution& solution) {
    return solutionMakespan(solution);
}

bool BaseAlgorithm::timedOut(const std::chrono::steady_clock::time_point& start,
                             double limit) {
    if (ExecutionControl::instance().cancelled()) return true;
    return limit >= 0 && std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start).count() >= limit;
}

Solution BaseAlgorithm::makeSolution(const Problem& problem,
                                      const std::vector<std::vector<Point>>& groups) {
    if (groups.size() > static_cast<size_t>(problem.numberOfCutters)) {
        throw std::invalid_argument(
            "candidate has more route groups than the instance cutter count");
    }
    Solution solution;
    solution.contentType = "CGSHOP2027_Solution";
    solution.instanceUid = problem.instanceUid;
    solution.tours.reserve(static_cast<size_t>(problem.numberOfCutters));
    for (const auto& group : groups) {
        ExecutionControl::instance().checkpoint();
        solution.tours.push_back(makeClosedTour(group, problem.cutterCenter));
    }
    while (solution.tours.size() < static_cast<size_t>(problem.numberOfCutters)) {
        ExecutionControl::instance().checkpoint();
        solution.tours.push_back(makeClosedTour({}, problem.cutterCenter));
    }
    return solution;
}

Solution BaseAlgorithm::finishCandidate(
    Solution candidate, const std::string& algorithm, double timeoutSeconds,
    const std::string& routeAssignmentScope) const {
    std::string validationError;
    if (!candidate.validate(problem_, &validationError)) {
        if (algorithm == "partition") {
            throw std::runtime_error(
                "partition construction produced an invalid solution: " +
                validationError);
        }
        Logger::instance().warning(
            "algorithm." + algorithm,
            "candidate rejected; falling back to partition: " + validationError);
        candidate = PartitioningAlgorithm(problem_).solve(timeoutSeconds);
        std::string fallbackError;
        if (!candidate.validate(problem_, &fallbackError)) {
            throw std::runtime_error(
                "partition fallback produced an invalid solution: " + fallbackError);
        }
        candidate.meta["algorithm_implementation"] = "partition";
        candidate.meta["candidate_source"] = "partition_fallback";
        candidate.meta["fallback_algorithm"] = "partition";
        candidate.meta["fallback_reason"] = validationError;
    } else {
        candidate.meta["algorithm_implementation"] = algorithm;
        candidate.meta["candidate_source"] = algorithm;
    }
    candidate.meta["requested_algorithm"] = algorithm;
    if (!routeAssignmentScope.empty()) {
        candidate.meta["requested_route_assignment_scope"] = routeAssignmentScope;
        candidate.meta["effective_route_assignment_scope"] =
            candidate.meta["algorithm_implementation"] == "partition"
                ? "multi_cutter_partition"
                : routeAssignmentScope;
    }
    return candidate;
}
}  // namespace cgshop2027
