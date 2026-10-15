#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// C1: exact min-max assignment of vertical strips (array-partition DP).
class IlpAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
