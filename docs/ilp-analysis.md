# ILP and Algorithm Analysis

The generated reports are:

- `build/evaluation.tsv`: every available candidate, checked by official
  `pyutils27`, with feasibility and makespan.
- `build/results.tsv`: parsed artifact inventory, including source paths.
- `build/ilp-results.tsv`: one bounded Gurobi placement-relaxation result per
  test instance.

`scripts/ilp_coverage.py` models static anchor selection as a binary set-cover
ILP and minimizes the number of selected candidate placements. This is a
placement-count study only, not a proof-grade lower bound on route length or
makespan: a tour can cover cells at intermediate centers along its travel, and
the model does not represent route trajectories. Its selected-placement
objective must not be compared with a tour makespan. Large instances are
explicitly marked `SKIPPED` when their bounding box exceeds the configured
5,000-cell study limit.

Gurobi process status is reported separately from route feasibility. The output
uses `PLACEMENT_OBJECTIVE` and does not claim that the static placement objective
is optimal unless solver logs independently establish that status. Never
interpret `selected_anchors` as a tour makespan or as a proof of optimality for
the original problem. The repository currently reports no proof-grade
route-length lower bound for the original makespan objective.
The former area-divided-by-cutter-capacity estimate is also not a route-length
lower bound: stationary cutters can cover positive area with zero movement.
