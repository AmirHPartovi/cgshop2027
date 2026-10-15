#include "core/Point.h"

#include <cstdint>
#include <cstdlib>

namespace cgshop2027 {

bool Point::operator==(const Point& other) const noexcept {
    return x == other.x && y == other.y;
}

bool Point::operator!=(const Point& other) const noexcept {
    return !(*this == other);
}

bool Point::operator<(const Point& other) const noexcept {
    return x < other.x || (x == other.x && y < other.y);
}

Point Point::operator+(const Point& other) const noexcept {
    return {x + other.x, y + other.y};
}

Point Point::operator-(const Point& other) const noexcept {
    return {x - other.x, y - other.y};
}

Point Point::operator*(int scalar) const noexcept {
    return {x * scalar, y * scalar};
}

int Point::manhattanDistance(const Point& other) const noexcept {
    return std::abs(x - other.x) + std::abs(y - other.y);
}

std::size_t PointHash::operator()(const Point& point) const noexcept {
    const auto x = static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(point.x));
    const auto y = static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(point.y));
    return static_cast<std::size_t>((x << 32U) ^ y);
}

}  // namespace cgshop2027
