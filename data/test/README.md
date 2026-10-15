# Local benchmark inputs and legacy table

This directory contains 73 local `*.instance.json` benchmark inputs. They are
ignored by Git via the scoped `/data/test/*.instance.json` rule and are not the
checked-in unit-test fixtures; small deterministic test fixtures are kept in
`tests/fixtures`.

`master-table.tsv` is tracked and predates this audit. Git history shows that it
was already present in the initial commit (`7c8c8133f5cdb9600c15b10ed08f3d1bc0786712`),
but no generating command, run date, software environment, or verification
metadata is recorded. The table contains per-algorithm makespans and
`TIME_LIMIT` values, so it is best classified as a **legacy experiment result
table of unknown provenance**. It is not a reference dataset, official result,
or verified ground truth. Preserve it unless a user explicitly requests its
replacement.

The preserved file's SHA-256 at the Phase 1 audit is
`01c0ab7bfa680f92024bcf66f5f63087b985bfb34d9ba280cac9e74a8af71a16`.

`scripts/solve_all.py` now writes its default master table to the selected
result output directory. It refuses an existing result directory/report
unless `--overwrite` is explicitly supplied.
