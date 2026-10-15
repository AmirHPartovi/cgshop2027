#pragma once

#include "core/Problem.h"
#include "core/Solution.h"

#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

namespace cgshop2027 {

class BaseAlgorithm {
public:
    explicit BaseAlgorithm(const Problem& problem) : problem_(problem) {}
    virtual ~BaseAlgorithm() = default;
    virtual Solution solve(double timeoutSeconds = -1.0) = 0;

    static Solution makeSolution(const Problem& problem,
                                const std::vector<std::vector<Point>>& groups);

protected:
    const Problem& problem_;

    static Tour makeClosedTour(const std::vector<Point>& points,
                               Point stationaryCenter);
    static std::vector<Point> coverageCenters(const Problem& problem);
    static bool validTour(const Tour& tour);
    static int64_t tourLength(const Tour& tour);
    static int64_t makespan(const Solution& solution);
    static bool timedOut(const std::chrono::steady_clock::time_point& start,
                         double limit);
    Solution finishCandidate(Solution candidate, const std::string& algorithm,
                             double timeoutSeconds,
                             const std::string& routeAssignmentScope = {}) const;
};

}  // namespace cgshop2027
