#!/usr/bin/env python3
"""Validate a solution with the official pyutils27 package when installed."""

import sys

from cgshop2027_pyutils.io import read_instance, read_solution
from cgshop2027_pyutils.verify import check_for_errors


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate.py INSTANCE SOLUTION", file=sys.stderr)
        return 2
    errors = check_for_errors(read_instance(sys.argv[1]), read_solution(sys.argv[2]))
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
