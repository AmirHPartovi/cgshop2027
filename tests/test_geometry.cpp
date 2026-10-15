#include "core/GeometryUtils.h"
#include "core/Polyomino.h"

#include <cassert>
#include <unordered_set>

using cgshop2027::Point;
using cgshop2027::Polyomino;

int main() {
    const Point a{1, 2};
    const Point b{4, 2};
    assert(a.manhattanDistance(b) == 3);
    assert(cgshop2027::manhattanDistance(a, b) == 3);
    assert(cgshop2027::isAxisAligned(a, b));
    assert(cgshop2027::latticeSegment(a, b).size() == 4U);
    assert(cgshop2027::latticeSegment(a, {4, 3}).empty());

    std::unordered_set<Point> points{{0, 0}, {1, 1}};
    assert(points.count({1, 1}) == 1U);

    Polyomino shape({{2, 0}, {0, 0}, {1, 0}, {2, 0}});
    assert(shape.area() == 3);
    assert(shape.contains({1, 0}));
    assert(!shape.contains({2, 1}));
    const auto box = shape.boundingBox();
    assert(box.min_x == 0 && box.min_y == 0 && box.max_x == 2 &&
           box.max_y == 0);
    assert(shape.isConnected());

    Polyomino disconnected({{0, 0}, {5, 5}});
    assert(!disconnected.isConnected());
    assert(disconnected.connectedComponents().size() == 2U);
    return 0;
}
