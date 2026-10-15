#include "core/Polyomino.h"

#include <algorithm>
#include <queue>
#include <ostream>
#include <unordered_set>

namespace cgshop2027 {

Polyomino::Polyomino(std::vector<Point> cells) : cells_(std::move(cells)) {
    std::sort(cells_.begin(), cells_.end());
    cells_.erase(std::unique(cells_.begin(), cells_.end()), cells_.end());
}

void Polyomino::addCell(const Point& cell) {
    if (!contains(cell)) {
        cells_.insert(std::lower_bound(cells_.begin(), cells_.end(), cell), cell);
    }
}

const std::vector<Point>& Polyomino::cells() const noexcept { return cells_; }
const std::vector<Point>& Polyomino::getCells() const noexcept { return cells_; }

bool Polyomino::contains(const Point& cell) const noexcept {
    return std::binary_search(cells_.begin(), cells_.end(), cell);
}

BoundingBox Polyomino::boundingBox() const noexcept {
    if (cells_.empty()) {
        return {};
    }
    BoundingBox result{cells_.front().x, cells_.front().y,
                       cells_.front().x, cells_.front().y};
    for (const Point cell : cells_) {
        result.min_x = std::min(result.min_x, cell.x);
        result.min_y = std::min(result.min_y, cell.y);
        result.max_x = std::max(result.max_x, cell.x);
        result.max_y = std::max(result.max_y, cell.y);
    }
    return result;
}

int Polyomino::getMinX() const noexcept { return boundingBox().min_x; }
int Polyomino::getMaxX() const noexcept { return boundingBox().max_x; }
int Polyomino::getMinY() const noexcept { return boundingBox().min_y; }
int Polyomino::getMaxY() const noexcept { return boundingBox().max_y; }
int Polyomino::area() const noexcept { return static_cast<int>(cells_.size()); }
bool Polyomino::empty() const noexcept { return cells_.empty(); }

Point Polyomino::getCentroid() const noexcept {
    if (cells_.empty()) {
        return {};
    }
    long long sum_x = 0;
    long long sum_y = 0;
    for (const Point cell : cells_) {
        sum_x += cell.x;
        sum_y += cell.y;
    }
    return {static_cast<int>(sum_x / static_cast<long long>(cells_.size())),
            static_cast<int>(sum_y / static_cast<long long>(cells_.size()))};
}

std::vector<Polyomino> Polyomino::connectedComponents() const {
    std::unordered_set<Point, PointHash> remaining(cells_.begin(), cells_.end());
    std::vector<Polyomino> result;
    constexpr Point directions[] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    while (!remaining.empty()) {
        const Point start = *remaining.begin();
        remaining.erase(start);
        std::queue<Point> queue;
        queue.push(start);
        std::vector<Point> component;
        while (!queue.empty()) {
            const Point current = queue.front();
            queue.pop();
            component.push_back(current);
            for (const Point direction : directions) {
                const Point next = current + direction;
                if (remaining.erase(next) != 0U) {
                    queue.push(next);
                }
            }
        }
        result.emplace_back(std::move(component));
    }
    return result;
}

std::vector<Polyomino> Polyomino::getConnectedComponents() const {
    return connectedComponents();
}

bool Polyomino::isConnected() const {
    return cells_.empty() || connectedComponents().size() == 1U;
}

std::ostream& operator<<(std::ostream& output, const Polyomino& polyomino) {
    return output << "Polyomino with " << polyomino.area() << " cells";
}

}  // namespace cgshop2027
