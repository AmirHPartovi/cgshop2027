#pragma once

#include "core/Point.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace cgshop2027 {

struct RegionSubproblem {
    size_t id{0};
    std::vector<Point> targetCells;
    std::vector<Point> coverageAnchors;
    int64_t boundingBoxArea{0};
    size_t boundaryCellCount{0};
    size_t narrowCellCount{0};
    double estimatedDifficulty{0.0};
};

struct RegionPartition {
    std::vector<RegionSubproblem> subproblems;
    size_t targetCellCount{0};
    size_t artificialBoundaryEdges{0};
    size_t connectedComponentCount{0};
    size_t holeCount{0};
    size_t maxCellsPerSubproblem{0};
};

struct LocalRouteOption {
    std::vector<Point> route;
    int64_t closedLength{0};
    std::string source;
};

struct LocalSubproblemResult {
    size_t subproblemId{0};
    std::vector<LocalRouteOption> options;
    std::string status{"unavailable"};
    bool exact{false};
};

}  // namespace cgshop2027
