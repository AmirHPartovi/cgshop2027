#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SOLVER="$ROOT/build/bin/solver"
OUT_DIR="$ROOT/build/test-solutions"
mkdir -p "$OUT_DIR"

if [ ! -x "$SOLVER" ] ||
   [ ! -f "$ROOT/build/CMakeCache.txt" ] ||
   ! grep -Fq "CMAKE_HOME_DIRECTORY:INTERNAL=$ROOT" "$ROOT/build/CMakeCache.txt"; then
    cmake -S "$ROOT" -B "$ROOT/build" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$ROOT/build" --parallel
fi

INSTANCE_DIR="$ROOT/data/test"
if [ ! -d "$INSTANCE_DIR" ]; then
    INSTANCE_DIR="$ROOT/data"
fi
for instance in "$INSTANCE_DIR"/*.json; do
    name=$(basename "$instance" .json)
    output="$OUT_DIR/$name.solution.json"
    "$SOLVER" -i "$instance" -o "$output" -a partition
    if command -v python3 >/dev/null 2>&1 &&
       python3 -c "import cgshop2027_pyutils" >/dev/null 2>&1; then
        python3 "$ROOT/scripts/validate.py" "$instance" "$output"
    fi
    printf '%s: generated %s\n' "$name" "$output"
done
