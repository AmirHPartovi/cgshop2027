# Repository map and baseline

## Snapshot

- Repository: local `cgshop2027` checkout
- Branch: `main`
- HEAD at audit: `7c8c8133f5cdb9600c15b10ed08f3d1bc0786712`
- Initial working tree: `docs/architecture.md` was already modified. That user/session change was preserved.
- Local ignored benchmark inputs: 250 files in `data/instances/` and 73 files in `data/test/`; neither input collection is tracked.
- Checked-in regression fixtures: small hand-written cases under `tests/fixtures/`.
- Existing generated comparison table: `data/test/master-table.tsv` is tracked.

## Layout

| Path | Purpose |
|---|---|
| `CMakeLists.txt` | C++17 build, warning policy, `cgshop_core`, CLI executable, optional KONT discovery, tests |
| `src/main.cpp` | CLI entry point, option parsing, hard-coded solver selection, final validation and output |
| `src/core/` | Point and geometry types, polygon/raster region model, coverage, solution validity |
| `src/io/` | Embedded JSON parser, instance and solution readers, validated solution writer, file helpers |
| `src/algorithms/` | Abstract algorithm contract, 15 CLI selections, shared route and improvement helpers |
| `src/utils/` | Logger and timer utility |
| `tests/` | Three C++ CTest executables plus Python objective tests when an interpreter is available |
| `scripts/` | Local runners, benchmarks, official verification, result analysis, visualizations, placement-cover study |
| `data/instances/` | Local ignored instance collection, separate from hand-written tests |
| `data/test/` | 73 local ignored benchmark inputs, tracked legacy `master-table.tsv`, provenance documented in `data/test/README.md` |
| `docs/` | Project documentation; `docs/architecture.md` existed before this artifact package and was preserved |
| `.clang-format`, `.editorconfig` | LLVM-derived C++ formatting and UTF-8/LF/4-space defaults; shell scripts use 2-space indentation |
| `.gitignore` | Ignores `build/`, local `.venv/` and `/.cache/`, benchmark JSON inputs under `data/instances/` and `data/test/`, and Python `__pycache__` directories |
| `build/` | Existing local CMake cache, compile database, solver and test binaries; ignored by Git |
| `.venv/` | Local Python environment; `requirements-cgshop.txt` pins the official verifier dependency |
| `.cache/clangd/` | Local clangd indexes; not application source |

No general application `requirements.txt`, `pyproject.toml`, `conanfile`, or vcpkg manifest is present in the tracked tree; `requirements-cgshop.txt` is scoped to the official competition utilities.

## Build targets and external dependencies

`CMakeLists.txt` defines:

- `cgshop_core`: core, I/O, utility, and all algorithm translation units.
- `solver`: `src/main.cpp`, linked to `cgshop_core`, output at `build/bin/solver`.
- CTest targets `test_geometry`, `test_algorithms`, and `test_io` (registered as `geometry`, `algorithms`, `io`).

The project requires C++17 and enables `-Wall -Wextra -Wpedantic -Werror` (or `/W4 /WX` on MSVC). It has no required third-party C++ library. CMake optionally finds `kont_cmd` under `/Applications/kont72/bin` and defines `CGSHOP_KONT_CMD` for the KONT-backed `ilp` path. The observed local build cache names `/Applications/kont72/bin/kont_cmd`; this is configure-time state, not proof that the external solver can solve or has a valid license.

Python scripts otherwise use the standard library. `cgshop2027_pyutils` is an optional official validator dependency used by `validate.py`, `evaluate_all.py`, and selected optional paths. `scripts/ilp_coverage.py` invokes the external `gurobi_cl` executable. Neither Python package is declared in a project manifest. `CGSHOP_LOG_LEVEL` is read by `Logger` (`debug`, `info`, `warning`/`warn`, or `error`); algorithm and timeout selection are CLI options rather than shared settings-file configuration.

Graphviz `dot`, `clang-query`, `clang-check`, and `clang-tidy` were not available during the audit. Mermaid source maps are provided without adding a graph-rendering dependency. A compilation database exists, but a practical C++ call-graph AST extractor was not available; the call map is source-inspected and labels virtual dispatch separately.

## Local workflows

- Build/test: `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel && ctest --test-dir build --output-on-failure`
- Small-fixture local runner: `scripts/run_all.sh`
- Multi-algorithm solver benchmark: `scripts/benchmark.py`
- Resource-limited all-pairs evaluation and plots: `scripts/solve_all.py`
- Official evaluation of candidate artifacts: `scripts/evaluate_all.py`
- Selected paper-algorithm runs: `scripts/run_paper_algorithms.py`
- Parse existing solution artifacts: `scripts/analyze_results.py`
- Standalone SVG rendering: `scripts/visualize.py`
- Bounded Gurobi set-cover study: `scripts/ilp_coverage.py`

## Audit baseline status

The configured CMake build completed successfully. CTest reported **3 passed, 0 failed, 0 skipped** (`geometry`, `algorithms`, `io`). The build/test run did not change application source or the user-modified `docs/architecture.md`.
