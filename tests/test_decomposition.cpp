#include "algorithms/DecomposeSolver.h"
#include "algorithms/LocalSubproblemSolver.h"
#include "algorithms/MergeSolver.h"
#include "algorithms/RegionPartitioner.h"
#include "core/ExecutionControl.h"
#include "io/InstanceReader.h"
#include "io/SolutionWriter.h"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#ifndef CGSHOP_TEST_FIXTURE_DIR
#error "CGSHOP_TEST_FIXTURE_DIR must point to the checked-in test fixtures"
#endif

namespace {

using namespace cgshop2027;

const std::filesystem::path kFixtures(CGSHOP_TEST_FIXTURE_DIR);
const Point kNeighbors[]{{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

bool connected(const std::vector<Point>& cells) {
    if (cells.empty()) return false;
    std::unordered_set<Point, PointHash> remaining(cells.begin(), cells.end());
    std::queue<Point> pending;
    pending.push(cells.front());
    remaining.erase(cells.front());
    while (!pending.empty()) {
        const Point current = pending.front();
        pending.pop();
        for (const Point delta : kNeighbors) {
            const Point neighbor{current.x + delta.x, current.y + delta.y};
            if (remaining.erase(neighbor) != 0U) pending.push(neighbor);
        }
    }
    return remaining.empty();
}

LocalSubproblemResult makeLocal(
    const Problem& problem, size_t id, std::vector<Point> cells) {
    RegionSubproblem subproblem;
    subproblem.id = id;
    subproblem.targetCells = std::move(cells);
    const auto cutter = problem.cutterCells();
    require(!cutter.empty(), "fixture cutter must contain cells");
    const Point reference = *std::min_element(cutter.begin(), cutter.end());
    for (const Point cell : subproblem.targetCells) {
        subproblem.coverageAnchors.push_back({
            cell.x + problem.cutterCenter.x - reference.x,
            cell.y + problem.cutterCenter.y - reference.y,
        });
    }
    return LocalSubproblemSolver().solve(problem, subproblem);
}

void checkFixture(const std::string& filename) {
    auto problem = InstanceReader::readInstance((kFixtures / "instances" / filename).string());
    const RegionPartition partition = RegionPartitioner().partition(*problem);
    const auto targetCells = problem->regionCells();
    require(partition.targetCellCount == targetCells.size(),
            filename + ": partition target count mismatch");
    require(partition.holeCount == problem->innerBoundaries.size(),
            filename + ": hole feature mismatch");
    std::unordered_set<Point, PointHash> owned;
    std::vector<LocalSubproblemResult> localResults;
    for (const auto& subproblem : partition.subproblems) {
        require(!subproblem.targetCells.empty(),
                filename + ": empty subproblem");
        require(connected(subproblem.targetCells),
                filename + ": subproblem is not four-neighbor connected");
        require(subproblem.coverageAnchors.size() == subproblem.targetCells.size(),
                filename + ": coverage-anchor mapping is incomplete");
        require(subproblem.estimatedDifficulty > 0.0,
                filename + ": missing difficulty estimate");
        for (const Point cell : subproblem.targetCells) {
            require(targetCells.count(cell) == 1U,
                    filename + ": subproblem owns a non-target cell");
            require(owned.insert(cell).second,
                    filename + ": target cell has duplicate ownership");
        }
        const auto local = LocalSubproblemSolver().solve(*problem, subproblem);
        require(!local.exact, filename + ": heuristic local result marked exact");
        require(!local.options.empty(), filename + ": local solver returned no options");
        localResults.push_back(local);
    }
    require(owned.size() == targetCells.size(),
            filename + ": target cells are missing from partition ownership");
    const MergeResult merged = MergeSolver().merge(*problem, localResults);
    require(merged.status == "FEASIBLE_HEURISTIC_MERGE",
            filename + ": merge failed: " + merged.status);
    std::string error;
    require(merged.solution.validate(*problem, &error),
            filename + ": merged solution invalid: " + error);
    require(merged.makespan == solutionMakespan(merged.solution),
            filename + ": merge makespan omitted closure or disagrees");
    require(merged.cutterAllocations.size() == partition.subproblems.size(),
            filename + ": cutter allocation count mismatch");
    for (const size_t cutter : merged.cutterAllocations) {
        require(cutter < static_cast<size_t>(problem->numberOfCutters),
                filename + ": allocation exceeds global cutter budget");
    }

    const Solution solution = DecomposeSolver(*problem).solve(10.0);
    require(solution.validate(*problem, &error),
            filename + ": public decomposition candidate invalid: " + error);
    require(solution.meta.at("algorithm_implementation") == "decompose_heuristic" ||
                solution.meta.at("algorithm_implementation") == "partition",
            filename + ": candidate provenance is not explicit");
    require(solution.meta.at("decomposition_exact") == "false",
            filename + ": decomposition claimed exactness");
}

void checkCutterAllocationCounts() {
    auto oneCutter = InstanceReader::readInstance(
        (kFixtures / "instances/tiny-square.instance.json").string());
    const auto squareCells = oneCutter->regionCells();
    std::vector<Point> oneCell(squareCells.begin(), squareCells.end());
    std::sort(oneCell.begin(), oneCell.end());
    std::vector<LocalSubproblemResult> manyRegions;
    for (size_t i = 0; i < oneCell.size(); ++i) {
        manyRegions.push_back(makeLocal(*oneCutter, i, {oneCell[i]}));
    }
    require(manyRegions.size() >
                static_cast<size_t>(oneCutter->numberOfCutters),
            "test must exercise more subproblems than cutters");
    require(MergeSolver().merge(*oneCutter, manyRegions).status ==
                "FEASIBLE_HEURISTIC_MERGE",
            "merge failed when subproblems outnumber cutters");
    const auto allSquareCells = std::vector<Point>(
        squareCells.begin(), squareCells.end());
    const std::vector<LocalSubproblemResult> equalRegions{
        makeLocal(*oneCutter, 0, allSquareCells)};
    require(equalRegions.size() ==
                static_cast<size_t>(oneCutter->numberOfCutters),
            "test must exercise equal subproblem and cutter counts");
    require(MergeSolver().merge(*oneCutter, equalRegions).status ==
                "FEASIBLE_HEURISTIC_MERGE",
            "merge failed when subproblems equal cutters");

    auto twoCutters = InstanceReader::readInstance(
        (kFixtures / "instances/tiny-hole-multicutter.instance.json").string());
    const auto holeCells = twoCutters->regionCells();
    std::vector<Point> holeTargets(holeCells.begin(), holeCells.end());
    std::sort(holeTargets.begin(), holeTargets.end());
    std::vector<LocalSubproblemResult> fewerRegions{
        makeLocal(*twoCutters, 0, holeTargets)};
    require(fewerRegions.size() <
                static_cast<size_t>(twoCutters->numberOfCutters),
            "test must exercise fewer subproblems than cutters");
    require(MergeSolver().merge(*twoCutters, fewerRegions).status ==
                "FEASIBLE_HEURISTIC_MERGE",
            "merge failed when subproblems are fewer than cutters");
}

void checkNoIncumbentHandling() {
    auto problem = InstanceReader::readInstance(
        (kFixtures / "instances/tiny-single.instance.json").string());
    const MergeResult result = MergeSolver().merge(
        *problem, {LocalSubproblemResult{}});
    require(result.status == "LOCAL_NO_INCUMBENT",
            "merge did not report a local no-incumbent status");
}

void checkAdaptiveSplitAndTimeout() {
    Problem large;
    large.contentType = "CGSHOP2027_Instance";
    large.instanceUid = "synthetic-large-rectangle";
    large.outerBoundary = {{0, 0}, {50, 0}, {50, 50}, {0, 50}};
    large.cutter = {{0, 0}, {1, 0}, {1, 1}, {0, 1}};
    large.cutterCenter = {0, 0};
    large.numberOfCutters = 2;
    const RegionPartition partition = RegionPartitioner().partition(large);
    require(partition.subproblems.size() > 1U,
            "large region was not adaptively split");
    require(partition.artificialBoundaryEdges > 0U,
            "adaptive split did not record artificial boundaries");
    std::unordered_set<Point, PointHash> ownership;
    for (const auto& subproblem : partition.subproblems) {
        require(connected(subproblem.targetCells),
                "adaptive split emitted a disconnected region");
        for (const Point cell : subproblem.targetCells) {
            require(ownership.insert(cell).second,
                    "adaptive split assigned a target cell more than once");
        }
    }
    require(ownership.size() == large.regionCells().size(),
            "adaptive split omitted target cells");

    ExecutionControl::instance().setDeadline(
        ExecutionControl::Clock::now() - std::chrono::milliseconds(1));
    bool cancelled = false;
    try {
        (void)RegionPartitioner().partition(large);
    } catch (const ExecutionCancelled&) {
        cancelled = true;
    }
    ExecutionControl::instance().clearDeadline();
    require(cancelled, "partitioner ignored an expired local deadline");
}

void writeMergedCandidate(const std::filesystem::path& output) {
    auto problem = InstanceReader::readInstance(
        (kFixtures / "instances/tiny-hole-multicutter.instance.json").string());
    const RegionPartition partition = RegionPartitioner().partition(*problem);
    std::vector<LocalSubproblemResult> localResults;
    for (const auto& subproblem : partition.subproblems) {
        localResults.push_back(LocalSubproblemSolver().solve(*problem, subproblem));
    }
    const MergeResult merged = MergeSolver().merge(*problem, localResults);
    require(merged.status == "FEASIBLE_HEURISTIC_MERGE",
            "cannot export merged test candidate");
    SolutionWriter::write(merged.solution, *problem, output.string());
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 1 && (argc != 3 || std::string(argv[1]) != "--write-merged")) {
            throw std::runtime_error("usage: test_decomposition [--write-merged PATH]");
        }
        ExecutionControl::instance().clearDeadline();
        checkFixture("tiny-single.instance.json");
        checkFixture("tiny-square.instance.json");
        checkFixture("tiny-hole-multicutter.instance.json");
        checkFixture("phase8-staircase.instance.json");
        checkCutterAllocationCounts();
        checkNoIncumbentHandling();
        checkAdaptiveSplitAndTimeout();
        if (argc == 3) writeMergedCandidate(argv[2]);
        std::cout << "decomposition: passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "decomposition: failed: " << error.what() << '\n';
        return 1;
    }
}
