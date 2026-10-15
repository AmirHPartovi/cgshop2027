# ILP and Algorithm Analysis

The generated reports are:

- `build/evaluation.tsv`: every available candidate, checked by official
  `pyutils27`, with feasibility and makespan.
- `build/results.tsv`: parsed artifact inventory, including source paths.
- `build/ilp-results.tsv`: one bounded Gurobi placement-relaxation result per
  test instance.

`scripts/ilp_coverage.py` models anchor selection as a binary set-cover ILP.
It minimizes the number of selected cutter placements that cover every region
cell. This is useful as a cutter-aware coverage lower bound, but it is not an
exact formulation of the requested minimum-makespan closed-tour problem:
selected anchors still need to be assigned to cutters and connected by
rectilinear tours. Large instances are explicitly marked `SKIPPED` when their
bounding box exceeds the configured 5,000-cell study limit.

Gurobi status is therefore reported separately from route feasibility. Never
interpret `selected_anchors` as a tour makespan or as a proof of optimality for
the original problem.
