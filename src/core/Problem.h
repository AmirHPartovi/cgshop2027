#pragma once
#include "Point.h"
#include <string>
#include <vector>
#include <unordered_set>

namespace cgshop2027 {
struct Problem {
  std::string contentType, instanceUid;
  std::vector<Point> outerBoundary;
  std::vector<std::vector<Point>> innerBoundaries;
  std::vector<Point> cutter;
  Point cutterCenter{};
  int numberOfCutters{0};

  int regionArea() const;
  bool validate(std::string* error = nullptr) const;
  std::unordered_set<Point, PointHash> regionCells() const;
  std::unordered_set<Point, PointHash> cutterCells() const;
  bool isCovered(const std::vector<Point>& centers) const;
  bool isCovered(const std::vector<std::vector<Point>>& tours) const;
  bool isValidCutterPosition(const Point&) const { return true; }
};
}
