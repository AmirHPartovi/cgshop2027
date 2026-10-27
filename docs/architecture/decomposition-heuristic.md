# Adaptive decomposition heuristic

The public `decompose` mode is a heuristic pipeline, not an exact global
solver. The exact IP-KONT backend remains unavailable; no local region is
claimed to have been solved exactly.

## Components

- `RegionPartitioner` rasterizes the complete target region, finds its
  four-neighbor connected components, and recursively bisects large or
  difficult components. Every emitted subproblem remains connected and owns
  each target cell exactly once. The partitioner records bounding-box area,
  boundary and narrow-cell counts, a cutter-aware difficulty estimate, and
  artificial boundaries introduced by splitting.
- `LocalSubproblemSolver` maps every owned target cell to a cutter-center
  anchor using one fixed cutter cell. It constructs deterministic
  boustrophedon and spanning-tree-walk alternatives with existing tour
  construction helpers. These are candidate builders only; they do not solve
  the local routing problem exactly.
- `MergeSolver` greedily assigns each local route option to one of the global
  cutters, choosing orientation and accounting for fragment travel,
  inter-fragment connectors, and the final closing edge. It assembles complete
  tours and validates coverage against the whole instance, including across
  artificial region boundaries.
- `DecomposeSolver` preserves the validated partition incumbent if
  decomposition fails, times out, or does not improve it. It applies LNS only
  to a better validated merged candidate and preserves that candidate if the
  deadline interrupts improvement.

The result metadata records the selected candidate source, exactness flags,
subproblem feature evidence, artificial-boundary count, global makespan, and
cutter allocations. A partition candidate returned after a failed or
non-improving merge is identified as a partition fallback, not as a merged
decomposition result. The outer solver performs its final validation before
writing the solution, and `scripts/auto_solve.py --mode decompose` additionally
requires official pyutils validation before publishing the output.

## Limitations

The split policy uses deterministic raster features and fixed size thresholds;
it does not train or estimate region-specific solver performance. Local
alternatives cover owned cells through their anchor placements, but there is
no exact local solver, Pareto frontier, or proof that these alternatives
preserve globally useful entry/exit choices. The greedy merger considers
connectors and closed-tour makespan but does not jointly optimize all region
allocations and orderings. Therefore even an officially feasible result is
only a feasible decomposition heuristic and never a global-optimality claim.
