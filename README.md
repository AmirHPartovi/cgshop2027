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

## Official Python verifier

Use the pinned official utilities release in the existing local virtual
environment. The dependency and verified parser, verifier, schema, archive,
and visualization APIs are documented in
[docs/cgshop-pyutils-dependency.md](docs/cgshop-pyutils-dependency.md).

```sh
.venv/bin/python -m pip install --upgrade -r requirements-cgshop.txt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python"
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Configure CMake with `.venv/bin/python` so the official compatibility smoke
test runs under the supported interpreter (Python 3.10 or newer).

## Usage

```sh
build/bin/solver -i tests/fixtures/instances/tiny-square.instance.json \
  -o result.solution.json \
  -a partition -t 10
```

## Runtime configuration

`config/default.json` is the single defaults file consumed by the C++ solver
and Python batch runners. Use `--config FILE` to start from a user-selected JSON
configuration; explicit CLI options override it, and omitted values come from
the defaults file. For example:

```sh
build/bin/solver -i tests/fixtures/instances/tiny-square.instance.json \
  -o build/example.solution.json --config config/default.json \
  --algorithm hybrid --algorithm-timeout 10 --kont-timeout 2 \
  --seed 2027 --lns-iterations 250 --portfolio \
  boustrophedon,stc,frederickson,mstc,region-partition,ilp,connected-growth,tsp-cov
```

Each solver output has a sibling `<solution>.config.json` containing requested
and effective settings. Batch runs also write `runtime-config.json` and
per-solver reports. Benchmark reports include the effective worker product
(`benchmark_jobs * threads_per_solver`) and any automatic reduction of
`benchmark_jobs` to the detected CPU-worker count. The current algorithms are
single-threaded, so `threads_per_solver` must be 1; parallel benchmark jobs
are independent solver processes and do not change that setting.

Timeout meanings are distinct: the global deadline bounds the whole batch;
per-instance timeout is the wall-clock limit for each solver process;
per-algorithm timeout caps the algorithm budget within the instance process;
and IP-KONT timeout caps its optional child process within both parent
deadlines. Deadlines use monotonic clocks. Cooperative search reserves up to
five seconds (20% of the run, with a 250 ms minimum) for final validation and
output; an already validated hybrid incumbent is retained when later work is
cancelled. If an algorithm is interrupted before it returns a candidate, the
solver attempts a partition fallback within the reserved finalization window.
All limits are in seconds and the batch runner also enforces the remaining
global budget externally.

On macOS the C++ process cannot enforce `RLIMIT_AS`; benchmark runners sample
and stop the complete process group when aggregate process-tree RSS exceeds
the configured target. On platforms with `RLIMIT_AS`, the solver additionally
applies a per-process address-space cap; this is not an aggregate tree cap.
Resource reports record elapsed wall time, sampled process-tree RSS, sampled
cumulative process-tree CPU time when available, sample counts, and the
termination reason. Sampling can miss short-lived memory peaks and CPU use
between samples, so these observations are not exact high-water marks. Missing
measurements are `null`, not zero. A failed resource probe stops the batch run
rather than silently disabling enforcement.

The implemented algorithm parameters are `lns_iterations` (default `250`,
maximum `100000` iterations), `lns_max_anchors` (default `5000`, skip
assignment search above this coverage-anchor count), `lns_max_move_anchors`
(default `16`, largest anchor relocation), `tsp_max_anchors`, and
`two_opt_passes`. Local search and LNS relocate coverage anchors between
cutter assignments, reconstruct each closed route, and accept only candidates
that pass the internal full-coverage and route validator and improve makespan.
They preserve the input incumbent and record evaluated candidates, accepted
moves, improvement, runtime, and termination reason. Official eligibility is
still established separately by the official checker. The seed controls
randomized local search and LNS moves and is varied across repetitions for
`local`, `lns`, and `hybrid`. `heuristic_portfolio`
selects the candidate algorithms evaluated by `hybrid`. The IP-KONT setting is named
`ip_kont_surrogate`, not “exact”: it optimizes a strip-assignment surrogate,
not the original closed-tour routing objective. `exact_solver_max_candidates`
can skip that backend above a configured column count. Difficulty-tier filtering
and medium-instance exploratory budgets are rejected unless set to the
supported defaults (`["all"]` and `0`): no validated tier classifier exists
yet. This prevents unclassified instances or unsupported settings from being
silently treated as meaningful.

Important configuration values in `config/default.json` are:

| Key | Default | Meaning |
|---|---:|---|
| `global_run_deadline_seconds` | `null` | No batch-wide deadline |
| `per_instance_timeout_seconds` | `10` | Wall-clock limit per solver process |
| `per_algorithm_timeout_seconds` | `10` | Solver algorithm budget |
| `ip_kont_timeout_seconds` | `30` | Maximum IP-KONT time, additionally bounded by the run |
| `threads_per_solver` | `1` | Internal solver workers; only one is currently supported |
| `benchmark_jobs` | `1` | Concurrent solver processes |
| `memory_limit_mib` | `2048` | Per-process or sampled process-tree memory limit |
| `random_seed` | `2027` | Deterministic heuristic seed |
| `algorithms` | `["hybrid"]` | Selected algorithm(s) for the batch runner |
| `randomized_repetitions` | `1` | 1–1000 repeats for local/LNS/hybrid; deterministic algorithms run once |
| `output_directory` | `"build/results"` | Default batch output directory |
| `overwrite_existing` | `false` | Refuse existing outputs unless explicitly enabled |
| `logging_verbosity` | `"info"` | `debug`, `info`, `warning`, or `error` |
| `official_validation` | `false` | Require the official pyutils checker in batch runs |

## Instance workload profiles

`scripts/profile_instances.py` creates deterministic pre-solve workload
estimates and can optionally execute a bounded, size-stratified pilot:

```sh
python3 scripts/profile_instances.py --instances data/test
python3 scripts/profile_instances.py --instances data/test --pilot \
  --pilot-max-instances 12 --timeout 3 --memory-limit-mib 1024
python3 scripts/profile_instances.py --instances data/test --pilot --official
```

Each invocation creates a new directory under `build/profiles/` by default
(or at `--output-dir`) and refuses to overwrite an existing directory. It
writes `profile.json`, `profile.tsv`, and `summary.md`; pilot runs also produce
`runtime-vs-raster-work.svg` when at least three successful measurements are
available. Pilot solution files are temporary. `--official` requires
`cgshop2027_pyutils`; without it, a successful candidate is reported only as
internally validated by the C++ solver, not officially verified.

Thresholds and the automatic pilot algorithm mapping are in
`config/instance_profiler.json`. The deterministic `LIGHT`/`MEDIUM` bounds
require both the estimated raster-work proxy and estimated anchor count to be
below their tier limits; higher work is `HEAVY`, and unavailable required
features are `UNKNOWN`. Defaults are `LIGHT <= 10,000,000` raster point tests
and `<= 50,000` anchors; `MEDIUM <= 1,000,000,000` raster point tests and
`<= 500,000` anchors. The workload proxy uses the outer bounding-box cell
area multiplied by total region-ring vertices, reflecting the active
`Problem::raster` scan; estimated anchor count follows
`TourConstruction::coveringAnchors`, which creates one shifted center per
region cell. This also tracks repeated geometry rasterization. TSP-COV has a
separate quadratic nearest-neighbor phase only while anchor count is under its
configured cap; above that it falls back to the simpler route. Ring topology
is not fully validated during feature extraction,
so threshold confidence is deliberately LOW. The defaults are conservative
and configurable, not fitted runtime guarantees.

The feature report distinguishes input-derived quantities from estimates.
The JSON nests these as `measured_features`, `derived_exact_features`, and
`estimated_features` for each instance.
Potential anchor/cutter-cell pairs are an upper-bound workload proxy, and
coordinate-payload bytes are only a lower bound; total hash-based coverage
memory and actual coverage relationships are left null because they depend
on topology, route geometry, container overhead, and runtime. The IP-KONT
column-count upper bound uses the instance x-span and region cell count; its
variable and constraint upper bounds follow `columns * cutters` and
`columns + cutters` from the implemented assignment model. These are
size-screening bounds, not proof of useful exact solving: the model remains a
strip-assignment surrogate. Pilot profiles separately record wall time, child
CPU time where available, sampled peak process-tree RSS, exit/timeout/resource
status, and validation level.
Correlation is reported only with at least three successful, nonconstant
measurements; failed or unvalidated runs remain listed but are excluded.
The profiler never automatically fits thresholds from a small pilot.

For `profile_instances.py --algorithm auto`, the pilot labels a single-run
algorithm using its configured `automatic_algorithm_by_tier` table. The
separate policy runner below uses bounded tier portfolios instead.

## Policy-based solver selection

`scripts/auto_solve.py` classifies one instance before solving, runs a
configured bounded portfolio, officially validates each successful candidate,
and retains the lowest-makespan officially valid result:

```sh
python3 scripts/auto_solve.py \
  --instance tests/fixtures/instances/tiny-square.instance.json \
  --output build/auto/tiny-square.solution.json
python3 scripts/auto_solve.py --instance INSTANCE --output OUTPUT \
  --algorithm partition
python3 scripts/auto_solve.py --instance INSTANCE --output OUTPUT \
  --policy heuristic
```

The default is `--policy auto`; `--policy heuristic` explicitly requests the
tier portfolio, and `--algorithm NAME` forces one named algorithm rather than
silently entering auto mode. `--policy exact` fails before solving because no
mathematically exact method for the original closed-tour makespan objective
exists in this repository. `config/auto_policy.json` contains tier portfolios,
per-candidate timeouts, exact-method availability, and the IP-KONT surrogate
probe size/time limits. Runtime timeouts and memory limits still cap those
policy budgets. The defaults run 3 LIGHT candidates with up to 10 seconds each,
6 MEDIUM candidates with up to 2 seconds each, and 4 HEAVY candidates with up
to 1 second each; the total is bounded by portfolio length and any configured
global deadline.

The LIGHT policy records that exact solving was preferred but unavailable,
then uses its bounded heuristic portfolio. The existing `ilp` implementation
does not solve the original route objective and may silently return a partition
fallback; it is excluded from default portfolios. Only an explicit
`--include-ip-kont-surrogate` can add it, and then only when
`config/auto_policy.json` enables a positive budget and estimated-column cap and central
runtime configuration allows `ip_kont_surrogate`. Reports distinguish a KONT
surrogate incumbent from a heuristic fallback. Neither is marked optimal.

Every invocation requires `cgshop2027_pyutils`; internal C++ validation alone
does not qualify candidates for selection. The requested policy/algorithm,
estimated tier, actually executed candidates, per-candidate status, selected
algorithm and solution, official-validation status, candidate provenance,
selection reason, and optimality certification status are saved in
`<output>.selection.json`. If no official candidate exists, the runner exits
nonzero and writes no solution. Existing outputs are refused unless
`--overwrite` is passed or central `overwrite_existing` is enabled. The exact
model status remains `unavailable`; heuristic fallback after a timeout never
changes that status.

Algorithms are `strip`, `partition`, `local`, `anchor-cover`,
`balanced-greedy`, `boustrophedon` (A1), `stc` (A2), `tsp-cov` (A3),
`frederickson` (B1), `mstc` (B2), `region-partition` (B3), `ilp` (legacy
name for the KONT column-assignment surrogate), `connected-growth` (formerly
`column-gen`, C2), `lns` (D1), and `hybrid` (E). `column-gen`, `c2`, and `bap`
remain accepted legacy aliases; they run the same connected-growth heuristic
and do not imply column generation. `anchor-cover` prioritizes cutter
placements by uncovered area, while `balanced-greedy` builds routes
concurrently to avoid an overloaded cutter. The input and output use the
official CG:SHOP 2027 JSON field names (`region_to_cover`, `cutter_center`,
`number_of_cutters`, and implicit closed tours).
Instance boundaries are implicitly closed, must be simple orthogonal rings,
and use CCW outer / CW hole orientation. Solutions are validated for exact
format identifiers, matching UIDs, cutter count, closed rectilinear tours,
and full swept-region coverage before they are written. The objective is the
maximum closed-tour Manhattan length, including each last-to-first edge; all
Python reporting scripts share `scripts/solution_metrics.py`.

### Algorithm guarantees

No registered method currently has a proved approximation guarantee for the
original closed-tour makespan objective. `ilp` optimizes a vertical-column
assignment surrogate and is not exact for that objective. No current command
reports a proof-grade route-length lower bound or a certified optimum.

| Algorithm | Classification for the original objective |
|---|---|
| `strip`, `partition`, `anchor-cover` (`anchor`), `balanced-greedy` (`greedy`), `boustrophedon` (`a1`, `zigzag`), `stc` (`a2`), `tsp-cov` (`tsp_cov`, `a3`), `frederickson` (`b1`), `mstc` (`b2`), `region-partition` (`b3`), `connected-growth` (`column-gen`, `c2`, `bap`) | Heuristic solution constructors; no formal approximation guarantee |
| `local`, `lns` (`d1`) | Heuristic local-search / large-neighborhood improvement methods; no formal approximation guarantee |
| `ilp` (`c1`) | Heuristic candidate constructor driven by a surrogate optimization model; no original-objective exactness or approximation guarantee |
| `hybrid` (`e`) | Sequential heuristic portfolio; no formal approximation guarantee |

## IP-KONT exactness and reference semantics

The registered `ilp` name is retained for compatibility, but it is **not an
exact solver for the CGSHOP closed-tour makespan objective**. The current
formulation is a vertical-column assignment surrogate. For each column `j`
and cutter `i`, it uses binary `x[j,i]`, plus a continuous `z`:

```text
minimize z
subject to
  sum_i x[j,i] = 1                         for every column j
  sum_j cost[j] * x[j,i] <= z              for every cutter i
  x[j,i] in {0,1}, z >= 0
  cost[j] = 2 * (max_y(j) - min_y(j)) + 2
```

With `J` columns and `C` cutters, the generated LP has `J*C + 1` variables
and `J + C` constraints, in addition to bounds and integrality. Each column
groups coverage anchors with the same x-coordinate. After assignment, the
implementation sorts the assigned anchors and constructs closed rectilinear
tours. Neither route order nor the reconstructed tour length is modeled by
the LP; the modeled column cost is not established as a lower bound or as an
equivalent expression for that route's makespan. Therefore even a raw KONT
`OPTIMAL` status proves only optimality for this surrogate, not for the
original routing problem.

Only a recovered route that passes the internal feasibility validator is
returned as an IP-KONT candidate; benchmark runs with `--official` and the
auto-selection runner also require the official validator. A malformed
assignment is rejected. The solver waits for KONT's child process to exit,
checks its exit status, timeout, full
assignment parse, and recovered-route validity; seeing a solution filename
alone is not success. Captured KONT output is retained in solution metadata
and benchmark reference reports.

The IP-KONT comparison status is one of `OPTIMAL_CERTIFIED`,
`FEASIBLE_NOT_PROVEN`, `TIME_LIMIT_WITH_INCUMBENT`,
`TIME_LIMIT_NO_INCUMBENT`, `INFEASIBLE_PROVEN`, `INVALID_OUTPUT`, or `ERROR`.
The current surrogate can produce a feasible route (`FEASIBLE_NOT_PROVEN`),
a solver-reported time limit with a recovered candidate
(`TIME_LIMIT_WITH_INCUMBENT`), a wrapper timeout without an incumbent
(`TIME_LIMIT_NO_INCUMBENT`), invalid output, or error. It never emits
`OPTIMAL_CERTIFIED` or `INFEASIBLE_PROVEN` for the original objective. The raw
solver status and captured log are reported separately. A heuristic partition
fallback is marked as such and never changes the IP-KONT status.
The wrapper does not configure a solver MIP-gap tolerance or extract a dual
bound; reported MIP gap and dual-bound fields therefore remain null, while any
solver diagnostics remain available in the captured log.

No exact formulation for the original problem is implemented. Although a
bounded exact model over grid coverage and closed routes is conceivable for
tiny cases, route ordering/coverage constraints would be a distinct,
potentially large optimization model. A direct all-pairs route-order model over
the profiler's LIGHT cap of 50,000 estimated anchors would already have up to
2.5 billion directed anchor-pair arcs before coverage and subtour constraints.
No validated sparse exact formulation or bounded proof experiment exists here,
so implementing a purported exact model would not be defensible. Consequently
the local exact optimum and a proof-grade IP-KONT lower bound are unavailable.

`scripts/benchmark.py` keeps `ilp` as an independent benchmark entry and writes
`reference-comparison.json` and `.tsv`. These distinguish the best validated
feasible makespan (with its validation level), best officially validated
candidate, certified optimum, IP-KONT lower bound, and best known upper bound.
Unavailable optimum and lower bound fields remain null. Relative gaps are
reported only for a valid positive lower bound; exact-agreement and difference
fields remain null unless an original-objective optimum is certified. An
incumbent is never labeled optimal.
The KONT metadata also records total/binary/continuous variable counts,
assignment/load constraint counts, the reconstructed assignment's surrogate
objective, and the actual reconstructed tour makespan separately.

Run the deterministic hand-written regression fixtures and local test suite
with:

```sh
./scripts/run_all.sh
```

The hand-written fixtures are under `tests/fixtures`; the runner accepts
`--official` to require `cgshop2027-pyutils`, and reports when official checking
is unavailable. The separate `data/test` collection is ignored benchmark
input, not the unit-test fixture suite. See
[`data/test/README.md`](data/test/README.md) for the provenance limits of its
tracked `master-table.tsv`.

The regression tests use checked-in fixtures and fail if a required fixture is
missing. Assertions remain enabled for all CTest targets in Release builds via
the test-target `-UNDEBUG` option. Run the build and tests from any working
directory by using absolute paths, or from the repository root:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

`run_all.sh` refuses to reuse `build/test-solutions` unless `--overwrite` is
passed.

## Layout

See [docs/architecture.md](docs/architecture.md) for the module boundaries and
algorithm contract. Unit fixtures live under `tests/fixtures`; local benchmark
instances live under `data/test` and `data/instances`. Generated solutions
and plots are intentionally kept out of the source fixture directories.

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
.venv/bin/python scripts/validate.py INSTANCE.instance.json SOLUTION.solution.json
```

To benchmark the configured algorithm list concurrently:

```sh
.venv/bin/python scripts/benchmark.py --instances data/test \
  --algorithms partition,hybrid --jobs 2 --official
```

The benchmark requires at least one `*.instance.json` input and a runnable
solver. It refuses existing output unless `overwrite_existing` is enabled (or
`--overwrite` is passed), validates every selected instance before the batch,
records requested/effective settings and each trial's input, source, executable,
configuration, and seed fingerprints, persists per-trial logs and resource
measurements, and exits nonzero if any run fails. The trial table distinguishes
feasibility from optimality and preserves timeout-with-incumbent outcomes.

Run one isolated algorithm, all registered algorithms on one instance, a
selected matrix, randomized repetitions, or the separate auto-policy
experiment:

```sh
python3 scripts/benchmark.py --instance INSTANCE.instance.json \
  --algorithm partition --output build/benchmarks/partition
python3 scripts/benchmark.py --instance INSTANCE.instance.json \
  --all-algorithms --output build/benchmarks/all
python3 scripts/benchmark.py --instances data/test --instance-ids uid-a,uid-b \
  --algorithms partition,lns --repetitions 5 --jobs 1 \
  --output build/benchmarks/selected
python3 scripts/benchmark.py --instances data/test --auto-policy \
  --official --output build/benchmarks/auto-policy
```

`--algorithm` and `--algorithms` accept registered IDs and aliases, but
`benchmark.tsv` stores canonical registry IDs. Each `instance × algorithm ×
repetition × seed` trial launches a fresh solver process; `auto-policy` is
recorded separately and never substitutes for standalone algorithm trials.
Output contains `benchmark.tsv`, reference comparisons, the effective runtime
configuration, each solution and its solver-side configuration reports, and
separate stdout/stderr logs. Missing measurements and proof references remain
`null`. The official Python verifier is required by `--official` and the
auto-policy experiment.

### Benchmark quality and resource reports

Every benchmark run also produces machine-readable `benchmark.csv` and
`benchmark.jsonl` copies of the raw trial table, `report-metadata.json`,
`benchmark-summary.md`, a best-valid-makespan instance × algorithm matrix,
separate quality, runtime, and memory rankings, deterministic/randomized/policy
summaries, per-instance and per-algorithm Markdown reports, and LIGHT/MEDIUM/
HEAVY/UNKNOWN tier reports. SVG plots show quality versus wall time and sampled
process-tree memory, runtime distributions and timeout counts, and scalability
by estimated anchor count when that feature is recorded. An optimality-gap plot
is emitted only for explicitly certified optima or validated lower bounds with
source/proof metadata.

Quality ranking is lexicographic: feasible-solution rate, geometric mean of
per-instance best-run ratios to the experiment's best validated feasible
makespan, then median valid makespan. Invalid solutions are excluded; timed-out
trials with a validated incumbent remain quality-eligible and still count as
timeouts. For each algorithm, repeated runs are reduced to that algorithm's
best valid result per instance for its per-instance quality ratios, so extra
repetitions do not overweight an instance. Runtime, CPU, memory, timeouts, and
feasible-solution rates use all attempted trials; metric denominators and
missing-measurement handling are recorded in `report-metadata.json`. The
experiment-relative best feasible value is never called an optimum. Certified
optimum comparisons and proof-grade lower-bound gaps are separate fields.
Runtime and memory rankings are not combined into a composite score.
They rank only algorithms with valid solutions by resource use among their
valid trials; all-attempt resource medians, failure counts, and timeout rates
remain visible beside those ranks, so fast invalid exits cannot lead the
resource ranking.

Reports can be regenerated from the raw table without rerunning solvers:

```sh
python3 scripts/summarize_benchmark.py \
  --input build/benchmarks/selected/benchmark.tsv --overwrite
```

The report generator refuses to overwrite existing artifacts unless
`--overwrite` is explicit. `quality-vs-instance-size.svg` and
`runtime-vs-instance-size.svg` use the classifier's estimated anchor count as
an input-size proxy, not as an objective or formal runtime guarantee.

To run every built-in algorithm on every instance, validate each generated
solution, create one PNG figure per instance/algorithm pair, and write both a
detailed run log and a wide comparison table:

```sh
python3 scripts/solve_all.py --instances data/test --timeout 10 \
  --output build/all-results --algorithms partition,ilp,hybrid
```

The output contains `all-results.tsv` (one row per run),
`all-results`'s `master-table.tsv` (instances as rows and algorithms as columns,
with makespans or a per-run limit/failure status), and matching PNG/SVG
snapshots named with instance UID, canonical algorithm ID, repetition, and seed.
The snapshots distinguish target cells, actual swept coverage, overlaps,
uncovered cells, cutter geometry, and closed center trajectories; SVG titles
include validation status, per-tour lengths, and makespan. To render a single
solution as an optional animated SVG, run:

```sh
python3 scripts/visualize.py INSTANCE.json SOLUTION.json --output route.svg \
  --algorithm-id partition --status OFFICIAL_VALID --animate
```

Visualization uses the solver's integer-cell sweep semantics, but its coverage
report is not a substitute for the official solution checker. Each
instance/algorithm run is hard
limited independently by time and memory; use `--memory` to change the
default 2048 MiB cap or `--master-table` to choose another table path. Add
`--official` to run the official validator in addition to the solver's
built-in validation. This option fails fast if `cgshop2027-pyutils` is
unavailable and records officially rejected solutions as failed runs. The
default master table is inside the output directory, and existing output
directories/reports are refused unless `--overwrite` is passed. Use
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
CGSHOP_LOG_LEVEL=debug build/bin/solver \
  -i tests/fixtures/instances/tiny-square.instance.json \
  -o result.solution.json -a hybrid -t 10
```

For result analysis, `scripts/analyze_results.py` writes a TSV containing every
available solution artifact and its makespan. `scripts/ilp_coverage.py` invokes
`gurobi_cl` for a bounded cutter-placement set-cover relaxation; its selected
anchors are a placement-count study and do not provide a route-length lower
bound or claim an optimal closed-tour route.
See [docs/ilp-analysis.md](docs/ilp-analysis.md) for the report definitions and
the distinction between the ILP relaxation and the original routing objective.
