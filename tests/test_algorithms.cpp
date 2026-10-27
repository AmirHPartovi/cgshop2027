#include "algorithms/AnchorCoverAlgorithm.h"
#include "algorithms/BalancedGreedyRouteAlgorithm.h"
#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/HybridSolver.h"
#include "algorithms/IlpAlgorithm.h"
#include "algorithms/LocalSearch.h"
#include "algorithms/LnsMultiCutterAlgorithm.h"
#include "algorithms/MstcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/RegionPartitionAssignAlgorithm.h"
#include "algorithms/StcAlgorithm.h"
#include "algorithms/StripAlgorithm.h"
#include "algorithms/TspCovAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/SolverResult.h"
#include "io/InstanceReader.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <string>

#ifndef CGSHOP_TEST_FIXTURE_DIR
#error "CGSHOP_TEST_FIXTURE_DIR must point to the checked-in test fixtures"
#endif

namespace {

const std::filesystem::path kFixtures(CGSHOP_TEST_FIXTURE_DIR);

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Factory>
void checkAlgorithm(const std::string& name,
                    const cgshop2027::Problem& problem,
                    Factory&& factory,
                    size_t& passed) {
    cgshop2027::Solution solution = factory();
    std::string error;
    require(solution.validate(problem, &error),
            name + " returned an invalid solution: " + error);
    require(solution.meta.count("requested_algorithm") == 1U &&
                solution.meta.at("requested_algorithm") == name,
            name + " must retain its requested algorithm identity");
    require(solution.meta.count("algorithm_implementation") == 1U &&
                solution.meta.count("candidate_source") == 1U,
            name + " must identify the implementation and candidate source");
    if (name == "local" || name == "lns" || name == "hybrid") {
        require(solution.meta.count("lns_candidates_evaluated") == 1U &&
                    solution.meta.count("lns_moves_accepted") == 1U &&
                    solution.meta.count("lns_improved") == 1U &&
                    solution.meta.count("lns_runtime_seconds") == 1U &&
                    solution.meta.count("lns_termination_reason") == 1U,
                name + " must report its anchor-search metrics");
    }
    if (name == "connected-growth") {
        require(solution.meta.count("connected_growth_search_status") == 1U &&
                    solution.meta.count("connected_growth_budget_checks") == 1U &&
                    (solution.meta.at("connected_growth_search_status") == "COMPLETED" ||
                     solution.meta.at("connected_growth_search_status") == "NOT_RUN" ||
                     solution.meta.at("connected_growth_search_status") ==
                         "TIMEOUT_UNKNOWN"),
                "connected-growth must report whether its heuristic budget search "
                "completed or was interrupted");
    }
    ++passed;
    std::cout << name << ": passed\n";
}

class FallbackProbe final : public cgshop2027::BaseAlgorithm {
public:
    using BaseAlgorithm::BaseAlgorithm;
    cgshop2027::Solution solve(double timeoutSeconds = -1.0) override {
        return finishCandidate({}, "fallback-probe", timeoutSeconds);
    }
};

bool anchorCoveredByGroups(
    cgshop2027::Point anchor,
    const std::vector<std::vector<cgshop2027::Point>>& groups) {
    for (const auto& group : groups) {
        if (group.empty()) continue;
        if (group.size() == 1U && group.front() == anchor) return true;
        for (size_t i = 0; i < group.size(); ++i) {
            const auto first = group[i];
            const auto second = group[(i + 1U) % group.size()];
            if (first.x == second.x && first.x == anchor.x &&
                anchor.y >= std::min(first.y, second.y) &&
                anchor.y <= std::max(first.y, second.y)) return true;
            if (first.y == second.y && first.y == anchor.y &&
                anchor.x >= std::min(first.x, second.x) &&
                anchor.x <= std::max(first.x, second.x)) return true;
        }
    }
    return false;
}

bool baselineInside(double x, double y,
                    const std::vector<cgshop2027::Point>& ring) {
    bool inside = false;
    for (size_t i = 0, j = ring.size() - 1U; i < ring.size(); j = i++) {
        const auto& a = ring[i];
        const auto& b = ring[j];
        if (((a.y > y) != (b.y > y)) &&
            x < ((static_cast<double>(b.x) - a.x) * (y - a.y) /
                     static_cast<double>(b.y - a.y) +
                 a.x))
            inside = !inside;
    }
    return inside;
}

std::unordered_set<cgshop2027::Point, cgshop2027::PointHash> baselineRaster(
    const std::vector<cgshop2027::Point>& outer,
    const std::vector<std::vector<cgshop2027::Point>>& holes) {
    std::unordered_set<cgshop2027::Point, cgshop2027::PointHash> cells;
    if (outer.empty()) return cells;
    int minX = outer.front().x;
    int maxX = minX;
    int minY = outer.front().y;
    int maxY = minY;
    for (const auto point : outer) {
        minX = std::min(minX, point.x);
        maxX = std::max(maxX, point.x);
        minY = std::min(minY, point.y);
        maxY = std::max(maxY, point.y);
    }
    for (int64_t y = minY; y < maxY; ++y) {
        for (int64_t x = minX; x < maxX; ++x) {
            const double centerX = static_cast<double>(x) + 0.5;
            const double centerY = static_cast<double>(y) + 0.5;
            if (!baselineInside(centerX, centerY, outer)) continue;
            bool inHole = false;
            for (const auto& hole : holes) {
                if (baselineInside(centerX, centerY, hole)) {
                    inHole = true;
                    break;
                }
            }
            if (!inHole) {
                cells.insert({static_cast<int>(x), static_cast<int>(y)});
            }
        }
    }
    return cells;
}

void checkRasterDifferential(const cgshop2027::Problem& problem) {
    require(problem.regionCells() ==
                baselineRaster(problem.outerBoundary, problem.innerBoundaries),
            "scanline region raster must match the point-in-polygon baseline");
    require(problem.cutterCells() == baselineRaster(problem.cutter, {}),
            "scanline cutter raster must match the point-in-polygon baseline");
}

}  // namespace

int main() {
    try {
        const auto single = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/tiny-square.instance.json").string());
        const auto multi = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/tiny-hole-multicutter.instance.json").string());
        const auto relocation = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/phase8-relocation.instance.json").string());
        const auto staircase = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/phase8-staircase.instance.json").string());
        size_t passed = 0;

        checkRasterDifferential(*single);
        checkRasterDifferential(*multi);
        checkRasterDifferential(*relocation);
        checkRasterDifferential(*staircase);

        const auto expiredGrowth = cgshop2027::TourConstruction::connectedGrowthTours(
            cgshop2027::TourConstruction::coveringAnchors(*multi),
            multi->numberOfCutters,
            std::chrono::steady_clock::now() - std::chrono::seconds(1), 0.0);
        const auto expiredGrowthSolution = cgshop2027::TourConstruction::makeSolution(
            *multi, expiredGrowth.tours);
        require(expiredGrowth.timedOut &&
                    expiredGrowth.tours.size() ==
                        static_cast<size_t>(multi->numberOfCutters) &&
                    expiredGrowthSolution.validate(*multi),
                "interrupted connected-growth search must report unknown and retain "
                "a complete valid baseline candidate");

        cgshop2027::Problem twoCutters = *single;
        twoCutters.numberOfCutters = 2;
        const auto allAnchors =
            cgshop2027::TourConstruction::coveringAnchors(*single);
        const auto padded = cgshop2027::TourConstruction::makeSolution(
            twoCutters, {allAnchors, {}});
        const std::vector<cgshop2027::Point> connectedAnchors{
            {0, 0}, {1, 0}, {2, 0}, {3, 0},
        };
        const auto mstcGroups =
            cgshop2027::TourConstruction::mstc(connectedAnchors, 2);
        size_t assignedAnchors = 0;
        for (const auto& group : mstcGroups) assignedAnchors += group.size();
        const bool paddingHasValidTours =
            padded.tours.size() == 2U && !padded.tours[0].points.empty() &&
            !padded.tours[1].points.empty();
        const bool paddingIsValid = padded.validate(twoCutters);
        const bool mstcHasTwoGroups =
            mstcGroups.size() == 2U && !mstcGroups[0].empty() &&
            !mstcGroups[1].empty();
        const bool mstcAssignsAllAnchors = std::all_of(
            connectedAnchors.begin(), connectedAnchors.end(),
            [&](cgshop2027::Point anchor) {
                return anchorCoveredByGroups(anchor, mstcGroups);
            });
        require(paddingHasValidTours && paddingIsValid && mstcHasTwoGroups &&
                    mstcAssignsAllAnchors,
                "reproduction: padding_tours=" +
                    std::string(paddingHasValidTours ? "ok" : "empty") +
                    ", padding_valid=" + (paddingIsValid ? "true" : "false") +
                    ", mstc_group_sizes=" +
                    (mstcGroups.empty() ? "none" :
                     std::to_string(mstcGroups.front().size())) + "," +
                    (mstcGroups.size() < 2 ? "none" :
                     std::to_string(mstcGroups[1].size())));
        require(assignedAnchors > 0U,
                "MSTC must produce at least one route point");
        const auto spanningWalk =
            cgshop2027::TourConstruction::spanningTreeWalk({{0, 0}, {1, 0}});
        require(std::find(spanningWalk.begin(), spanningWalk.end(),
                          cgshop2027::Point{1, 0}) != spanningWalk.end(),
                "collinear tree-walk reversal must retain the far endpoint");
        const auto reversalPath = cgshop2027::TourConstruction::compactPath(
            {{0, 0}, {1, 0}, {0, 0}});
        require(reversalPath.size() == 3U &&
                    reversalPath[1] == cgshop2027::Point{1, 0},
                "path compaction must preserve a collinear reversal");
        const auto closedInput = cgshop2027::TourConstruction::makeSolution(
            *single, {{{0, 0}, {1, 0}, {0, 0}}});
        require(closedInput.tours.size() == 1U &&
                    closedInput.tours[0].points.size() == 2U &&
                    closedInput.tours[0].points.front() !=
                        closedInput.tours[0].points.back(),
                "shared solution construction must normalize an explicit closing point");

        const auto singleRoute =
            cgshop2027::BoustrophedonAlgorithm(twoCutters).solve(1.0);
        require(singleRoute.tours.size() == 2U &&
                     singleRoute.meta.at("requested_route_assignment_scope") ==
                         "single_route_with_stationary_padding" &&
                     singleRoute.meta.at("effective_route_assignment_scope") ==
                         "single_route_with_stationary_padding",
                "single-route algorithms must disclose stationary cutter padding");

        FallbackProbe fallbackProbe(twoCutters);
        bool invalidCandidateRejected = false;
        try {
            (void)fallbackProbe.solve(1.0);
        } catch (const std::runtime_error& error) {
            invalidCandidateRejected =
                std::string(error.what()).find("produced an invalid candidate") !=
                std::string::npos;
        }
        require(invalidCandidateRejected,
                "invalid algorithm candidate must fail rather than silently become a partition result");

        cgshop2027::SolverResult unavailable;
        unavailable.completion = cgshop2027::SolverCompletionStatus::Unavailable;
        unavailable.terminationReason = "exact route model is not implemented";
        const std::string unavailableJson = unavailable.toJson();
        require(unavailableJson.find("\"candidate_exists\": false") !=
                    std::string::npos &&
                    unavailableJson.find("\"solver_completion_status\": \"unavailable\"") !=
                    std::string::npos &&
                    unavailableJson.find("\"optimality_proved\": false") !=
                    std::string::npos,
                "unavailable exact mode must not be serialized as an incumbent or proof");

        cgshop2027::SolverResult invalidTimeoutResult;
        invalidTimeoutResult.completion =
            cgshop2027::SolverCompletionStatus::TimedOutWithIncumbent;
        bool inconsistentStatusRejected = false;
        try {
            invalidTimeoutResult.validate();
        } catch (const std::runtime_error&) {
            inconsistentStatusRejected = true;
        }
        require(inconsistentStatusRejected,
                "timed-out-with-incumbent status must require a validated incumbent");
        cgshop2027::SolverResult timedOutIncumbent;
        timedOutIncumbent.candidate =
            cgshop2027::PartitioningAlgorithm(twoCutters).solve(1.0);
        timedOutIncumbent.internalValidation =
            cgshop2027::CandidateValidationStatus::Passed;
        timedOutIncumbent.completion =
            cgshop2027::SolverCompletionStatus::TimedOutWithIncumbent;
        timedOutIncumbent.algorithmImplementation = "partition";
        timedOutIncumbent.candidateSource = "partition_fallback";
        timedOutIncumbent.terminationReason = "deadline with retained incumbent";
        timedOutIncumbent.validate();
        require(timedOutIncumbent.toJson().find(
                    "\"solver_completion_status\": \"timed_out_with_incumbent\"") !=
                    std::string::npos &&
                    timedOutIncumbent.toJson().find(
                        "\"candidate_source\": \"partition_fallback\"") !=
                        std::string::npos,
                "timeout incumbent status must preserve its actual candidate provenance");

        bool excessGroupsRejected = false;
        try {
            (void)cgshop2027::TourConstruction::makeSolution(
                twoCutters, {{{0, 0}}, {{0, 0}}, {{0, 0}}});
        } catch (const std::invalid_argument&) {
            excessGroupsRejected = true;
        }
        require(excessGroupsRejected,
                "common solution construction must reject excess route groups");

        int64_t paddedMakespan = 0;
        for (const auto& tour : padded.tours) {
            paddedMakespan = std::max(
                paddedMakespan, cgshop2027::closedTourLength(tour.points));
        }
        require(paddedMakespan == cgshop2027::solutionMakespan(padded),
                "candidate comparison must use canonical closed-tour makespan");

        const auto lnsStart = std::chrono::steady_clock::now();
        const auto lnsResult = cgshop2027::TourConstruction::improveLns(
            twoCutters, padded, lnsStart, 2.0, 250, 2027, 5000, 16);
        require(lnsResult.validate(twoCutters),
                "anchor relocation LNS must preserve a valid incumbent");
        require(std::stoll(lnsResult.meta.at("lns_candidates_evaluated")) > 0 &&
                    lnsResult.meta.count("lns_moves_accepted") == 1U &&
                    lnsResult.meta.count("lns_runtime_seconds") == 1U &&
                    lnsResult.meta.count("lns_termination_reason") == 1U,
                "LNS must report candidate, move, runtime, and termination metrics");
        require(lnsResult.meta.at("lns_improved") == "true" &&
                    cgshop2027::solutionMakespan(lnsResult) <
                        cgshop2027::solutionMakespan(padded),
                "repro fixture must demonstrate a meaningful makespan improvement");
        const auto repeatedLns = cgshop2027::TourConstruction::improveLns(
            twoCutters, padded, std::chrono::steady_clock::now(), 2.0, 250,
            2027, 5000, 16);
        require(repeatedLns.tours.size() == lnsResult.tours.size() &&
                    cgshop2027::solutionMakespan(repeatedLns) ==
                        cgshop2027::solutionMakespan(lnsResult) &&
                    repeatedLns.meta.at("lns_moves_accepted") ==
                        lnsResult.meta.at("lns_moves_accepted"),
                "fixed-seed anchor relocation must be reproducible");
        const auto noSearch = cgshop2027::TourConstruction::improveLns(
            twoCutters, lnsResult, std::chrono::steady_clock::now(), 2.0, 0,
            2027, 5000, 16);
        require(cgshop2027::solutionMakespan(noSearch) ==
                    cgshop2027::solutionMakespan(lnsResult) &&
                    noSearch.meta.at("lns_improved") == "false" &&
                    noSearch.meta.at("lns_termination_reason") == "iteration_limit",
                "zero-iteration search must retain the initial incumbent");
        const auto anchorLimited = cgshop2027::TourConstruction::improveLns(
            twoCutters, padded, std::chrono::steady_clock::now(), 2.0, 10,
            2027, 1, 1);
        require(cgshop2027::solutionMakespan(anchorLimited) ==
                    cgshop2027::solutionMakespan(padded) &&
                    anchorLimited.meta.at("lns_termination_reason") == "anchor_limit",
                "anchor cap must stop search while preserving the incumbent");

        cgshop2027::Problem rectangle = *single;
        rectangle.instanceUid = "phase8-objective-rectangle";
        rectangle.outerBoundary = {{0, 0}, {8, 0}, {8, 6}, {0, 6}};
        rectangle.numberOfCutters = 2;
        require(rectangle.validate(), "objective fixture must be a valid instance");
        std::vector<cgshop2027::Point> horizontalSnake;
        for (int y = 0; y < 6; ++y) {
            if ((y & 1) == 0) {
                for (int x = 0; x < 8; ++x) horizontalSnake.push_back({x, y});
            } else {
                for (int x = 7; x >= 0; --x) horizontalSnake.push_back({x, y});
            }
        }
        const auto longSingleRoute = cgshop2027::TourConstruction::makeSolution(
            rectangle, {horizontalSnake, {}});
        require(longSingleRoute.validate(rectangle),
                "single-route objective incumbent must cover the rectangle");
        const auto balancedRectangle = cgshop2027::TourConstruction::improveLns(
            rectangle, longSingleRoute, std::chrono::steady_clock::now(), 2.0,
            250, 2027, 5000, 16);
        require(balancedRectangle.validate(rectangle) &&
                    cgshop2027::solutionMakespan(balancedRectangle) <
                        cgshop2027::solutionMakespan(longSingleRoute),
                "reconstruction must lower the longest route on a balanceable instance");
        require(std::stoll(balancedRectangle.meta.at(
                    "lns_final_total_route_length")) >=
                    std::stoll(balancedRectangle.meta.at(
                    "lns_initial_total_route_length")),
                    "makespan improvement must not depend on reducing total route length: " +
                        balancedRectangle.meta.at("lns_initial_total_route_length") +
                        " -> " +
                        balancedRectangle.meta.at("lns_final_total_route_length"));
        const auto incompleteRelocation =
            cgshop2027::TourConstruction::makeSolution(
                    rectangle, {{{0, 0}}, {}});
        require(!incompleteRelocation.validate(rectangle) &&
                        balancedRectangle.validate(rectangle),
                    "an infeasible incomplete assignment must be rejected without "
                    "replacing the valid incumbent");
        const auto timedOutLns = cgshop2027::TourConstruction::improveLns(
            rectangle, longSingleRoute, std::chrono::steady_clock::now(), 0.01,
            100000, 2027, 5000, 16);
        require(timedOutLns.validate(rectangle) &&
                    timedOutLns.meta.at("lns_termination_reason") == "deadline" &&
                    std::stoi(timedOutLns.meta.at("lns_iterations_completed")) > 0,
                "a mid-search deadline must return the valid incumbent");
        const auto relocationInitial = cgshop2027::TourConstruction::makeSolution(
            *relocation,
            {cgshop2027::TourConstruction::coveringAnchors(*relocation), {}});
        const auto relocationSearch = cgshop2027::TourConstruction::improveLns(
            *relocation, relocationInitial, std::chrono::steady_clock::now(),
            2.0, 100, 1, 5000, 16);
        require(relocationSearch.validate(*relocation) &&
                    std::stoi(relocationSearch.meta.at("lns_moves_accepted")) > 0 &&
                    std::stoi(relocationSearch.meta.at("lns_candidates_evaluated")) > 1 &&
                    relocationSearch.meta.at("lns_improved") == "true",
                "fixed-seed LNS fixture must accept a feasible relocation and improve "
                "the validated incumbent");
        const auto relocationRepeat = cgshop2027::TourConstruction::improveLns(
            *relocation, relocationInitial, std::chrono::steady_clock::now(),
            2.0, 100, 1, 5000, 16);
        bool sameRoutes = relocationRepeat.tours.size() == relocationSearch.tours.size();
        for (size_t i = 0; sameRoutes && i < relocationSearch.tours.size(); ++i) {
            sameRoutes = relocationRepeat.tours[i].points ==
                         relocationSearch.tours[i].points;
        }
        require(sameRoutes &&
                    relocationRepeat.meta.at("lns_moves_accepted") ==
                        relocationSearch.meta.at("lns_moves_accepted"),
                "fixed seed must reproduce the accepted anchor moves and tours");

        checkAlgorithm("strip", *single,
                       [&] { return cgshop2027::StripAlgorithm(*single).solve(1.0); },
                       passed);
        checkAlgorithm("partition", *multi,
                       [&] {
                           return cgshop2027::PartitioningAlgorithm(*multi).solve(1.0);
                       },
                       passed);
        const auto initial = cgshop2027::PartitioningAlgorithm(*multi).solve();
        checkAlgorithm("local", *multi,
                       [&] { return cgshop2027::LocalSearch(*multi, initial).solve(1.0); },
                       passed);
        checkAlgorithm("anchor-cover", *multi,
                       [&] {
                           return cgshop2027::AnchorCoverAlgorithm(*multi).solve(1.0);
                       },
                       passed);
        checkAlgorithm("balanced-greedy", *multi,
                       [&] {
                           return cgshop2027::BalancedGreedyRouteAlgorithm(*multi)
                               .solve(1.0);
                       },
                       passed);
        checkAlgorithm("boustrophedon", *single,
                       [&] {
                           return cgshop2027::BoustrophedonAlgorithm(*single).solve(1.0);
                       },
                       passed);
        checkAlgorithm("stc", *single,
                       [&] { return cgshop2027::StcAlgorithm(*single).solve(1.0); },
                       passed);
        checkAlgorithm("tsp-cov", *single,
                       [&] { return cgshop2027::TspCovAlgorithm(*single).solve(1.0); },
                       passed);
        checkAlgorithm("frederickson", *multi,
                       [&] {
                           return cgshop2027::FredericksonSplitAlgorithm(*multi)
                               .solve(1.0);
                       },
                       passed);
        checkAlgorithm("mstc", *multi,
                       [&] { return cgshop2027::MstcAlgorithm(*multi).solve(1.0); },
                       passed);
        checkAlgorithm("region-partition", *multi,
                       [&] {
                           return cgshop2027::RegionPartitionAssignAlgorithm(*multi)
                               .solve(1.0);
                       },
                       passed);
        const auto ilpResult = cgshop2027::IlpAlgorithm(*multi).solve(1.0);
        std::string ilpError;
        require(ilpResult.validate(*multi, &ilpError),
                "ilp returned an invalid solution: " + ilpError);
        require(ilpResult.meta.count("ip_kont_status") == 1U &&
                    ilpResult.meta.count("ip_kont_raw_status") == 1U &&
                    ilpResult.meta.count("ip_kont_solver_log") == 1U &&
                    ilpResult.meta.count("ip_kont_variable_count") == 1U &&
                    ilpResult.meta.count("ip_kont_constraint_count") == 1U &&
                    ilpResult.meta.count("ip_kont_exact_for_original_objective") == 1U,
                "ilp result must record KONT status, log, and exactness scope");
        require(ilpResult.meta.at("ip_kont_exact_for_original_objective") == "false",
                "IP-KONT surrogate must not claim exactness for the route objective");
        const auto& ipStatus = ilpResult.meta.at("ip_kont_status");
        require(ipStatus == "OPTIMAL_CERTIFIED" ||
                    ipStatus == "FEASIBLE_NOT_PROVEN" ||
                    ipStatus == "TIME_LIMIT_WITH_INCUMBENT" ||
                    ipStatus == "TIME_LIMIT_NO_INCUMBENT" ||
                    ipStatus == "INFEASIBLE_PROVEN" ||
                    ipStatus == "INVALID_OUTPUT" || ipStatus == "ERROR",
                "ilp result has an unsupported comparison status: " + ipStatus);
        ++passed;
        std::cout << "ilp: passed\n";
        checkAlgorithm("connected-growth", *multi,
                       [&] {
                           return cgshop2027::ConnectedGrowthAlgorithm(*multi)
                               .solve(1.0);
                       },
                       passed);
        const auto legacyGrowth =
            cgshop2027::ConnectedGrowthAlgorithm(*multi, "column-gen").solve(1.0);
        require(legacyGrowth.validate(*multi) &&
                    legacyGrowth.meta.at("requested_algorithm") == "column-gen" &&
                    (legacyGrowth.meta.at("algorithm_implementation") ==
                         "connected-growth" ||
                     legacyGrowth.meta.at("algorithm_implementation") == "partition"),
                "legacy column-gen alias must retain its requested name and truthful "
                "implementation metadata");
        checkAlgorithm("lns", *multi,
                       [&] {
                           return cgshop2027::LnsMultiCutterAlgorithm(*multi)
                               .solve(1.0);
                       },
                       passed);
        const auto hybridResult = cgshop2027::HybridSolver(*multi).solve(1.0);
        checkAlgorithm("hybrid", *multi,
                       [&] { return hybridResult; }, passed);
        require(hybridResult.meta.count("portfolio_selected_algorithm") == 1U &&
                    hybridResult.meta.count("candidate_source") == 1U &&
                    hybridResult.meta.count("candidate_generation_order") == 1U,
                "hybrid must preserve selected-builder and candidate provenance");
        if (hybridResult.meta.at("candidate_source") == "hybrid_lns_improvement") {
            require(hybridResult.meta.at("algorithm_implementation") == "hybrid",
                    "an LNS improvement must name hybrid as the actual producer");
        } else {
            require(hybridResult.meta.at("candidate_source") ==
                        hybridResult.meta.at("algorithm_implementation"),
                    "a constructive candidate must retain its actual producer");
        }

        require(passed == 15U,
                "expected all 15 registered algorithm implementations to run");
        std::cout << "Summary: " << passed << " algorithms passed\n";
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << "test_algorithms failed: " << exception.what() << '\n';
        return 1;
    }
}
