#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// Legacy "ilp" entry point for the IP-KONT vertical-column assignment surrogate.
class IlpAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
