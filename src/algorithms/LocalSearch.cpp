#include "algorithms/LocalSearch.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <utility>

namespace cgshop2027 {
LocalSearch::LocalSearch(const Problem& problem, Solution initial)
    : BaseAlgorithm(problem), initial_(std::move(initial)) {}

Solution LocalSearch::solve(double timeoutSeconds) {
    LogScope scope("algorithm.local-search", "solve");
    const auto start = std::chrono::steady_clock::now();
    Solution best = initial_;
    std::string error;
    bool toursAreClosed = best.tours.size() ==
                          static_cast<size_t>(problem_.numberOfCutters);
    if (toursAreClosed) {
        for (const auto& tour : best.tours)
            toursAreClosed = toursAreClosed && validTour(tour);
    }
    if (!toursAreClosed || !best.validate(problem_, &error)) {
        return best = PartitioningAlgorithm(problem_).solve(timeoutSeconds);
    }
    // Reversing a tour preserves coverage and validity; keep only strict gains.
    for (auto& tour : best.tours) {
        if (timedOut(start, timeoutSeconds)) break;
        Tour candidate = tour;
        std::reverse(candidate.points.begin(), candidate.points.end());
        if (validTour(candidate) && tourLength(candidate) < tourLength(tour)) tour = candidate;
    }
    return best;
}
}  // namespace cgshop2027
