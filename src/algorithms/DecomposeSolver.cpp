#include "algorithms/DecomposeSolver.h"

#include "algorithms/LocalSubproblemSolver.h"
#include "algorithms/MergeSolver.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/RegionPartitioner.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <string>
#include <vector>

namespace cgshop2027 {
namespace {
std::string partitionFeaturesJson(const RegionPartition& partition) {
    std::ostringstream output;
    output << '[';
    for (size_t index = 0; index < partition.subproblems.size(); ++index) {
        if (index != 0U) output << ',';
        const auto& region = partition.subproblems[index];
        output << "{\"id\":" << region.id
               << ",\"target_cell_count\":" << region.targetCells.size()
               << ",\"bounding_box_area\":" << region.boundingBoxArea
               << ",\"boundary_cell_count\":" << region.boundaryCellCount
               << ",\"narrow_cell_count\":" << region.narrowCellCount
               << ",\"estimated_difficulty\":"
               << region.estimatedDifficulty << '}';
    }
    output << ']';
    return output.str();
}

std::string allocationsJson(const std::vector<size_t>& allocations) {
    std::ostringstream output;
    output << '[';
    for (size_t index = 0; index < allocations.size(); ++index) {
        if (index != 0U) output << ',';
        output << allocations[index];
    }
    output << ']';
    return output.str();
}

void setFallbackMetadata(Solution& solution, size_t subproblems,
                         size_t assignedCells, size_t artificialBoundaries,
                         const std::string& reason, bool timedOut,
                         const RegionPartition& partition) {
    solution.meta["requested_algorithm"] = "decompose";
    solution.meta["algorithm_implementation"] = "partition";
    solution.meta["candidate_source"] = "partition_fallback";
    solution.meta["decomposition_status"] = timedOut
        ? "TIME_LIMIT_WITH_PARTITION_INCUMBENT" : "PARTITION_FALLBACK";
    solution.meta["decomposition_exact"] = "false";
    solution.meta["decomposition_local_solver"] = "heuristic_anchor_options";
    solution.meta["decomposition_fallback_reason"] = reason;
    solution.meta["decomposition_subproblem_count"] = std::to_string(subproblems);
    solution.meta["decomposition_owned_cell_count"] = std::to_string(assignedCells);
    solution.meta["decomposition_artificial_boundary_edges"] =
        std::to_string(artificialBoundaries);
    solution.meta["decomposition_hole_count"] =
        std::to_string(partition.holeCount);
    solution.rawMetaJson["decomposition_partition_features"] =
        partitionFeaturesJson(partition);
    if (timedOut) {
        solution.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
    }
}

}  // namespace

Solution DecomposeSolver::solve(double timeoutSeconds) {
    LogScope scope("solver.decompose", "solve");
    const auto started = std::chrono::steady_clock::now();
    auto remaining = [&] {
        if (timeoutSeconds < 0.0) return -1.0;
        const double elapsed = std::chrono::duration<double>(
                                   std::chrono::steady_clock::now() - started)
                                   .count();
        return std::max(0.0, timeoutSeconds - elapsed);
    };

    Solution incumbent;
    try {
        incumbent = PartitioningAlgorithm(problem_).solve(remaining());
        std::string error;
        if (!incumbent.validate(problem_, &error)) {
            throw std::runtime_error(
                "partition incumbent failed validation: " + error);
        }
    } catch (const ExecutionCancelled&) {
        throw;
    }
    int64_t incumbentMakespan = solutionMakespan(incumbent);
    size_t subproblemCount = 0;
    size_t ownedCellCount = 0;
    size_t artificialBoundaryEdges = 0;
    RegionPartition partition;

    auto returnFallback = [&](const std::string& reason, bool timedOut) {
        setFallbackMetadata(incumbent, subproblemCount, ownedCellCount,
                            artificialBoundaryEdges, reason, timedOut, partition);
        return incumbent;
    };

    try {
        partition = RegionPartitioner().partition(problem_);
        subproblemCount = partition.subproblems.size();
        ownedCellCount = partition.targetCellCount;
        artificialBoundaryEdges = partition.artificialBoundaryEdges;
        if (partition.targetCellCount == 0U || partition.subproblems.empty()) {
            return returnFallback("region partition produced no target subproblems", false);
        }
    } catch (const ExecutionCancelled&) {
        return returnFallback("deadline during adaptive region partitioning", true);
    }

    std::vector<LocalSubproblemResult> localResults;
    localResults.reserve(partition.subproblems.size());
    try {
        const LocalSubproblemSolver localSolver;
        for (const auto& subproblem : partition.subproblems) {
            ExecutionControl::instance().checkpoint();
            localResults.push_back(localSolver.solve(problem_, subproblem));
            if (localResults.back().options.empty()) {
                return returnFallback(
                    "local heuristic produced no candidate for subproblem " +
                        std::to_string(subproblem.id),
                    false);
            }
        }
    } catch (const ExecutionCancelled&) {
        return returnFallback("deadline during local subproblem construction", true);
    }

    MergeResult merged;
    try {
        merged = MergeSolver().merge(problem_, localResults);
    } catch (const ExecutionCancelled&) {
        return returnFallback("deadline during global route merge", true);
    }
    if (merged.status != "FEASIBLE_HEURISTIC_MERGE" ||
        merged.solution.tours.empty()) {
        return returnFallback("merge failed: " + merged.status, false);
    }
    if (merged.makespan != solutionMakespan(merged.solution)) {
        return returnFallback("merge makespan disagrees with closed-tour recomputation", false);
    }

    Solution candidate = std::move(merged.solution);
    candidate.meta["requested_algorithm"] = "decompose";
    candidate.meta["algorithm_implementation"] = "decompose_heuristic";
    candidate.meta["candidate_source"] = "decomposition_heuristic_merge";
    candidate.meta["decomposition_status"] = "FEASIBLE_HEURISTIC_MERGE";
    candidate.meta["decomposition_exact"] = "false";
    candidate.meta["decomposition_local_solver"] = "heuristic_anchor_options";
    candidate.meta["decomposition_local_exact"] = "false";
    candidate.meta["decomposition_merge"] =
        "greedy_global_makespan_with_connectors_and_closure";
    candidate.meta["decomposition_subproblem_count"] =
        std::to_string(subproblemCount);
    candidate.meta["decomposition_owned_cell_count"] =
        std::to_string(ownedCellCount);
    candidate.meta["decomposition_connected_component_count"] =
        std::to_string(partition.connectedComponentCount);
    candidate.meta["decomposition_hole_count"] =
        std::to_string(partition.holeCount);
    candidate.meta["decomposition_artificial_boundary_edges"] =
        std::to_string(artificialBoundaryEdges);
    candidate.meta["decomposition_max_cells_per_subproblem"] =
        std::to_string(partition.maxCellsPerSubproblem);
    candidate.meta["decomposition_global_makespan"] =
        std::to_string(merged.makespan);
    candidate.meta["decomposition_cutter_allocation_count"] =
        std::to_string(merged.cutterAllocations.size());
    candidate.meta["decomposition_exact_backend_status"] =
        "unavailable; local options are heuristic";
    candidate.rawMetaJson["decomposition_partition_features"] =
        partitionFeaturesJson(partition);
    candidate.rawMetaJson["decomposition_merge_cutter_allocations"] =
        allocationsJson(merged.cutterAllocations);
    std::string error;
    if (!candidate.validate(problem_, &error)) {
        return returnFallback("global validation failed: " + error, false);
    }
    const int64_t candidateMakespan = solutionMakespan(candidate);
    if (candidateMakespan >= incumbentMakespan) {
        setFallbackMetadata(
            incumbent, subproblemCount, ownedCellCount, artificialBoundaryEdges,
            "merged candidate did not improve the validated partition incumbent",
            false, partition);
        incumbent.meta["decomposition_candidate_makespan"] =
            std::to_string(candidateMakespan);
        incumbent.meta["decomposition_partition_makespan"] =
            std::to_string(incumbentMakespan);
        return incumbent;
    }

    const auto& config = runtimeConfig();
    try {
        if (remaining() > 0.0 && problem_.numberOfCutters > 1) {
            Solution improved = TourConstruction::improveLns(
                problem_, candidate, started, timeoutSeconds,
                config.algorithmParameters.lnsIterations, config.randomSeed,
                config.algorithmParameters.lnsMaxAnchors,
                config.algorithmParameters.lnsMaxMoveAnchors);
            const auto improvedFlag = improved.meta.find("lns_improved");
            if (improvedFlag != improved.meta.end() &&
                improvedFlag->second == "true") {
                improved.meta["decomposition_pre_lns_makespan"] =
                    std::to_string(candidateMakespan);
                improved.meta["decomposition_global_makespan"] =
                    std::to_string(solutionMakespan(improved));
                improved.meta["requested_algorithm"] = "decompose";
                improved.meta["algorithm_implementation"] = "decompose_heuristic";
                improved.meta["candidate_source"] =
                    "decomposition_lns_improvement";
                improved.meta["decomposition_status"] =
                    "FEASIBLE_HEURISTIC_MERGE_WITH_LNS";
                improved.meta["decomposition_exact"] = "false";
                improved.meta["decomposition_subproblem_count"] =
                    std::to_string(subproblemCount);
                improved.meta["decomposition_owned_cell_count"] =
                    std::to_string(ownedCellCount);
                improved.meta["decomposition_artificial_boundary_edges"] =
                    std::to_string(artificialBoundaryEdges);
                return improved;
            }
        }
    } catch (const ExecutionCancelled&) {
        candidate.meta["execution_status"] = "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
        candidate.meta["decomposition_status"] =
            "TIME_LIMIT_WITH_MERGED_INCUMBENT";
    }
    return candidate;
}

}  // namespace cgshop2027
