#include "algorithms/MstcAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"

#include <utility>

namespace cgshop2027 {
Solution MstcAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.mstc", "solve");
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    Solution solution = makeSolution(problem_,
                        TourConstruction::mstc(anchors, problem_.numberOfCutters));
    return finishCandidate(std::move(solution), "mstc", timeoutSeconds);
}
}  // namespace cgshop2027
