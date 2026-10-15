#pragma once

#include "core/Point.h"

#include <vector>

namespace cgshop2027 {

int manhattanDistance(Point a, Point b) noexcept;
bool isAxisAligned(Point a, Point b) noexcept;
std::vector<Point> latticeSegment(Point a, Point b);

}  // namespace cgshop2027
