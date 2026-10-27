#pragma once

#include "algorithms/DecompositionTypes.h"
#include "core/Problem.h"
#include "core/Solution.h"

#include <string>
#include <vector>

namespace cgshop2027 {

struct MergeResult {
    Solution solution;
    int64_t makespan{0};
    std::string status{"FAILED"};
    std::vector<size_t> cutterAllocations;
};

class MergeSolver {
public:
    MergeResult merge(const Problem& problem,
                      const std::vector<LocalSubproblemResult>& localResults) const;
};

}  // namespace cgshop2027
