#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// B3: balanced recursive bisection of anchors, then a single-cutter tour per part.
class RegionPartitionAssignAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
