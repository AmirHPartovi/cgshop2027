# Official CGSHOP 2027 Python utilities

## Selected dependency

The local `.venv` uses the latest official PyPI release available at the time
of this audit, pinned in `requirements-cgshop.txt`:

| Property | Value |
| --- | --- |
| Distribution | `cgshop2027-pyutils` |
| Version | `0.2.0` |
| Source | Official PyPI release |
| Upstream repository | <https://github.com/CG-SHOP/pyutils27> |
| Upstream ref | `v0.2.0` |
| Resolved upstream commit | `80ce533adc3a09cd90e3bf74666f26a85a8bc367` |
| Python used | `3.13.0` (`.venv/bin/python`) |
| Install command | `.venv/bin/python -m pip install --upgrade -r requirements-cgshop.txt` |

At verification time, PyPI reported `0.2.0` as latest and required Python
`>=3.10`. A live `git ls-remote` resolved both upstream `HEAD` and `main` to
the same SHA as tag `v0.2.0`; therefore, no newer unreleased commit needed to
be pinned. The official wheel SHA-256 was
`fc7c9bbcf6a5361fd390f875afb182adf594c3c0cd7f9efe632cb6c5309911cd`.
No unrelated project packages were intentionally upgraded.

## Verified public API

The API below was inspected from the installed `0.2.0` package:

- `cgshop2027_pyutils.io.read_instance(file)` and
  `read_solution(file)` accept a path or file-like object.
- `cgshop2027_pyutils.verify.check_for_errors(instance, solution)` returns a
  list of validation messages; `SolutionValidator(instance)` exposes
  `check_for_errors(solution)`, `swept_cells(solution)`, and
  `uncovered_cells(solution)`.
- `CGSHOP2027Solution` and `CutterTour` are exported from
  `cgshop2027_pyutils.schemas`; the solution model supports Pydantic
  `model_validate_json`, `model_dump_json`, and `max_tour_length`.
- `cgshop2027_pyutils.zip.ZipWriter(path)` supports `add_solution(solution)`
  and context-manager use. The supported solution archive reader is
  `ZipSolutionIterator(path_or_file)`, which is iterated directly and manages
  its own archive file while iterating (it is not a context manager).
  `ZipReaderError` and `BadSolutionFile` are the reader exceptions.
- `cgshop2027_pyutils.visualize.create_solution_plot(instance, solution, *,
  coverage="flat"|"shaded", bare=False)` returns a Matplotlib figure.
  `create_solution_animation(instance, solution, step=None, max_frames=300,
  interval=120, *, coverage="flat"|"shaded", bare=False)` returns a
  `FuncAnimation`.

These APIs are exercised using only the repository's `tiny-square` fixture by
`tests/test_pyutils_compat.py`. The test verifies the solution, round-trips it
through the schema and official ZIP writer/reader, and renders a PNG through
the official plotting API.

## Local setup and verification

Install the pinned package into the existing environment:

```sh
.venv/bin/python -m pip install --upgrade -r requirements-cgshop.txt
```

Configure CTest to use that same interpreter:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python"
```

The package's declared Python floor is 3.10, so the repository's system Python
3.9 is not a supported interpreter for this dependency. The built C++ solver
and internal checker remain separate executables and are not changed by this
dependency update.
