# CG:SHOP 2027 Solver

Modular, validated C++17 solver for **Multi-Robot Lawn Mowing for Polyominoes**.
The implementation follows the official `pyutils27` instance and solution
schemas and keeps algorithms replaceable behind a small interface.

## Build

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

The solver executable is written to `build/bin/solver`.

## Usage

```sh
build/bin/solver -i data/test/tiny1.json -o result.solution.json \
  -a partition -t 10
```

Algorithms are `strip`, `partition`, `local`, `anchor-cover`,
`balanced-greedy`, `boustrophedon` (A1), `stc` (A2), `tsp-cov` (A3),
`frederickson` (B1), `mstc` (B2), `region-partition` (B3), `ilp` (C1 strip DP),
`column-gen` (C2), `lns` (D1), and `hybrid` (E). `anchor-cover` prioritizes cutter placements by uncovered
area, while `balanced-greedy` builds routes concurrently to avoid an overloaded
cutter. The input and output use the
official CG:SHOP 2027 JSON field names (`region_to_cover`, `cutter_center`,
`number_of_cutters`, and implicit closed tours).

The `ilp` algorithm uses the locally installed KONT command-line MIP solver
(`kont_cmd`) when CMake can find it (by default `/Applications/kont72/bin`).
It solves a binary min-max assignment of vertical cutter-coverage strips, then
constructs and validates rectilinear tours from that assignment. If KONT is not
installed, cannot obtain a valid license, or returns no feasible assignment, the
algorithm reports a warning and uses the validated partition fallback.

Run all local fixtures with:

```sh
./scripts/run_all.sh
```

If Python 3.10+ and `cgshop2027-pyutils` are installed, the script also invokes
the official validator.

## Layout

See [docs/architecture.md](docs/architecture.md) for the module boundaries and
algorithm contract. Test fixtures live under `data/test`; generated solutions
and plots are intentionally kept out of the C++ build targets.

## Quality checks

```sh
ctest --test-dir build --output-on-failure
./scripts/run_all.sh
```

`run_all.sh` checks that `build/` was configured for this checkout and
reconfigures/rebuilds it when the cache belongs to another path. This avoids
running stale solver binaries after moving or copying the repository.

For official validation:

```sh
python3 scripts/validate.py INSTANCE.instance.json SOLUTION.solution.json
```

To compare all built-in algorithms and persist the best result per instance:

```sh
python3 scripts/benchmark.py --instances data/test --timeout 10
```

To run every built-in algorithm on every instance, validate each generated
solution, create one PNG figure per instance/algorithm pair, and write both a
detailed run log and a wide comparison table:

```sh
python3 scripts/solve_all.py --instances data/test --timeout 10 \
  --output build/all-results
```

The output contains `all-results.tsv` (one row per run),
`data/test/master-table.tsv` (instances as rows and algorithms as columns,
with makespans or a per-run limit/failure status), and
`<instance>.<algorithm>.png` figures. Each instance/algorithm run is hard
limited independently by time and memory; use `--memory` to change the
default 2048 MiB cap or `--master-table` to choose another table path. Add
`--official` to run the official validator in addition to the solver's
built-in validation. This option fails fast if `cgshop2027-pyutils` is
unavailable and records officially rejected solutions as failed runs. Use
`--algorithms partition,ilp,hybrid` to select a subset for a quick experiment.

The local virtual environment can be used for reproducible official
validation:

```sh
.venv/bin/python scripts/solve_all.py --instances data/test \
  --output build/all-results --official
```

## Logging

The C++ solver writes timestamped, component-scoped logs to stderr (errors) or
the standard logging stream (informational and diagnostic messages). Reader,
writer, solver, and every algorithm entry point emit lifecycle timing at debug
level. Set `CGSHOP_LOG_LEVEL` to `debug`, `info` (default), `warning`, or
`error` to control verbosity:

```sh
CGSHOP_LOG_LEVEL=debug build/bin/solver -i data/test/tiny1.json \
  -o result.solution.json -a hybrid -t 10
```

For result analysis, `scripts/analyze_results.py` writes a TSV containing every
available solution artifact and its makespan. `scripts/ilp_coverage.py` invokes
`gurobi_cl` for a bounded cutter-placement set-cover relaxation; its selected
anchors are a lower-bound study and do not claim an optimal closed-tour route.
See [docs/ilp-analysis.md](docs/ilp-analysis.md) for the report definitions and
the distinction between the ILP relaxation and the original routing objective.
