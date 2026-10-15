#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// E: run constructive solvers, keep the best feasible, then LNS.
class HybridSolver final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
