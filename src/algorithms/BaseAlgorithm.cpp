#include "algorithms/BaseAlgorithm.h"
#include "utils/Logger.h"

#include <algorithm>
#include <cmath>
#include <unordered_set>

namespace cgshop2027 {

Tour BaseAlgorithm::makeClosedTour(const std::vector<Point>& input) {
    Tour result;
    if (input.empty()) return result;
    if (input.size() == 1U) {
        result.points = input;
        return result;
    }
    result.points.push_back(input.front());
    for (size_t i = 1; i < input.size(); ++i) {
        const Point a = result.points.back();
        const Point b = input[i];
        if (a.x != b.x && a.y != b.y) result.points.push_back({b.x, a.y});
        result.points.push_back(b);
    }
    const Point first = input.front();
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
    for (const Point cell : cells)
        result.push_back({cell.x + problem.cutterCenter.x - anchor.x,
                          cell.y + problem.cutterCenter.y - anchor.y});
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
        const Point& a = tour.points[i];
        const Point& b = tour.points[(i + 1) % tour.points.size()];
        if (a == b || (a.x != b.x && a.y != b.y)) return false;
    }
    return true;
}

double BaseAlgorithm::tourLength(const Tour& tour) {
    double length = 0;
    if (tour.points.size() > 1U) {
        for (size_t i = 0; i < tour.points.size(); ++i)
            length += tour.points[i].manhattanDistance(
                tour.points[(i + 1) % tour.points.size()]);
    }
    return length;
}

double BaseAlgorithm::makespan(const Solution& solution) {
    double result = 0;
    for (const Tour& tour : solution.tours) result = std::max(result, tourLength(tour));
    return result;
}

bool BaseAlgorithm::timedOut(const std::chrono::steady_clock::time_point& start,
                             double limit) {
    return limit >= 0 && std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start).count() >= limit;
}

Solution BaseAlgorithm::makeSolution(const Problem& problem,
                                      const std::vector<std::vector<Point>>& groups) {
    Solution solution;
    solution.contentType = "CGSHOP2027_Solution";
    solution.instanceUid = problem.instanceUid;
    solution.tours.reserve(static_cast<size_t>(problem.numberOfCutters));
    for (const auto& group : groups) solution.tours.push_back(makeClosedTour(group));
    while (solution.tours.size() < static_cast<size_t>(problem.numberOfCutters))
        solution.tours.push_back(makeClosedTour({{0, 0}}));
    if (solution.tours.size() > static_cast<size_t>(problem.numberOfCutters))
        solution.tours.resize(static_cast<size_t>(problem.numberOfCutters));
    return solution;
}
}  // namespace cgshop2027
