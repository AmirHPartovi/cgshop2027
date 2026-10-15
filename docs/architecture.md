# Solver Architecture

The solver is organized into four layers:

- `core/` contains value-based geometry, problem representation, coverage, and
  solution validation.
- `io/` translates the official CG:SHOP 2027 JSON representation to and from
  the core model.
- `algorithms/` contains interchangeable implementations of `BaseAlgorithm`.
  Algorithms return complete solutions and must not bypass `Solution::validate`.
- `utils/` provides logging and timeout primitives shared by all layers.

## Algorithm contract

Every algorithm:

1. receives an immutable `Problem`;
2. returns exactly `number_of_cutters` tours;
3. uses integer axis-aligned tour vertices and implicit closure;
4. checks its timeout inside potentially expensive loops;
5. can be selected from the CLI without changing the I/O layer.

The authoritative feasibility check is the official `pyutils27` verifier. The
C++ validator mirrors its coverage semantics so algorithms can be tested without
Python.

## Reproducible workflow

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./scripts/run_all.sh
```
