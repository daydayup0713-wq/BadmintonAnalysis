from __future__ import annotations

from statistics import median
from typing import Sequence


def _turning_points(
    values: Sequence[float],
    *,
    threshold: float,
    window: int,
) -> list[int]:
    points: list[int] = []
    for index in range(window, len(values) - window):
        left_delta = values[index] - values[index - 1]
        right_delta = values[index] - values[index + 1]
        if left_delta * right_delta < 0:
            continue
        left_slope = median(
            values[offset] - values[offset - 1]
            for offset in range(index - window + 1, index + 1)
        )
        right_slope = median(
            values[offset + 1] - values[offset]
            for offset in range(index, index + window)
        )
        if max(abs(left_slope), abs(right_slope)) > threshold:
            points.append(index)
    return points


def _merge_candidates(
    first: Sequence[int],
    second: Sequence[int],
    *,
    closeness: int,
) -> list[int]:
    merged: list[int] = []
    for frame in sorted([*first, *second]):
        if not merged or frame - merged[-1] > closeness:
            merged.append(frame)
    return merged


def detect_trajectory_turns(
    x: Sequence[float],
    y: Sequence[float],
    *,
    threshold: float = 10,
    window: int = 7,
    closeness: int = 15,
) -> list[int]:
    if len(x) != len(y):
        raise ValueError("x and y trajectories must have the same length")
    if window < 1:
        raise ValueError("window must be positive")
    return _merge_candidates(
        _turning_points(x, threshold=threshold, window=window),
        _turning_points(y, threshold=threshold, window=window),
        closeness=closeness,
    )
