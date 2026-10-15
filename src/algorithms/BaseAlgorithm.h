#pragma once

#include "core/Problem.h"
#include "core/Solution.h"

#include <chrono>
#include <vector>

namespace cgshop2027 {

class BaseAlgorithm {
public:
    explicit BaseAlgorithm(const Problem& problem) : problem_(problem) {}
    virtual ~BaseAlgorithm() = default;
    virtual Solution solve(double timeoutSeconds = -1.0) = 0;

protected:
    const Problem& problem_;

    static Tour makeClosedTour(const std::vector<Point>& points);
    static std::vector<Point> coverageCenters(const Problem& problem);
    static bool validTour(const Tour& tour);
    static double tourLength(const Tour& tour);
    static double makespan(const Solution& solution);
    static bool timedOut(const std::chrono::steady_clock::time_point& start,
                         double limit);
    static Solution makeSolution(const Problem& problem,
                                 const std::vector<std::vector<Point>>& groups);
};

}  // namespace cgshop2027
