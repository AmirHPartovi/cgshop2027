#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// Builds routes simultaneously, choosing a nearby unvisited anchor while
// penalizing cutters whose estimated route is already longer than the others.
class BalancedGreedyRouteAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
