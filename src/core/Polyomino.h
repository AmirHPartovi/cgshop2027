#pragma once

#include "core/Point.h"

#include <iosfwd>
#include <vector>

namespace cgshop2027 {

struct BoundingBox {
    int min_x{0};
    int min_y{0};
    int max_x{0};
    int max_y{0};
};

class Polyomino {
public:
    Polyomino() = default;
    explicit Polyomino(std::vector<Point> cells);

    void addCell(const Point& cell);
    const std::vector<Point>& cells() const noexcept;
    const std::vector<Point>& getCells() const noexcept;
    bool contains(const Point& cell) const noexcept;
    BoundingBox boundingBox() const noexcept;
    int getMinX() const noexcept;
    int getMaxX() const noexcept;
    int getMinY() const noexcept;
    int getMaxY() const noexcept;
    int area() const noexcept;
    bool empty() const noexcept;
    Point getCentroid() const noexcept;
    bool isConnected() const;
    std::vector<Polyomino> connectedComponents() const;
    std::vector<Polyomino> getConnectedComponents() const;

private:
    std::vector<Point> cells_;
};

std::ostream& operator<<(std::ostream& output, const Polyomino& polyomino);

}  // namespace cgshop2027
