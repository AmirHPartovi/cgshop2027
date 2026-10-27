# Algorithm registry and implementation inventory

The public mode registry is `config/solver_modes.json`. Legacy heuristic
component IDs are selected by the conditional dispatch in `src/main.cpp`; there
is no independent factory or plugin registry. The CLI makes one concrete
object and calls its virtual `BaseAlgorithm::solve(timeout)`. `local` is special: the
dispatch expression first computes a `PartitioningAlgorithm::solve(timeout)`
solution and passes it to the `LocalSearch` constructor.

**Guarantees:** No registered algorithm is an exact solver or has a proven
approximation guarantee for the original makespan objective. Every registered
algorithm returns a heuristic candidate, searches for heuristic improvements,
or selects among heuristic candidates. `ilp` optimizes a vertical-column
surrogate only. There is no registered proof-grade route-length lower-bound
computation.

**Legend:** “candidate” means a complete `Solution` is returned; all CLI
results must pass the final C++ validator. “Multi-cutter” distinguishes real
route assignment from wrapping one route in `makeSolution`, which pads missing
cutters with one-point stationary tours at `problem.cutterCenter`. “Internal
validation” refers to an explicit call to `Solution::validate`, not the final
CLI gate. Randomness is deterministic or absent as stated.

**Shared candidate contract:** `BaseAlgorithm::makeSolution` rejects excess
route groups, normalizes duplicate consecutive/explicit closing points, and
pads missing groups with stationary tours. `finishCandidate` validates each
algorithm's result and throws on invalid output instead of substituting a
candidate. The heuristic orchestration boundary may explicitly select a
partition fallback and marks `requested_algorithm`,
`algorithm_implementation`, `candidate_source`, `fallback_algorithm`, and
`fallback_reason` distinctly. The public `decompose` mode is implemented by
`DecomposeSolver` and reports a non-exact decomposition heuristic or an
explicitly sourced partition incumbent. `SolverResult` separately records candidate
existence, validation outcomes, completion status, proof scope, provenance,
runtime, and termination reason. The `ip-kont` mode cannot use a heuristic
fallback. Hybrid also records its portfolio winner and retains a validated
incumbent when optional improvement is cancelled or rejected. Single-route
implementations record whether stationary padding was needed; this does not
imply multi-cutter assignment.

| CLI name (aliases) | Implementation / entry | Actual construction and shared helpers | Cutter/result character | Randomness | Timeout and validation | Limitations / fallback |
|---|---|---|---|---|---|---|
| `strip` (none) | `StripAlgorithm::solve`, `StripAlgorithm.cpp` | `coverageCenters`; sort by row then x; divide ordered centers into k groups; `BaseAlgorithm::makeSolution` | Multi-group candidate, then validation | None | Ignores timeout; explicitly validates | On invalid result calls `PartitioningAlgorithm::solve()` without forwarding timeout. “strip” is ordered point partitioning, not a distinct strip-DP method. |
| `partition` (none) | `PartitioningAlgorithm::solve`, `PartitioningAlgorithm.cpp` | `coverageCenters`; serpentine row order; split ordered centers into k groups; base `makeSolution` | Multi-group candidate | None | Shared cancellation checkpoints and `finishCandidate` validation | Explicit fallback target at the heuristic orchestration boundary and in the legacy `ilp` surrogate. |
| `local` (none) | `LocalSearch::solve`, `LocalSearch.cpp` | Constructed in `main.cpp` with a prior partition solve; relocates bounded subsets of coverage anchors between cutter assignments and reconstructs each route | Multi-cutter assignment search | Configured random seed | Central iteration/anchor/move caps; deadline checkpoints; validates every reconstructed candidate | Retains the validated input incumbent and reports search counts, improvement, runtime, and termination reason. |
| `anchor-cover` (`anchor`) | `AnchorCoverAlgorithm::solve`, `AnchorCoverAlgorithm.cpp` | Repeated maximum uncovered-cell gain over `coverageCenters` and cutter cells; assign next placement to least estimated load | Multi-cutter greedy assignment | None | Checks timeout at outer/placement scan; internal validation | On timeout assigns remaining centers round-robin; invalid candidate falls back to partition. “Cover” is candidate construction, not an intermediate bound. |
| `balanced-greedy` (`greedy`) | `BalancedGreedyRouteAlgorithm::solve`, `BalancedGreedyRouteAlgorithm.cpp` | Repeatedly choose shortest-load cutter and its nearest unused coverage center; base `makeSolution` | Multi-cutter greedy route groups | None | Checks timeout within candidate scans and remaining-center assignment; internal validation | Remaining centers are assigned round-robin on timeout; invalid candidate falls back to partition. |
| `boustrophedon` (`a1`, `zigzag`) | `BoustrophedonAlgorithm::solve`, `BoustrophedonAlgorithm.cpp` | `TourConstruction::coveringAnchors` -> column grouping -> `boustrophedon` -> `makeSolution` | Primarily a single route; padded to k tours, not a real multi-cutter allocation | None | Ignores timeout; internal validation | Invalid route falls back to partition. A1 label does not imply multi-cutter output. |
| `stc` (`a2`) | `StcAlgorithm::solve`, `StcAlgorithm.cpp` | `coveringAnchors` -> `spanningTreeWalk` (grid-neighbor spanning forest plus component links) -> `makeSolution` | Primarily a single tree-walk route; padded to k | None | Ignores timeout; internal validation | Invalid result falls back to partition. |
| `tsp-cov` (`tsp_cov`, `a3`) | `TspCovAlgorithm::solve`, `TspCovAlgorithm.cpp` | `coveringAnchors` -> nearest-neighbor cycle ordering and bounded 2-opt in `tspCov` -> `makeSolution` | Primarily one route; padded to k | None | TSP helper checks timeout; internal validation | For >3500 anchors or timeout helper returns boustrophedon. Invalid result falls back to partition. This is a heuristic, not an exact TSP solver. |
| `frederickson` (`b1`) | `FredericksonSplitAlgorithm::solve`, `FredericksonSplitAlgorithm.cpp` | Build boustrophedon and spanning-tree tours; optionally TSP tour; choose shortest; split its closed perimeter with `splitFrederickson` | Multi-cutter output by slicing a single giant tour | None | TSP subcall checks timeout; other work does not; internal validation | Invalid split falls back to partition. |
| `mstc` (`b2`) | `MstcAlgorithm::solve`, `MstcAlgorithm.cpp` | `coveringAnchors` -> `TourConstruction::mstc` tree component partition and tree walks | Real multi-cutter tree groups | None | Ignores timeout; internal validation | Invalid candidate falls back to partition. |
| `region-partition` (`b3`) | `RegionPartitionAssignAlgorithm::solve`, `RegionPartitionAssignAlgorithm.cpp` | `coveringAnchors` -> recursive longest-axis bisection -> per-group boustrophedon | Multi-cutter region-ish partition of anchor points | None | Ignores timeout; internal validation | Invalid candidate falls back to partition; bisection sorts points, not polygon-connected regions. |
| `ilp` (legacy `c1` alias) | `IlpAlgorithm::solve`, `IlpAlgorithm.cpp` | `coveringAnchors`; group anchors by x into columns; LP assigns each column to one cutter and minimizes max summed proxy column cost; reconstruct sorted-anchor closed tours and validate | Multi-cutter assignment candidate, or partition fallback | None | KONT child timeout and exit status checked; complete column assignment parsed; internal route validation | Surrogate only: modeled `cost[j] = 2 * vertical_span(j) + 2` does not encode route order or actual closed-tour makespan. Never certifies original-objective optimality or a valid lower bound. Reports model dimensions, raw solver status/log, termination, and `FEASIBLE_NOT_PROVEN` for a valid recovered route. Timeout has no incumbent because solution extraction follows optimize completion. Uses a unique temporary directory and removes it on handled paths. |
| `connected-growth` (legacy `column-gen`, `c2`, `bap`) | `ConnectedGrowthAlgorithm::solve`, `ColumnGenerationAlgorithm.cpp` | `coveringAnchors` -> `connectedGrowthTours`, using MSTC and split-tour baselines plus deterministic budget search/growth | Multi-cutter candidate | Deterministic coordinate-ordered seed selection | Interrupted budget checks return `TIMEOUT_UNKNOWN`; retain the baseline candidate; internal validation | Greedy connected-growth heuristic, not column generation: no restricted master, pricing problem, or column-generation guarantee. A completed budget check is not a proof about all possible assignments. |
| `lns` (`d1`) | `LnsMultiCutterAlgorithm::solve`, `LnsMultiCutterAlgorithm.cpp` | Frederickson incumbent -> full coverage-anchor assignment -> bounded relocation and per-cutter boustrophedon reconstruction | Multi-cutter assignment search | Configured `std::mt19937_64` seed | Central iteration/anchor/move caps; deadline checkpoints; validates each candidate | Never concatenates existing route vertices. Keeps the best validated incumbent and records candidate/move counts, runtime, improvement, and termination. |
| `hybrid` (`e`, public `heuristic` mode) | `HybridSolver::solve`, `HybridSolver.cpp` | Partition incumbent, then configured Frederickson and MSTC candidates; optionally connected-growth when explicitly configured; choose minimum canonical closed-tour makespan and run anchor-relocation LNS | Validated candidate portfolio with multi-cutter constructions | Configured seed for randomized relocation | One cooperative search deadline covers candidate generation, candidate validation, and LNS; preserves the best internally validated candidate and its actual producer metadata on timeout | The default portfolio excludes the IP-KONT surrogate and connected-growth, whose baseline trials consumed most short budgets without establishing a quality benefit. Frederickson's bounded TSP-COV helper remains available; LNS improvements are tagged `hybrid_lns_improvement`. |
| `decompose` (public mode) | `DecomposeSolver::solve`, `DecomposeSolver.cpp` | Actual target-cell connected components -> adaptive connected region partitioning -> heuristic local anchor routes -> greedy global assignment, connector and closing-edge merge; optional LNS | Global cutter routes assembled from region options; unused cutters get stationary tours | Deterministic partition, route alternatives, and tie-breaking; configured seed only for optional LNS | Shared execution deadline; retains partition incumbent on local failure, timeout, invalid merge, or non-improvement; validates the complete merged solution | Local options and merge are heuristic; no exact local backend, complete Pareto set, or global-equivalence proof. See `decomposition-heuristic.md`; result is never globally optimal. |

`TourConstruction::stripIlpTours` exists but the registered legacy `ilp` path writes and
solves its own column-assignment LP in `IlpAlgorithm.cpp`; no call from `ilp` to
`stripIlpTours` was found.
