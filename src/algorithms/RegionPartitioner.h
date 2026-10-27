#pragma once

#include "algorithms/DecompositionTypes.h"
#include "core/Problem.h"

namespace cgshop2027 {

class RegionPartitioner {
public:
    RegionPartition partition(const Problem& problem) const;
};

}  // namespace cgshop2027
