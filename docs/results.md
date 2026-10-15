# Benchmark Results

The five hand-made fixtures in `data/test` are used as the regression set.
`scripts/run_all.sh` generates and self-validates each output with the C++
domain validator. The official Python validator is invoked automatically when
installed in the environment.

| Fixture | Algorithm | Result |
|---|---|---|
| tiny1--tiny5 | partition | feasible; see generated solution files |

## Complete comparison run

`scripts/solve_all.py` is the reproducible batch entry point for the full
instance/algorithm matrix:

```sh
python3 scripts/solve_all.py --instances data/test --timeout 10 \
  --output build/all-results
```

It writes one validated solution and one PNG route figure for every successful
pair. `all-results.tsv` contains status, validation, makespan, runtime,
resource limits, and artifact paths. `master-table.tsv` is the wide
comparison table with one instance per row and one algorithm per column; by
default it is written to `data/test/master-table.tsv`. Every pair has an
independent time and memory limit. Pairs that exceed a limit are skipped and
recorded as `TIME_LIMIT` or `MEMORY_LIMIT`, so they do not stop later runs.
