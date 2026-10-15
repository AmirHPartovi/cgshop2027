#include "algorithms/FredericksonSplitAlgorithm.h"
#include "utils/Logger.h"
#include "algorithms/TourConstruction.h"
#include "core/RuntimeConfig.h"

#include <chrono>
#include <utility>

namespace cgshop2027 {
Solution FredericksonSplitAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.frederickson", "solve");
    const auto start = std::chrono::steady_clock::now();
    const auto anchors = TourConstruction::coveringAnchors(problem_);
    auto giant = TourConstruction::boustrophedon(anchors);
    const auto stc = TourConstruction::spanningTreeWalk(anchors);
    if (TourConstruction::closedLength(stc) < TourConstruction::closedLength(giant))
        giant = stc;
    if (!TourConstruction::timedOut(start, timeoutSeconds)) {
        const auto tsp = TourConstruction::tspCov(
            anchors, start, timeoutSeconds,
            runtimeConfig().algorithmParameters.tspMaxAnchors,
            runtimeConfig().algorithmParameters.twoOptPasses);
        if (TourConstruction::closedLength(tsp) < TourConstruction::closedLength(giant))
            giant = tsp;
    }
    Solution solution = makeSolution(problem_, TourConstruction::splitFrederickson(
                                      giant, problem_.numberOfCutters));
    return finishCandidate(
        std::move(solution), "frederickson", timeoutSeconds,
        "multi_cutter_split_of_single_tour");
}
}  // namespace cgshop2027
