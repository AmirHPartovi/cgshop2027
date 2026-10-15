#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// A2: spanning-tree coverage (Gabriely–Rimon), on the covering-anchor graph.
class StcAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
