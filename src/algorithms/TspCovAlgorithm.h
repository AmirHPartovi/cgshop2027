#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// A3: TSP on covering anchors plus rectilinear puzzle pieces (Fekete–Keldenich).
class TspCovAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
