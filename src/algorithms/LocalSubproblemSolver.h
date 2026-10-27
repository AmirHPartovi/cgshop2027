#pragma once

#include "algorithms/DecompositionTypes.h"
#include "core/Problem.h"

namespace cgshop2027 {

class LocalSubproblemSolver {
public:
    LocalSubproblemResult solve(const Problem& problem,
                                const RegionSubproblem& subproblem) const;
};

}  // namespace cgshop2027
