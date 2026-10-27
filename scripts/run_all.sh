#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SOLVER="$ROOT/build/bin/solver"
INSTANCE_DIR="$ROOT/tests/fixtures/instances"
OUT_DIR="$ROOT/build/test-solutions"
OVERWRITE=0
REQUIRE_OFFICIAL=0

usage() {
    echo "usage: $0 [--overwrite] [--official]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --overwrite) OVERWRITE=1 ;;
        --official) REQUIRE_OFFICIAL=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage; echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v cmake >/dev/null 2>&1 || {
    echo "error: cmake is required to build the solver" >&2
    exit 1
}
command -v ctest >/dev/null 2>&1 || {
    echo "error: ctest is required to run the test suite" >&2
    exit 1
}

if [ ! -f "$ROOT/build/CMakeCache.txt" ] ||
   ! grep -Fq "CMAKE_HOME_DIRECTORY:INTERNAL=$ROOT" "$ROOT/build/CMakeCache.txt"; then
    cmake -S "$ROOT" -B "$ROOT/build" -DCMAKE_BUILD_TYPE=Release
fi
cmake --build "$ROOT/build" --parallel
ctest --test-dir "$ROOT/build" --output-on-failure

if [ ! -d "$INSTANCE_DIR" ]; then
    echo "error: fixture directory does not exist: $INSTANCE_DIR" >&2
    exit 1
fi
set -- "$INSTANCE_DIR"/*.instance.json
if [ ! -f "$1" ]; then
    echo "error: no *.instance.json fixtures found in $INSTANCE_DIR" >&2
    exit 1
fi

OFFICIAL=0
PYTHON=${PYTHON:-python3}
if command -v "$PYTHON" >/dev/null 2>&1 &&
   "$PYTHON" -c "import cgshop2027_pyutils" >/dev/null 2>&1; then
    OFFICIAL=1
elif [ "$REQUIRE_OFFICIAL" -eq 1 ]; then
    echo "error: --official requires Python with cgshop2027_pyutils" >&2
    exit 1
else
    echo "SKIP: official validation unavailable (cgshop2027_pyutils not importable)" >&2
fi

if [ -e "$OUT_DIR" ] && [ "$OVERWRITE" -ne 1 ]; then
    echo "error: output directory already exists: $OUT_DIR (pass --overwrite to reuse)" >&2
    exit 1
fi
if [ ! -x "$SOLVER" ]; then
    echo "error: solver executable not found or not executable: $SOLVER" >&2
    exit 1
fi
mkdir -p "$OUT_DIR"

for instance in "$@"; do
    name=$(basename "$instance" .instance.json)
    output="$OUT_DIR/$name.solution.json"
    "$SOLVER" -i "$instance" -o "$output" --mode heuristic -a partition
    if [ "$OFFICIAL" -eq 1 ]; then
        "$PYTHON" "$ROOT/scripts/validate.py" "$instance" "$output"
    fi
    printf '%s: generated %s\n' "$name" "$output"
done
