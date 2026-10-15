#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// D1: large-neighborhood search over k cutter tours (TSP_Turn-style moves).
class LnsMultiCutterAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
