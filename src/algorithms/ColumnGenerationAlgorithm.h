#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// C2: binary search on makespan with greedy column (tour) generation.
class ColumnGenerationAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
