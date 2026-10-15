# Architecture evidence and audit findings

## Evidence method

The maps in this directory were built from implementation reads of `main.cpp`,
the CMake target source lists, concrete algorithm `solve` bodies,
`TourConstruction.cpp`, the core geometry/validation code, and every runner or
evaluation script named below. They are source-inspected static maps, not a
claim of an exhaustive compiler-generated call graph.

The local build has `build/compile_commands.json`; `clang++` and `clangd` are
present, but no `clang-query`, `clang-check`, `clang-tidy`, or Graphviz `dot`
was available. A practical filtered AST/call-graph extractor was therefore
not available without adding tooling. Mermaid source graphs are the only graph
artifacts; no graph package was installed. Standard-library calls and
implementation internals are omitted where they do not change the application
call graph.

### Direct and inferred edges

- Solid edges in `function-call-graph.mmd` denote direct calls or known target
  construction as read in source.
- Dashed edges denote fallback / optional external execution paths or a
  dynamic call boundary.
- `main.cpp` constructs concrete algorithm classes in a conditional chain and
  invokes `algorithm->solve(timeout)` through `std::unique_ptr<BaseAlgorithm>`.
  Each concrete `solve` override is therefore an inferred virtual-dispatch
  target; the target set was enumerated from that chain and confirmed against
  CMake's algorithm sources and the class overrides. It is not a runtime trace.
- `HybridSolver` directly constructs and calls each portfolio algorithm. Those
  edges are direct, while each call's own internal helper edges are documented
  in the algorithm inventory.
- Every candidate-specific fallback is visible in the relevant `solve` body;
  exact line-level function evidence is listed below.

## Call-chain evidence by responsibility

| Responsibility | Implementation evidence |
|---|---|
| CLI and option parsing | `src/main.cpp`: `main`, `parseOptions`, `Options`; timeout defaults to `-1`, algorithm defaults to `hybrid`; `local` constructs a partition solution before the virtual call. |
| Algorithm dispatch | `src/main.cpp`: hard-coded if/else chain; no separately declared registry/factory. Aliases and concrete targets in `algorithm-registration-map.md`. |
| Instance read and JSON parse | `src/io/InstanceReader.cpp`: `readInstance`, `resolveInputPath`, `polygon`, `point`; `src/io/Json.h`: `json::parseFile`, `Parser::parse` and recursive parse routines. |
| Input model validation | `InstanceReader::readInstance` enforces required typed fields, exact `CGSHOP2027_Instance`, integer-valued coordinates, and required `inner_boundaries`; `Problem::validate` checks simple orthogonal rings, orientation, valid non-overlapping hole relationships, center placement, positive rasterized area, and positive cutter count. |
| Geometry preprocessing | `src/core/Problem.cpp`: `regionCells`, `cutterCells`, private `raster`/`inside`; `src/algorithms/BaseAlgorithm.cpp::coverageCenters`; `src/algorithms/TourConstruction.cpp::coveringAnchors`. `regionCells()` and `cutterCells()` recompute raster sets; no persistent cache was found. |
| Dormant utility types | `Polyomino`, `GeometryUtils`, `Timer`, `FileUtils`, `MathUtils`, and `Types.h` are present in the source tree/CMake source list or headers, but no application source caller was found for these utilities. `Polyomino` has internal methods for connectivity and cell collections but is not used by the active `Problem`/algorithm path. |
| Common solver contract | `src/algorithms/BaseAlgorithm.h/.cpp`: pure virtual `solve`, route closure, coverage-center building, tour shape checks, closed length/makespan, timeout predicate, base solution assembly. |
| Route construction and shared algorithms | `src/algorithms/TourConstruction.h/.cpp`: `coveringAnchors`, `boustrophedon`, `spanningTreeWalk`, `tspCov`, `splitFrederickson`, `mstc`, `recursiveBisectionTours`, `stripIlpTours`, `columnGenerationTours`, `improveLns`, `makeSolution`, `closedLength`, `timedOut`, `areaLowerBound`. |
| Internal solution validation | `src/io/SolutionReader.cpp::SolutionReader::readSolution` parses strict tour coordinate arrays and calls `Solution::validate`; `Solution::validate` checks exact solution content type and UID, exact cutter count, nonempty tours, rectilinear edges including closure, and `Problem::isCovered`. The coverage implementation sweeps the translated cutter over every integer center on each edge, including stationary one-point tours. `main.cpp` validates before writing. |
| Output | `src/io/SolutionWriter.cpp::SolutionWriter::write` validates against the `Problem`, escapes JSON strings, preserves JSON-typed metadata, checks write errors, and refuses invalid candidates before opening the output file. |
| Official verifier | `scripts/validate.py` calls `read_instance`, `read_solution`, `check_for_errors` from `cgshop2027_pyutils`. `solve_all.py` invokes it only with `--official`; `run_all.sh` invokes it if import succeeds; `run_paper_algorithms.py` tries it when installed; `evaluate_all.py` imports and runs it unconditionally. |
| External solver management | `src/algorithms/IlpAlgorithm.cpp`: `runKont` writes a command script, starts KONT in a separate process group, registers the child for parent-watchdog cleanup, polls `waitpid`, enforces the remaining parent deadline, and captures its exit status/log; `solveWithKont` validates recovered routes before accepting a candidate. |
| Python process/resource management | `scripts/benchmark.py::run_bounded_process_with_metrics` samples aggregate descendant RSS and cumulative CPU with `ps`, kills the process group on timeout/resource-probe failure/limit, and returns exit and resource metadata. `benchmark.py`, `solve_all.py`, `auto_solve.py`, `profile_instances.py`, and the paper-run visualizer use the bounded runner. Benchmark worker exceptions become explicit failed rows. RSS and CPU values are periodic samples, not exact high-water measurements. |
| Tables and plots | `solve_all.py` writes per-run TSV, master TSV, and PNG; `run_paper_algorithms.py` writes summary TSV and calls `visualize.py` for SVG; `evaluate_all.py` writes official validity rows; `benchmark.py` writes best-per-instance TSV and solution copies; `analyze_results.py` parses available artifacts; `visualize.py` writes SVG. |

## Risk register (document-only; no repairs in this phase)

| Finding | Evidence and impact |
|---|---|
| Output overwrite is not uniformly guarded | Phase 1 adds `--overwrite` gates to `run_all.sh`, `benchmark.py`, `solve_all.py`, and `evaluate_all.py`; the `solve_all.py` default master table is now inside its output directory rather than the tracked data directory. `SolutionWriter::write`, `run_paper_algorithms.py`, `analyze_results.py`, and visualization scripts still write fixed/default destinations without an overwrite refusal. |
| Empty input glob handling varies across scripts | Phase 1 makes `run_all.sh`, `benchmark.py`, `solve_all.py`, and `evaluate_all.py` reject missing directories or empty instance sets. `run_paper_algorithms.py` still silently skips absent hard-coded fixture files; its `all()` over no executed rows can return success. |
| Candidate selection may ignore official validation | `scripts/benchmark.py` selects the smallest makespan from solver exit/output alone; the solver's C++ validation is the only precondition. `scripts/analyze_results.py` records parseability and score only. `evaluate_all.py` performs official validation but does not choose a winner. `solve_all.py` only makes official validation a gate with `--official`; otherwise status `ok` means internal C++-validated. |
| Official-evaluation failure reporting varies | Phase 1 makes `evaluate_all.py` return nonzero for invalid candidates or missing corresponding solutions. `run_paper_algorithms.py`'s final exit condition still checks only the `valid_cpp` column, not `official`; official rejection may be reported while exit remains successful. `run_all.sh` explicitly reports when optional official checking is skipped and `--official` makes the dependency mandatory. |
| Some work remains cooperatively non-interruptible | `ExecutionControl` provides monotonic cancellation checkpoints through rasterization, coverage, anchor generation, and major route/search loops. Sorting, JSON parsing, some polygon predicates, and external library calls cannot be interrupted internally; the POSIX process watchdog and runner process-group timeout remain hard backstops. The solver reserves a bounded finalization window and reports a validated partition fallback or retained hybrid incumbent separately from normal completion. |
| Geometry utility functions and Timer are not on the observed solver path | `src/core/GeometryUtils.cpp` defines free `manhattanDistance`, `isAxisAligned`, and `latticeSegment`, but no other source references them; the active path uses `Point::manhattanDistance` and private raster/edge loops. `src/utils/Timer.h` is likewise not referenced by source; algorithm timing uses local steady-clock checks. |
| Resource limits have platform-specific strength | Batch runners treat an unavailable `ps` process-tree probe as an explicit failure and terminate the run. RSS is sampled and can miss short peaks. On platforms with `RLIMIT_AS`, the solver also enforces a per-process address-space limit; macOS relies on the runner's sampled process-tree watchdog. `ilp_coverage.py` uses the central runtime timeout/memory settings and bounded runner for Gurobi. |
| Some legacy scripts do not share every runner control | The main benchmark, full matrix, auto-solver, profiler pilot, paper-run visualization, and IP coverage study enforce bounded process groups and record sampled resource metrics. `run_all.sh` relies on the C++ process watchdog, while `evaluate_all.py` and `differential_validate.py` remain validation utilities without a uniform process-tree memory report; these are not benchmark resource-accounting claims. |
| Internal validation allows degenerate one-point tours | `Solution::validate` rejects empty tours and invalid edges but a one-point tour passes the edge loop; `Problem::isCovered` treats it as a stationary center. `BaseAlgorithm::makeSolution` and `TourConstruction::makeSolution` pad missing groups with `{0,0}`. Those padded tours can be zero-length and provide no coverage; only overall solution coverage can catch whether another route covers all target cells. |
| Route assignment labels overstate distinct strategies | `strip` is a sorted center distribution, `partition` is a serpentine assignment, and several A/B-labelled algorithms wrap a single constructed route or use a simple grouping heuristic. `column-gen` is a budgeted connected-growth routine, not a conventional master/pricing implementation. The legacy `ilp` entry models vertical-column assignment rather than the original routing objective. Details in `algorithm-registration-map.md`. |
| IP-KONT is only a surrogate comparison | The LP assigns fixed vertical anchor columns to cutters and minimizes the maximum sum of proxy column costs. It does not model route ordering or reconstructed closed-tour lengths. KONT optimality is therefore not an optimum proof or lower bound for the original objective. The wrapper now waits for child exit, checks exit/timeout and complete assignment parsing, captures logs, and validates the recovered route. |
| Repeated rasterization can dominate runtime/memory | `Problem::regionCells()` and `cutterCells()` materialize `unordered_set`s on each call. `validate`, `isCovered`, `coverageCenters`, `coveringAnchors`, area reporting, and heuristics invoke them repeatedly; no cache exists. Official inputs are also present at large scale (250 instance files). |
| Objective definitions are centralized; eligibility still depends on validator mode | `closedTourLength` and `solutionMakespan` are the common C++ route objective; Python batch, benchmark, analysis, and visualization tools use `scripts/solution_metrics.py`; `evaluate_all.py` uses the official schema's `max_tour_length`. `benchmark.py` scores only successful solver output (already internally validated); official validation is available separately or through the runner's `--official` option. |
| Negative/non-finite timeout handling is not centralized | CLI parses `-t` via `std::stod` without range or finiteness validation. `-1` means unbounded in most helpers; KONT converts any negative value to 300 seconds. |
| Column-generation seed selection depends on unordered-set iteration | `columnGenerationTours` seeds growth from `unordered_set::begin()`, whose order is not part of the algorithm contract. `improveLns` now uses the configured `mt19937_64` seed for anchor relocations. No explicit parallelism was found. |
| Optional ILP requirements are not declared | CMake optionally finds KONT by a platform-specific path. The separate `ilp_coverage.py` invokes Gurobi and marks oversized inputs skipped; this is a placement-cover relaxation, not the tour objective. |

## Scope and non-changes

The Phase 0 package above was documentation-only. Phase 1 adds deterministic
fixtures and test-harness changes, narrows JSON ignore rules to local benchmark
inputs, and adds safe input/output checks to the four local runner scripts.
No solver algorithm behavior or remote state is changed. The legacy
`data/test/master-table.tsv` remains byte-for-byte preserved.

## Phase 2 validation contract

The local `.venv` contains `cgshop2027_pyutils`; its installed Pydantic schemas
and `SolutionValidator` were inspected directly. The C++ validator implements
the same axis-aligned polygon and cell-sweep semantics and is exercised against
the deterministic fixtures. Official verification remains an explicit
additional check in `scripts/validate.py` / `run_all.sh --official`; scripts do
not claim that an unavailable official package accepted a solution.

The repository's `Point` model uses signed 32-bit coordinates, whereas the
official Python schema uses arbitrary-precision integers. C++ therefore
rejects otherwise schema-valid coordinates outside `int` range rather than
overflowing or truncating them. Also, the C++ reader requires an explicit
content-type field even though the installed Pydantic model supplies its
literal as a default when omitted. These are deliberate safe restrictions;
the official package may accept those inputs while the local solver rejects
them. The JSON reader accepts mathematically integral decimal/exponent forms
such as `1.0`, but rejects fractional coordinates and booleans.

`SolutionReader` preserves non-string `meta` values as validated raw JSON
fragments, while the existing algorithm metadata API continues to write
strings. The C++ coverage checker and official checker agreed on the three
valid regression instances and their generated solutions; malformed,
self-intersecting, overlapping-hole, fractional-coordinate, wrong-content-type,
and nonrectilinear fixtures were rejected by both validation paths.

### Phase 2 commands and results

- Inspected the locally installed package with
  `.venv/bin/python` and `inspect.getsource` for its instance/solution schema,
  parser, `SolutionValidator`, and `check_for_errors`.
- `cmake --build build --parallel`: passed.
- `ctest --test-dir build --output-on-failure`: **4/4 passed**, 0 failed,
  0 skipped (`geometry`, `algorithms`, `io`, `solution_metrics`).
- From `/tmp`, ran
  `PYTHON=<repo>/.venv/bin/python <repo>/scripts/run_all.sh --overwrite
  --official`: all three smoke outputs passed the official verifier.
- `python3 scripts/benchmark.py --instances tests/fixtures/instances
  --output build/phase2-objective-benchmark.tsv --timeout 10 --overwrite`:
  all **45/45** algorithm/instance runs succeeded. The official verifier
  accepted all 45 candidate files, and `solution_metrics.makespan` matched
  the official `max_tour_length` for every candidate.
- `.venv/bin/python scripts/evaluate_all.py --instances
  tests/fixtures/instances --solutions build/test-solutions --output
  build/phase2-official-evaluation.tsv --overwrite`: **3/3** generated smoke
  solutions were officially valid. An initial rerun without `--overwrite`
  correctly refused to replace the existing report.
- `python3 -m py_compile` for the changed Python scripts and objective tests,
  `sh -n scripts/run_all.sh`, and `git diff --check`: passed.
- The legacy result table remains unchanged:
  `data/test/master-table.tsv` SHA-256 is
  `01c0ab7bfa680f92024bcf66f5f63087b985bfb34d9ba280cac9e74a8af71a16`.

The installed Pydantic models have a few permissive defaults/coercions that do
not match the declared JSON Schema constraints: omitted content types receive
defaults, and booleans may coerce to integers. The C++ readers intentionally
require explicit exact content types and reject booleans as coordinates.
Duplicate JSON object keys are also rejected locally rather than accepted with
last-value-wins behavior. The C++ model supports signed 32-bit coordinates
and cutter counts; the official Python models can represent larger integers,
so values outside C++ range are rejected locally. These safe, documented
differences are not acceptance of invalid data.

## Phase 2.2 differential validation

`tests/internal_solution_check.cpp` exposes the production C++ instance and
solution readers as a machine-readable local checker. The new
`scripts/differential_validate.py` generates a solver candidate for each
deterministic instance, mutates candidates to cover invalid input and
geometric edge cases, and compares internal validity/makespan with
`cgshop2027-pyutils`. It requires the official package and both executables;
missing dependencies are a nonzero error, never an official-verification skip.
Every invocation creates a unique directory under `build/test-results/` and
retains the candidate JSON, copied instances, and `report.json`.

The suite checks outside-region trajectories, overlapping multi-cutter
trajectories, turns and implicit closure, swept cutter coverage, wrong UID,
wrong cutter count, non-rectilinear edges, uncovered regions, repeated closing
points, and empty tours. A required-case gate prevents the suite from
reporting success if fixture changes stop exercising any required geometric
scenario.

### Phase 2.2 commands and results

- `cmake --build build --parallel`: passed; built
  `build/bin/internal_solution_check`.
- `ctest --test-dir build --output-on-failure`: **4/4 passed**, 0 failed,
  0 skipped.
- `.venv/bin/python scripts/differential_validate.py`: **3 instances, 30
  candidates, 30 official checks, 30 agreements, 0 mismatches**. Internal and
  official validators each accepted 12 and rejected 18 candidates.
- From `/tmp`, ran the same script by absolute path: **3 instances, 30
  candidates, 30 official checks, 30 agreements, 0 mismatches**.
- `python3 scripts/differential_validate.py` using system Python, where
  `cgshop2027-pyutils` is unavailable: exited **2** with an explicit
  dependency-unavailable error before creating result artifacts.
- `python3 -m py_compile scripts/differential_validate.py` and
  `git diff --check`: passed.

## Commands and checks executed

- `git -C /Users/amirpartovi/Desktop/Codes/cgshop2027 status --short`,
  `git branch --show-current`, and `git rev-parse HEAD`: initial status was
  `M docs/architecture.md`, branch `main`, HEAD
  `7c8c8133f5cdb9600c15b10ed08f3d1bc0786712`.
- `cmake --build build --parallel`: passed.
- `ctest --test-dir build --output-on-failure`: **3/3 passed**, 0 failures,
  0 skipped.
- Generated a fresh solution outside the repository with
  `build/bin/solver -i data/test/fpg73_1k_1s2.instance.json -o
  <temporary>/candidate.solution.json -a partition -t 5`, then ran
  `.venv/bin/python scripts/validate.py data/test/fpg73_1k_1s2.instance.json
  <temporary>/candidate.solution.json`: solver exited 0 and the official
  `cgshop2027_pyutils` verifier accepted it. Temporary output was removed.
- `git diff --check`: passed. All seven new artifacts were checked for a final
  newline and trailing whitespace.
- At the end of Phase 0, the only reported pre-existing modification was
  `docs/architecture.md`. Phase 1/2 changes are listed in their respective
  sections above; the pre-existing documentation edit and tracked clangd
  cache changes were preserved rather than discarded.
