#pragma once

#include <cstddef>
#include <functional>

namespace cgshop2027 {

struct Point {
    int x{0};
    int y{0};

    constexpr Point() = default;
    constexpr Point(int x_value, int y_value) : x(x_value), y(y_value) {}

    bool operator==(const Point& other) const noexcept;
    bool operator!=(const Point& other) const noexcept;
    bool operator<(const Point& other) const noexcept;
    Point operator+(const Point& other) const noexcept;
    Point operator-(const Point& other) const noexcept;
    Point operator*(int scalar) const noexcept;
    int manhattanDistance(const Point& other) const noexcept;
};

struct PointHash {
    std::size_t operator()(const Point& point) const noexcept;
};

}  // namespace cgshop2027

template <>
struct std::hash<cgshop2027::Point> {
    std::size_t operator()(const cgshop2027::Point& point) const noexcept {
        return cgshop2027::PointHash{}(point);
    }
};
