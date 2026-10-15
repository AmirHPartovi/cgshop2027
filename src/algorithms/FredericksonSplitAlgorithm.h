#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// B1: min-max split of a giant covering tour (Frederickson–Hecht–Kim).
class FredericksonSplitAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
