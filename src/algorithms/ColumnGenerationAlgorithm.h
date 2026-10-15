#pragma once

#include "algorithms/BaseAlgorithm.h"

#include <string>

namespace cgshop2027 {

class ConnectedGrowthAlgorithm final : public BaseAlgorithm {
public:
    explicit ConnectedGrowthAlgorithm(const Problem& problem,
                                      std::string requestedAlgorithm = "connected-growth");
    Solution solve(double timeoutSeconds = -1.0) override;

private:
    std::string requestedAlgorithm_;
};

using ColumnGenerationAlgorithm = ConnectedGrowthAlgorithm;

}  // namespace cgshop2027
