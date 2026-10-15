#pragma once

#include "core/Problem.h"
#include "core/Solution.h"

#include <chrono>
#include <vector>

namespace cgshop2027 {

class TourConstruction {
public:
    static std::vector<Point> coveringAnchors(const Problem& problem);
    static std::vector<Point> compactPath(std::vector<Point> points);
    static std::vector<Point> boustrophedon(const std::vector<Point>& anchors);
    static std::vector<Point> spanningTreeWalk(const std::vector<Point>& anchors);
    static std::vector<Point> tspCov(const std::vector<Point>& anchors,
                                     const std::chrono::steady_clock::time_point& start,
                                     double limit);
    static std::vector<std::vector<Point>> splitFrederickson(
        const std::vector<Point>& tour, int k);
    static std::vector<std::vector<Point>> mstc(const std::vector<Point>& anchors,
                                                int k);
    static std::vector<std::vector<Point>> recursiveBisectionTours(
        const std::vector<Point>& anchors, int k);
    static std::vector<std::vector<Point>> stripIlpTours(
        const std::vector<Point>& anchors, int k);
    static std::vector<std::vector<Point>> columnGenerationTours(
        const std::vector<Point>& anchors, int k,
        const std::chrono::steady_clock::time_point& start, double limit);
    static Solution improveLns(const Problem& problem, Solution solution,
                               const std::chrono::steady_clock::time_point& start,
                               double limit);
    static Solution makeSolution(const Problem& problem,
                                 const std::vector<std::vector<Point>>& groups);
    static int closedLength(const std::vector<Point>& points);
    static bool timedOut(const std::chrono::steady_clock::time_point& start,
                         double limit);
    static int areaLowerBound(const Problem& problem);
    static std::vector<Point> rectilinearConnect(Point from, Point to);
};

}  // namespace cgshop2027
