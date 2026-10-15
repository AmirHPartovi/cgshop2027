#include "core/GeometryUtils.h"

#include <cstdlib>

namespace cgshop2027 {

int manhattanDistance(Point a, Point b) noexcept {
    return std::abs(a.x - b.x) + std::abs(a.y - b.y);
}

bool isAxisAligned(Point a, Point b) noexcept {
    return a.x == b.x || a.y == b.y;
}

std::vector<Point> latticeSegment(Point a, Point b) {
    std::vector<Point> points;
    if (!isAxisAligned(a, b)) {
        return points;
    }
    const int dx = (b.x > a.x) - (b.x < a.x);
    const int dy = (b.y > a.y) - (b.y < a.y);
    const int length = manhattanDistance(a, b);
    points.reserve(static_cast<std::size_t>(length + 1));
    for (int step = 0; step <= length; ++step) {
        points.push_back({a.x + step * dx, a.y + step * dy});
    }
    return points;
}

}  // namespace cgshop2027
