#include "Problem.h"
#include "core/ExecutionControl.h"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <unordered_set>

namespace cgshop2027 {
namespace {

struct Edge {
    Point start;
    Point end;
    size_t index{0};
    int ring{0};
};

bool horizontal(const Edge& edge) {
    return edge.start.y == edge.end.y;
}

std::vector<Edge> edgesOf(const std::vector<Point>& points, int ring = 0) {
    std::vector<Edge> edges;
    edges.reserve(points.size());
    for (size_t i = 0; i < points.size(); ++i) {
        edges.push_back({points[i], points[(i + 1U) % points.size()], i, ring});
    }
    return edges;
}

bool adjacent(const Edge& first, const Edge& second, size_t edgeCount) {
    return (first.index + 1U) % edgeCount == second.index ||
           (second.index + 1U) % edgeCount == first.index;
}

bool sharedEndpointIntersection(const Edge& first, const Edge& second,
                                const Point& intersection, size_t edgeCount) {
    if (!adjacent(first, second, edgeCount)) return false;
    const Point shared = (first.index + 1U) % edgeCount == second.index
                             ? first.end
                             : second.end;
    return shared == intersection;
}

bool hasPerpendicularIntersection(const std::vector<Edge>& edges,
                                  size_t edgeCount, bool crossRingsOnly) {
    struct Event {
        int x;
        int kind;
        size_t edge;
    };
    std::vector<Event> events;
    events.reserve(edges.size() * 2U);
    for (size_t i = 0; i < edges.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        const Edge& edge = edges[i];
        if (horizontal(edge)) {
            const int low = std::min(edge.start.x, edge.end.x);
            const int high = std::max(edge.start.x, edge.end.x);
            events.push_back({low, 0, i});
            events.push_back({high, 2, i});
        } else {
            events.push_back({edge.start.x, 1, i});
        }
    }
    std::sort(events.begin(), events.end(), [](const Event& a, const Event& b) {
        if (a.x != b.x) return a.x < b.x;
        if (a.kind != b.kind) return a.kind < b.kind;
        return a.edge < b.edge;
    });

    std::map<int, std::set<size_t>> active;
    size_t visitedEvents = 0;
    for (const Event& event : events) {
        if ((visitedEvents++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        const Edge& edge = edges[event.edge];
        if (event.kind == 0) {
            active[edge.start.y].insert(event.edge);
        } else if (event.kind == 2) {
            auto line = active.find(edge.start.y);
            if (line != active.end()) {
                line->second.erase(event.edge);
                if (line->second.empty()) active.erase(line);
            }
        } else {
            const int low = std::min(edge.start.y, edge.end.y);
            const int high = std::max(edge.start.y, edge.end.y);
            for (auto line = active.lower_bound(low);
                 line != active.end() && line->first <= high; ++line) {
                for (const size_t horizontalIndex : line->second) {
                    const Edge& horizontalEdge = edges[horizontalIndex];
                    if (crossRingsOnly) {
                        if (edge.ring != horizontalEdge.ring) return true;
                        continue;
                    }
                    const Point crossing{edge.start.x, horizontalEdge.start.y};
                    if (!sharedEndpointIntersection(edge, horizontalEdge, crossing,
                                                    edgeCount)) {
                        return true;
                    }
                }
            }
        }
    }
    return false;
}

bool hasSelfParallelOverlap(const std::vector<Edge>& edges, bool horizontalEdges,
                            size_t edgeCount) {
    std::vector<Edge> sorted;
    size_t visited = 0;
    for (const Edge& edge : edges) {
        if ((visited++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (horizontal(edge) == horizontalEdges) sorted.push_back(edge);
    }
    std::sort(sorted.begin(), sorted.end(), [horizontalEdges](const Edge& a,
                                                              const Edge& b) {
        const int aLine = horizontalEdges ? a.start.y : a.start.x;
        const int bLine = horizontalEdges ? b.start.y : b.start.x;
        if (aLine != bLine) return aLine < bLine;
        const int aLow = horizontalEdges ? std::min(a.start.x, a.end.x)
                                          : std::min(a.start.y, a.end.y);
        const int bLow = horizontalEdges ? std::min(b.start.x, b.end.x)
                                          : std::min(b.start.y, b.end.y);
        if (aLow != bLow) return aLow < bLow;
        const int aHigh = horizontalEdges ? std::max(a.start.x, a.end.x)
                                           : std::max(a.start.y, a.end.y);
        const int bHigh = horizontalEdges ? std::max(b.start.x, b.end.x)
                                           : std::max(b.start.y, b.end.y);
        return aHigh < bHigh;
    });
    for (size_t i = 1; i < sorted.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        const Edge& previous = sorted[i - 1U];
        const Edge& current = sorted[i];
        const int line = horizontalEdges ? current.start.y : current.start.x;
        if ((horizontalEdges ? previous.start.y : previous.start.x) != line) continue;
        const int previousHigh = horizontalEdges
                                     ? std::max(previous.start.x, previous.end.x)
                                     : std::max(previous.start.y, previous.end.y);
        const int currentLow = horizontalEdges
                                   ? std::min(current.start.x, current.end.x)
                                   : std::min(current.start.y, current.end.y);
        if (currentLow > previousHigh) continue;
        if (currentLow != previousHigh ||
            !adjacent(previous, current, edgeCount)) return true;
    }
    return false;
}

bool hasCrossParallelOverlap(const std::vector<Edge>& edges,
                             bool horizontalEdges) {
    std::vector<Edge> sorted;
    size_t visited = 0;
    for (const Edge& edge : edges) {
        if ((visited++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (horizontal(edge) == horizontalEdges) sorted.push_back(edge);
    }
    std::sort(sorted.begin(), sorted.end(), [horizontalEdges](const Edge& a,
                                                              const Edge& b) {
        const int aLine = horizontalEdges ? a.start.y : a.start.x;
        const int bLine = horizontalEdges ? b.start.y : b.start.x;
        if (aLine != bLine) return aLine < bLine;
        const int aLow = horizontalEdges ? std::min(a.start.x, a.end.x)
                                          : std::min(a.start.y, a.end.y);
        const int bLow = horizontalEdges ? std::min(b.start.x, b.end.x)
                                          : std::min(b.start.y, b.end.y);
        return aLow < bLow;
    });
    int currentLine = 0;
    int maxHigh[2] = {std::numeric_limits<int>::min(),
                      std::numeric_limits<int>::min()};
    int currentRing = 0;
    bool firstLine = true;
    visited = 0;
    for (const Edge& edge : sorted) {
        if ((visited++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        const int line = horizontalEdges ? edge.start.y : edge.start.x;
        if (firstLine || line != currentLine) {
            currentLine = line;
            maxHigh[0] = maxHigh[1] = std::numeric_limits<int>::min();
            firstLine = false;
        }
        const int low = horizontalEdges ? std::min(edge.start.x, edge.end.x)
                                        : std::min(edge.start.y, edge.end.y);
        const int high = horizontalEdges ? std::max(edge.start.x, edge.end.x)
                                         : std::max(edge.start.y, edge.end.y);
        currentRing = edge.ring;
        if (maxHigh[1 - currentRing] >= low) return true;
        maxHigh[currentRing] = std::max(maxHigh[currentRing], high);
    }
    return false;
}

bool validRing(const std::vector<Point>& points) {
    if (points.size() < 4U) return false;
    std::unordered_set<Point, PointHash> unique;
    for (size_t i = 0; i < points.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        if (!unique.insert(points[i]).second) return false;
        const Point& next = points[(i + 1U) % points.size()];
        if (points[i] == next ||
            (points[i].x != next.x && points[i].y != next.y)) return false;
    }
    const auto edges = edgesOf(points);
    return !hasSelfParallelOverlap(edges, true, points.size()) &&
           !hasSelfParallelOverlap(edges, false, points.size()) &&
           !hasPerpendicularIntersection(edges, points.size(), false);
}

long double signedDoubleArea(const std::vector<Point>& points) {
    long double area = 0.0L;
    for (size_t i = 0; i < points.size(); ++i) {
        if ((i & 0x3ffU) == 0U) ExecutionControl::instance().checkpoint();
        const Point& a = points[i];
        const Point& b = points[(i + 1U) % points.size()];
        area += static_cast<long double>(a.x) * b.y -
                static_cast<long double>(b.x) * a.y;
    }
    return area;
}

bool inside(double x, double y, const std::vector<Point>& points) {
    bool in = false;
    for (size_t i = 0, j = points.size() - 1U; i < points.size(); j = i++) {
        const Point& a = points[i];
        const Point& b = points[j];
        if (((a.y > y) != (b.y > y)) &&
            x < ((static_cast<double>(b.x) - a.x) * (y - a.y) /
                     static_cast<double>(b.y - a.y) +
                 a.x)) {
            in = !in;
        }
    }
    return in;
}

bool onBoundary(double x, double y, const std::vector<Point>& points) {
    for (size_t i = 0; i < points.size(); ++i) {
        const Point& a = points[i];
        const Point& b = points[(i + 1U) % points.size()];
        if (a.x == b.x && x == a.x && y >= std::min(a.y, b.y) &&
            y <= std::max(a.y, b.y)) return true;
        if (a.y == b.y && y == a.y && x >= std::min(a.x, b.x) &&
            x <= std::max(a.x, b.x)) return true;
    }
    return false;
}

bool ringsIntersect(const std::vector<Point>& first,
                    const std::vector<Point>& second) {
    auto edges = edgesOf(first, 0);
    auto other = edgesOf(second, 1);
    edges.insert(edges.end(), other.begin(), other.end());
    return hasCrossParallelOverlap(edges, true) ||
           hasCrossParallelOverlap(edges, false) ||
           hasPerpendicularIntersection(edges, 0U, true);
}

std::unordered_set<Point, PointHash> raster(
    const std::vector<Point>& outer,
    const std::vector<std::vector<Point>>& holes) {
    std::unordered_set<Point, PointHash> cells;
    if (outer.empty()) return cells;
    int minX = outer[0].x;
    int maxX = minX;
    int minY = outer[0].y;
    int maxY = minY;
    for (const Point point : outer) {
        minX = std::min(minX, point.x);
        maxX = std::max(maxX, point.x);
        minY = std::min(minY, point.y);
        maxY = std::max(maxY, point.y);
    }
    uint64_t scanned = 0;
    for (int64_t y = minY; y < static_cast<int64_t>(maxY); ++y) {
        for (int64_t x = minX; x < static_cast<int64_t>(maxX); ++x) {
            if ((scanned++ & 0x3ffU) == 0U)
                ExecutionControl::instance().checkpoint();
            const double centerX = static_cast<double>(x) + 0.5;
            const double centerY = static_cast<double>(y) + 0.5;
            if (!inside(centerX, centerY, outer)) continue;
            bool inHole = false;
            for (const auto& hole : holes) {
                if (inside(centerX, centerY, hole)) {
                    inHole = true;
                    break;
                }
            }
            if (!inHole) {
                cells.insert({static_cast<int>(x), static_cast<int>(y)});
            }
        }
    }
    return cells;
}

}  // namespace

int Problem::regionArea() const {
    return static_cast<int>(regionCells().size());
}

std::unordered_set<Point, PointHash> Problem::regionCells() const {
    return raster(outerBoundary, innerBoundaries);
}

std::unordered_set<Point, PointHash> Problem::cutterCells() const {
    return raster(cutter, {});
}

bool Problem::validate(std::string* error) const {
    const auto fail = [&](const char* message) {
        if (error != nullptr) *error = message;
        return false;
    };
    if (contentType != "CGSHOP2027_Instance") {
        return fail("unsupported instance content_type");
    }
    if (!validRing(outerBoundary)) {
        return fail("outer_boundary must be a simple orthogonal ring without repeated vertices");
    }
    if (signedDoubleArea(outerBoundary) <= 0) {
        return fail("outer_boundary must be counter-clockwise");
    }
    for (size_t i = 0; i < innerBoundaries.size(); ++i) {
        ExecutionControl::instance().checkpoint();
        const auto& hole = innerBoundaries[i];
        if (!validRing(hole)) {
            return fail("inner boundary must be a simple orthogonal ring without repeated vertices");
        }
        if (signedDoubleArea(hole) >= 0) {
            return fail("inner boundary must be clockwise");
        }
        if (ringsIntersect(outerBoundary, hole) ||
            !inside(hole.front().x, hole.front().y, outerBoundary)) {
            return fail("inner boundary must lie strictly inside outer_boundary");
        }
        for (size_t j = 0; j < i; ++j) {
            ExecutionControl::instance().checkpoint();
            if (ringsIntersect(hole, innerBoundaries[j]) ||
                inside(hole.front().x, hole.front().y, innerBoundaries[j]) ||
                inside(innerBoundaries[j].front().x, innerBoundaries[j].front().y,
                       hole)) {
                return fail("inner boundaries must be disjoint and non-nested");
            }
        }
    }
    if (!validRing(cutter)) {
        return fail("cutter must be a simple orthogonal ring without repeated vertices");
    }
    if (signedDoubleArea(cutter) <= 0) {
        return fail("cutter must be counter-clockwise");
    }
    if (!inside(cutterCenter.x, cutterCenter.y, cutter) &&
        !onBoundary(cutterCenter.x, cutterCenter.y, cutter)) {
        return fail("cutter_center must be within cutter");
    }
    if (numberOfCutters <= 0) return fail("number_of_cutters must be positive");
    if (cutterCells().empty() || regionCells().empty()) {
        return fail("polygons must have positive rasterized area");
    }
    return true;
}

bool Problem::isCovered(const std::vector<Point>& centers) const {
    ExecutionControl::instance().checkpoint();
    if (centers.size() != static_cast<size_t>(numberOfCutters)) return false;
    const auto target = regionCells();
    const auto shape = cutterCells();
    std::unordered_set<Point, PointHash> covered;
    size_t work = 0;
    for (const Point center : centers) {
        for (const Point cell : shape) {
            if ((work++ & 0x3ffU) == 0U)
                ExecutionControl::instance().checkpoint();
            const int64_t x = static_cast<int64_t>(center.x) + cell.x - cutterCenter.x;
            const int64_t y = static_cast<int64_t>(center.y) + cell.y - cutterCenter.y;
            if (x >= std::numeric_limits<int>::min() &&
                x <= std::numeric_limits<int>::max() &&
                y >= std::numeric_limits<int>::min() &&
                y <= std::numeric_limits<int>::max()) {
                covered.insert({static_cast<int>(x), static_cast<int>(y)});
            }
        }
    }
    size_t checked = 0;
    for (const Point cell : target) {
        if ((checked++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (covered.count(cell) == 0U) return false;
    }
    return true;
}

bool Problem::isCovered(const std::vector<std::vector<Point>>& tours) const {
    ExecutionControl::instance().checkpoint();
    if (tours.size() != static_cast<size_t>(numberOfCutters)) return false;
    const auto target = regionCells();
    const auto shape = cutterCells();
    std::unordered_set<Point, PointHash> covered;
    size_t work = 0;
    for (const auto& tour : tours) {
        if (tour.empty()) return false;
        const size_t edgeCount = tour.size() == 1U ? 1U : tour.size();
        for (size_t i = 0; i < edgeCount; ++i) {
            const Point start = tour[i];
            const Point end = tour.size() == 1U ? start : tour[(i + 1U) % tour.size()];
            const int64_t dx = static_cast<int64_t>(end.x) - start.x;
            const int64_t dy = static_cast<int64_t>(end.y) - start.y;
            const int64_t length = std::abs(dx) + std::abs(dy);
            for (int64_t step = 0; step <= length; ++step) {
                if ((work++ & 0xffU) == 0U)
                    ExecutionControl::instance().checkpoint();
                const Point center{
                    static_cast<int>(static_cast<int64_t>(start.x) +
                                     (dx == 0 ? 0 : (dx > 0 ? step : -step))),
                    static_cast<int>(static_cast<int64_t>(start.y) +
                                     (dy == 0 ? 0 : (dy > 0 ? step : -step)))};
                for (const Point cell : shape) {
                    if ((work++ & 0x3ffU) == 0U)
                        ExecutionControl::instance().checkpoint();
                    const int64_t x = static_cast<int64_t>(center.x) + cell.x -
                                      cutterCenter.x;
                    const int64_t y = static_cast<int64_t>(center.y) + cell.y -
                                      cutterCenter.y;
                    if (x >= std::numeric_limits<int>::min() &&
                        x <= std::numeric_limits<int>::max() &&
                        y >= std::numeric_limits<int>::min() &&
                        y <= std::numeric_limits<int>::max()) {
                        covered.insert({static_cast<int>(x), static_cast<int>(y)});
                    }
                }
            }
        }
    }
    size_t checked = 0;
    for (const Point cell : target) {
        if ((checked++ & 0x3ffU) == 0U)
            ExecutionControl::instance().checkpoint();
        if (covered.count(cell) == 0U) return false;
    }
    return true;
}

}  // namespace cgshop2027
