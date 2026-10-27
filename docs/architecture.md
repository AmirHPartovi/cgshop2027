# Solver Architecture

## Runtime flow

`src/main.cpp` is the executable entry point and legacy heuristic-component
registry. The public modes are `heuristic`, `ip-kont`, and `decompose`, from
`config/solver_modes.json`; the C++ runtime and Python runners validate against
that shared registry. `heuristic` currently dispatches to the hybrid solver.
The other modes return a typed `unavailable` result without invoking a
heuristic or writing a candidate. Legacy `--algorithm` names and aliases remain
as heuristic-component overrides for batch experiments.

## Module map

- `src/core/` defines the domain model. `Problem` stores the region, cutter,
  cutter center, and cutter count; validates instance geometry; rasterizes the
  region and cutter into integer cells; and tests whether tours cover the
  region. `Solution` stores one point sequence per cutter and validates tour
  count, non-empty routes, rectilinear edges, and coverage.
- `src/io/` translates the JSON instance format into `Problem` and writes
  `Solution` as JSON. The reader invokes `Problem::validate`; the writer is
  called by the CLI only after solution validation. The official Python
  checker is separate, in `scripts/validate.py`.
- `src/algorithms/` contains implementations of `BaseAlgorithm`. The base
  class provides shared tour construction, coverage-center generation,
  rectilinear tour-length and makespan calculations, timeout checking, and
  solution assembly. Missing cutter routes are stationary at the instance's
  cutter center, duplicate consecutive/explicit closing points are normalized,
  and excess route groups are rejected. `finishCandidate` rejects invalid
  candidates; only the heuristic orchestration boundary can choose a partition
  fallback. Requested algorithm, actual implementation, and candidate source
  remain separate metadata. `src/core/SolverResult` defines typed validation,
  completion, and optimality statuses and writes a sibling result report.
  `src/core/ExecutionControl` supplies the shared
  monotonic deadline and cancellation checkpoints used by geometry,
  construction, validation, hybrid incumbent retention, and KONT child cleanup.
  The CLI reserves a finalization window and distinguishes a timeout fallback
  from normal completion in solution metadata. The concrete implementations are strip, partition,
  local search, anchor cover, balanced greedy, boustrophedon (A1), STC (A2),
  TSP coverage (A3), Frederickson split (B1), MSTC (B2), region partition
  (B3), KONT vertical-column assignment surrogate (`ilp`, legacy C1 alias),
  connected-growth heuristic (legacy C2 aliases), LNS (D1), and
  hybrid (E).
- `src/utils/` contains logging (`Logger` / `LogScope`) and a standalone
  `Timer`. The shared algorithm timeout predicate is implemented in
  `BaseAlgorithm`, rather than in `Timer`.
- `tests/` builds four CTest executables: geometry, algorithms, I/O, and
  execution control, plus registered Python regression suites.
- `scripts/` contains the official-validator adapter, local fixture runner,
  benchmark/evaluation drivers, result analysis, and visualization helpers.

## Feasibility and objective boundaries

Tours are represented by their listed vertices with an implicit edge from the
last vertex back to the first. Both `BaseAlgorithm::tourLength` and the Python
benchmark drivers include that closing edge when calculating route length.
The C++ coverage check expands each rectilinear edge over its integer lattice
centers and applies the cutter-cell offset at each center. The official
`cgshop2027_pyutils` checker, when installed, is invoked separately by
`scripts/validate.py` and by the `--official` option in
`scripts/benchmark.py` / `scripts/auto_solve.py`.

The C++ validator is the gate in the solver executable; it is not a substitute
for demonstrating that the official checker has accepted a candidate. Use the
official checker before treating a solution as eligible for quality
comparisons.

The `ilp` / `c1` implementation may call `kont_cmd` if it was found at CMake
configuration time. The model assigns vertical strips to cutters and minimizes
the largest modeled strip load; tours are constructed afterward and validated.
If that backend is unavailable or its constructed result fails validation,
the implementation uses the partition fallback. This is not an exact
formulation or proof of optimality for the minimum-makespan closed-tour
objective. The separate `scripts/ilp_coverage.py` study is a cutter-placement
set-cover relaxation, as described in [ilp-analysis.md](ilp-analysis.md).

## Build and verification paths

The CMake project builds `cgshop_core`, the `solver` executable, and the three
CTest targets:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

`scripts/run_all.sh` runs the partition algorithm on local fixtures and calls
the official checker when its Python package is available. For a
resource-limited algorithm/instance matrix, use `scripts/benchmark.py`; pass
`--official` to require the official checker for each candidate.
`scripts/auto_solve.py` also requires official validation before selecting or
writing a result.
