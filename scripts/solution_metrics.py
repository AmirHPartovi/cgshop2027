"""Canonical strict parsing and objective calculation for solution JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _coordinate(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("tour coordinates must be integers")
    return value


def tour_length(tour: Mapping[str, object]) -> int:
    xs = tour.get("x")
    ys = tour.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        raise ValueError("tour x and y must be equally sized arrays")
    points = [(_coordinate(x), _coordinate(y)) for x, y in zip(xs, ys)]
    if not points:
        raise ValueError("tour must contain at least one point")
    if len(points) == 1:
        return 0
    length = 0
    for start, end in zip(points, [*points[1:], points[0]]):
        if start == end:
            raise ValueError("tour has an immediately repeated point")
        if start[0] != end[0] and start[1] != end[1]:
            raise ValueError("tour contains a non-rectilinear edge")
        length += abs(start[0] - end[0]) + abs(start[1] - end[1])
    return length


def makespan(solution: Mapping[str, object]) -> int:
    if not isinstance(solution, Mapping):
        raise ValueError("solution must be a JSON object")
    if solution.get("content_type") != "CGSHOP2027_Solution":
        raise ValueError("unsupported solution content_type")
    if not isinstance(solution.get("instance_uid"), str):
        raise ValueError("solution instance_uid must be a string")
    tours = solution.get("tours")
    if not isinstance(tours, Sequence) or isinstance(tours, (str, bytes)) or not tours:
        raise ValueError("solution must contain at least one tour")
    if any(not isinstance(tour, Mapping) for tour in tours):
        raise ValueError("solution tours must be objects")
    return max(tour_length(tour) for tour in tours)
