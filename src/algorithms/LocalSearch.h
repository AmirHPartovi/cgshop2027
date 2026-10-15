#pragma once
#include "algorithms/BaseAlgorithm.h"

namespace cgshop2027 {
class LocalSearch final : public BaseAlgorithm {
public:
    LocalSearch(const Problem& problem, Solution initial = {});
    Solution solve(double timeoutSeconds = -1.0) override;
private:
    Solution initial_;
};
}  // namespace cgshop2027
