# Deterministic regression fixtures

These tiny hand-written fixtures are checked in for CTest and `scripts/run_all.sh`.
They are separate from the ignored benchmark inputs in `data/test` and
`data/instances`.

| Path | Coverage |
|---|---|
| `instances/tiny-single.instance.json` | One raster cell, one cutter; paired stationary solution has one point and makespan 0 |
| `instances/tiny-square.instance.json` | Four raster cells; paired solution visits all four with known closed makespan 4 |
| `instances/tiny-hole-multicutter.instance.json` | 3x3 region with one-cell hole and two cutters |
| `invalid/invalid-content-type.json` | Valid JSON with invalid instance content type |
| `invalid/malformed.json` | Truncated JSON parser failure |
| `invalid/missing-inner-boundaries.instance.json` | Required hole-list field is absent |
| `invalid/self-intersecting.instance.json` | Orthogonal outer ring intersects itself |
| `invalid/overlapping-holes.instance.json` | Hole boundaries overlap |
| `invalid/fractional-coordinate.instance.json` | Non-integer boundary coordinate |
| `solutions/invalid-nonrectilinear.solution.json` | Deliberately invalid diagonal closing edge |

The valid solution fixtures exercise a stationary one-point tour and a known
closed makespan of 4. `test_io` also checks UID/cutter-count mismatches, empty
and uncovered tours, repeated closing points, invalid coordinates, metadata
and UID escaping, and the absent
`instances/does-not-exist.instance.json` path. `test_solution_metrics.py`
tests the canonical Python objective helper. No test depends on the large
local benchmark inputs being present.

## Differential verification

After building the project and installing `cgshop2027-pyutils` in `.venv`, run
the differential suite from the repository root:

```sh
.venv/bin/python scripts/differential_validate.py
```

The script also supports invocation by absolute path from another working
directory.

The script generates solver candidates and invalid variants, then checks every
candidate with both `internal_solution_check` and the official verifier.
It exits nonzero if the official dependency or either executable is missing,
if any official check is skipped, or if validity/objective results disagree.
Each invocation creates a unique directory under `build/test-results/` and
never replaces prior output; `report.json` includes per-case results and
official-verification counts. Candidate JSON is retained alongside the report
to make mismatches reproducible.
