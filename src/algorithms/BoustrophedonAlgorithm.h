#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// A1: column-wise zigzag coverage (Choset boustrophedon).
class BoustrophedonAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
