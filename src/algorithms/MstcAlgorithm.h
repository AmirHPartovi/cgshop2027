#pragma once

#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {

// B2: multi-robot spanning-tree coverage (Agmon–Hazon–Kaminka).
class MstcAlgorithm final : public BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    Solution solve(double timeoutSeconds = -1.0) override;
};

}  // namespace cgshop2027
