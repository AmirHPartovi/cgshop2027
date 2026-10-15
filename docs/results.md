# Benchmark Results

The deterministic hand-written regression fixtures live in
`tests/fixtures/instances` and are separate from the ignored local benchmark
inputs under `data/test`. `scripts/run_all.sh` runs CTest and generates a
solution for each valid smoke-test fixture with the C++ domain validator.
Official verification is performed when `cgshop2027_pyutils` is available, or
required explicitly with `--official`.

Makespan is the maximum of each tour's Manhattan length with its implicit
last-to-first edge included. C++ routes use the shared `closedTourLength` /
`solutionMakespan` functions; Python reports use
`scripts/solution_metrics.py`, while official evaluation reads the official
`max_tour_length` property.

`data/test/master-table.tsv` is a legacy comparison artifact preserved from
the repository's initial commit. Its generating command, date, environment,
and verification status were not recorded; it is not ground truth.

## Complete comparison run

`scripts/solve_all.py` is the reproducible batch entry point for the full
instance/algorithm matrix:

```sh
python3 scripts/solve_all.py --instances data/test --timeout 10 \
  --output build/all-results
```

It writes one validated solution and matching PNG/SVG snapshots for every
successful pair, using instance UID, canonical algorithm ID, repetition, and
seed in the filenames. The cell overlays distinguish target region, swept
coverage, uncovered cells, and cutter overlap; the SVG also shows cutter
geometry, closed center trajectories, per-tour lengths, makespan, and
validation status. A visualization's coverage check mirrors the solver's
integer-cell sweep semantics and is not a substitute for official validation.
`all-results.tsv` contains status, validation, makespan, runtime,
resource limits, sampled process-tree wall/CPU/RSS measurements, sample counts,
termination reasons, and artifact paths. RSS and CPU are periodic `ps`
observations and may miss peaks between samples; they are not exact process
high-water measurements. On platforms that support it, the C++ solver also
applies a per-process `RLIMIT_AS`; the runner's sampled RSS watchdog covers the
whole process tree. `master-table.tsv` is the wide
comparison table with one instance per row and one algorithm per column; by
default it is written to the selected output directory. Every pair has an
independent time and memory limit. Pairs that exceed a limit are recorded as
`TIME_LIMIT` or `MEMORY_LIMIT`, so they do not stop later runs. Existing output
directories and reports require the explicit `--overwrite` option.

## IP-KONT and comparison semantics

The `ilp` benchmark entry invokes the KONT vertical-column assignment
surrogate when enabled. It is not an exact model of the original closed-tour
makespan objective: it assigns each fixed x-column to one cutter and minimizes
the maximum sum of proxy costs `2 * vertical_span + 2`. Reconstructed routes
are feasible candidates only after validation; neither this proxy value nor
KONT's `OPTIMAL` status is a proof-grade lower bound or optimum for routing.
The legacy algorithm name is retained for compatibility.

`scripts/benchmark.py` writes `reference-comparison.json` and
`reference-comparison.tsv` alongside `benchmark.tsv`. A row records the best
validated feasible makespan and its validation level separately from the best
officially validated result. Certified optimum and IP-KONT lower-bound fields
are null until a valid proof source exists. Accordingly, relative gap,
exact-agreement, additive-difference, and relative-difference fields are null.
IP-KONT status, recognized raw status, termination reason, solver runtime,
process exit code, model dimensions, exactness scope, and captured solver log
are preserved. No MIP-gap tolerance or dual-bound extraction is implemented,
so those fields are null. When a valid assignment is recovered, its modeled
surrogate objective and reconstructed-tour makespan are recorded as different
quantities. A surrogate incumbent is `FEASIBLE_NOT_PROVEN`, even if KONT
reports `OPTIMAL` for the surrogate. A timeout without an extracted incumbent is
`TIME_LIMIT_NO_INCUMBENT`; a solver-reported time limit with a recovered
candidate is `TIME_LIMIT_WITH_INCUMBENT`. Fallback heuristic results remain
separate.

## Independent benchmark rankings

`scripts/benchmark.py` also persists raw `benchmark.csv` and
`benchmark.jsonl` records and emits a locally reproducible report bundle from
`benchmark.tsv`. The bundle includes the overall summary, quality/runtime/
memory rankings, instance × algorithm matrix, per-instance and per-algorithm
reports, tier reports, budget comparisons, and SVG plots. Regenerate the
reports without invoking a solver with:

```sh
python3 scripts/summarize_benchmark.py \
  --input build/benchmarks/selected/benchmark.tsv
```

Quality ratios use the best validated feasible makespan for that instance
within the experiment as the default reference; this is a `best_known_feasible`
value, not an optimum. Certified-optimum and validated-lower-bound gaps are
included only when explicit proof, validation, objective-match, and source
metadata are present. Invalid outputs do not contribute a makespan or ratio.
Validated timeout incumbents remain quality-eligible but count toward timeout
rates. Per-instance ratios reduce repeated trials to each algorithm's best
valid run, while reliability and resource metrics use every attempted trial.
Runtime and memory rankings are separate and order algorithms with valid
solutions by resource use on valid trials; all-attempt resource metrics and
failures remain visible. The generated metadata records metric denominators
and missing-value policy. The report generator refuses existing artifacts
unless `--overwrite` is supplied.
