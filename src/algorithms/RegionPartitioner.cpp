#include "algorithms/RegionPartitioner.h"

#include "core/ExecutionControl.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <queue>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace cgshop2027 {
namespace {
const Point kNeighbors[]{{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

int64_t boundingBoxArea(const std::vector<Point>& cells) {
    if (cells.empty()) return 0;
    int64_t minX = cells.front().x;
    int64_t maxX = cells.front().x;
    int64_t minY = cells.front().y;
    int64_t maxY = cells.front().y;
    for (size_t i = 0; i < cells.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        minX = std::min(minX, static_cast<int64_t>(cells[i].x));
        maxX = std::max(maxX, static_cast<int64_t>(cells[i].x));
        minY = std::min(minY, static_cast<int64_t>(cells[i].y));
        maxY = std::max(maxY, static_cast<int64_t>(cells[i].y));
    }
    const int64_t width = maxX - minX + 1;
    const int64_t height = maxY - minY + 1;
    if (width > std::numeric_limits<int64_t>::max() / height) {
        throw std::overflow_error("region subproblem bounding box is too large");
    }
    return width * height;
}

}  // namespace

RegionPartition RegionPartitioner::partition(const Problem& problem) const {
    RegionPartition result;
    const auto raster = problem.regionCells();
    result.targetCellCount = raster.size();
    result.holeCount = problem.innerBoundaries.size();
    if (raster.empty()) return result;

    std::vector<Point> cells(raster.begin(), raster.end());
    std::sort(cells.begin(), cells.end());
    std::unordered_set<Point, PointHash> remaining(cells.begin(), cells.end());
    std::vector<std::vector<Point>> components;
    for (const Point seed : cells) {
        if ((components.size() & 0xffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (remaining.erase(seed) == 0U) continue;
        components.emplace_back();
        std::queue<Point> queue;
        queue.push(seed);
        while (!queue.empty()) {
            ExecutionControl::instance().checkpoint();
            const Point current = queue.front();
            queue.pop();
            components.back().push_back(current);
            for (const Point delta : kNeighbors) {
                const Point next{current.x + delta.x, current.y + delta.y};
                if (remaining.erase(next) != 0U) queue.push(next);
            }
        }
        std::sort(components.back().begin(), components.back().end());
    }
    result.connectedComponentCount = components.size();

    const size_t cutterArea = problem.cutterCells().size();
    const size_t complexity = problem.innerBoundaries.size() +
        static_cast<size_t>(std::max(problem.numberOfCutters, 1)) +
        std::min<size_t>(cutterArea / 16U, 16U);
    result.maxCellsPerSubproblem =
        std::max<size_t>(64U, std::min<size_t>(512U, 4096U / (1U + complexity)));
    std::unordered_map<Point, size_t, PointHash> ownership;
    ownership.reserve(cells.size());

    auto emit = [&](std::vector<Point> ownedCells) {
        ExecutionControl::instance().checkpoint();
        std::sort(ownedCells.begin(), ownedCells.end());
        RegionSubproblem subproblem;
        subproblem.id = result.subproblems.size();
        subproblem.targetCells = std::move(ownedCells);
        subproblem.boundingBoxArea = boundingBoxArea(subproblem.targetCells);
        const auto cutterCells = problem.cutterCells();
        if (!cutterCells.empty()) {
            const Point reference = *std::min_element(
                cutterCells.begin(), cutterCells.end());
            subproblem.coverageAnchors.reserve(subproblem.targetCells.size());
            for (const Point cell : subproblem.targetCells) {
                const int64_t x = static_cast<int64_t>(cell.x) +
                                  problem.cutterCenter.x - reference.x;
                const int64_t y = static_cast<int64_t>(cell.y) +
                                  problem.cutterCenter.y - reference.y;
                if (x < std::numeric_limits<int>::min() ||
                    x > std::numeric_limits<int>::max() ||
                    y < std::numeric_limits<int>::min() ||
                    y > std::numeric_limits<int>::max()) {
                    throw std::overflow_error(
                        "region coverage anchor exceeds coordinate range");
                }
                subproblem.coverageAnchors.push_back(
                    {static_cast<int>(x), static_cast<int>(y)});
            }
            std::sort(subproblem.coverageAnchors.begin(),
                      subproblem.coverageAnchors.end());
            subproblem.coverageAnchors.erase(
                std::unique(subproblem.coverageAnchors.begin(),
                            subproblem.coverageAnchors.end()),
                subproblem.coverageAnchors.end());
        }
        const auto local = std::unordered_set<Point, PointHash>(
            subproblem.targetCells.begin(), subproblem.targetCells.end());
        for (const Point cell : subproblem.targetCells) {
            if ((subproblem.boundaryCellCount & 0x3ffU) == 0U)
                ExecutionControl::instance().checkpoint();
            size_t degree = 0;
            for (const Point delta : kNeighbors) {
                if (local.count({cell.x + delta.x, cell.y + delta.y}) != 0U) ++degree;
            }
            if (degree < 4U) ++subproblem.boundaryCellCount;
            if (degree <= 2U) ++subproblem.narrowCellCount;
            ownership.emplace(cell, subproblem.id);
        }
        const double occupancy = static_cast<double>(subproblem.targetCells.size()) /
            static_cast<double>(std::max<int64_t>(1, subproblem.boundingBoxArea));
        const double cutterFactor = 1.0 + std::log2(
            static_cast<double>(std::max<size_t>(1U, cutterArea)));
        const double boundaryFactor = 1.0 +
            static_cast<double>(subproblem.narrowCellCount) /
                static_cast<double>(std::max<size_t>(1U, subproblem.targetCells.size()));
        subproblem.estimatedDifficulty =
            static_cast<double>(subproblem.boundingBoxArea) * cutterFactor *
            boundaryFactor / std::max(occupancy, 0.01);
        result.subproblems.push_back(std::move(subproblem));
    };

    std::function<void(std::vector<Point>)> split =
        [&](std::vector<Point> part) {
            ExecutionControl::instance().checkpoint();
            const int64_t area = boundingBoxArea(part);
            const bool difficult = part.size() > result.maxCellsPerSubproblem ||
                area > static_cast<int64_t>(result.maxCellsPerSubproblem) * 4;
            if (!difficult || part.size() <= 1U) {
                emit(std::move(part));
                return;
            }
            int minX = part.front().x, maxX = minX;
            int minY = part.front().y, maxY = minY;
            for (const Point point : part) {
                minX = std::min(minX, point.x);
                maxX = std::max(maxX, point.x);
                minY = std::min(minY, point.y);
                maxY = std::max(maxY, point.y);
            }
            const bool splitX = static_cast<int64_t>(maxX) - minX >=
                                static_cast<int64_t>(maxY) - minY;
            std::sort(part.begin(), part.end(), [splitX](Point left, Point right) {
                if (splitX) return left.x == right.x ? left.y < right.y : left.x < right.x;
                return left.y == right.y ? left.x < right.x : left.y < right.y;
            });
            const size_t middle = part.size() / 2U;
            std::vector<Point> right(part.begin() + static_cast<std::ptrdiff_t>(middle),
                                     part.end());
            part.erase(part.begin() + static_cast<std::ptrdiff_t>(middle), part.end());
            const auto splitConnectedParts = [&](std::vector<Point> half) {
                std::unordered_set<Point, PointHash> unvisited(
                    half.begin(), half.end());
                for (const Point seed : half) {
                    ExecutionControl::instance().checkpoint();
                    if (unvisited.erase(seed) == 0U) continue;
                    std::vector<Point> connected;
                    std::queue<Point> pending;
                    pending.push(seed);
                    while (!pending.empty()) {
                        ExecutionControl::instance().checkpoint();
                        const Point current = pending.front();
                        pending.pop();
                        connected.push_back(current);
                        for (const Point delta : kNeighbors) {
                            const Point neighbor{
                                current.x + delta.x, current.y + delta.y};
                            if (unvisited.erase(neighbor) != 0U)
                                pending.push(neighbor);
                        }
                    }
                    split(std::move(connected));
                }
            };
            splitConnectedParts(std::move(part));
            splitConnectedParts(std::move(right));
        };
    for (auto& component : components) split(std::move(component));

    if (ownership.size() != cells.size()) {
        throw std::runtime_error("region partition did not assign every target cell");
    }
    for (const Point cell : cells) {
        const auto found = ownership.find(cell);
        if (found == ownership.end() ||
            found->second >= result.subproblems.size()) {
            throw std::runtime_error("region partition contains an unowned target cell");
        }
        for (const Point delta : kNeighbors) {
            const Point neighbor{cell.x + delta.x, cell.y + delta.y};
            const auto adjacent = ownership.find(neighbor);
            if (adjacent != ownership.end() &&
                adjacent->second != found->second) {
                ++result.artificialBoundaryEdges;
            }
        }
    }
    result.artificialBoundaryEdges /= 2U;
    return result;
}

}  // namespace cgshop2027
