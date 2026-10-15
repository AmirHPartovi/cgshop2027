#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// Orders cutter centers by the amount of not-yet-covered region they explain,
// while assigning the order to the least-loaded cutter route.
class AnchorCoverAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
