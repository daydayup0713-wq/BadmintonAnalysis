from __future__ import annotations

import math
import statistics
from typing import Sequence

from .contracts import PlayerPoseFrame


COURT_WIDTH_M = 6.1
COURT_LENGTH_M = 13.4
MOVEMENT_VALID_RATIO_THRESHOLD = 0.8


def map_point_to_court(
    point: Sequence[float],
    court_points: Sequence[Sequence[float]],
) -> tuple[float, float]:
    top_y = (court_points[0][1] + court_points[1][1]) / 2
    bottom_y = (court_points[4][1] + court_points[5][1]) / 2
    denominator = max(bottom_y - top_y, 1e-6)
    y_ratio = min(max((point[1] - top_y) / denominator, 0.0), 1.0)
    left_x = court_points[0][0] + (
        court_points[4][0] - court_points[0][0]
    ) * y_ratio
    right_x = court_points[1][0] + (
        court_points[5][0] - court_points[1][0]
    ) * y_ratio
    width = max(right_x - left_x, 1e-6)
    x_ratio = min(max((point[0] - left_x) / width, 0.0), 1.0)
    return x_ratio * COURT_WIDTH_M, y_ratio * COURT_LENGTH_M


def _foot_point(keypoints: list[list[float]]) -> tuple[float, float]:
    left_ankle = keypoints[15]
    right_ankle = keypoints[16]
    return (
        (left_ankle[0] + right_ankle[0]) / 2,
        (left_ankle[1] + right_ankle[1]) / 2,
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _median_smooth(
    points: Sequence[tuple[int, int, float, float]],
    *,
    window: int = 5,
) -> list[tuple[int, int, float, float]]:
    if len(points) < window:
        return list(points)
    radius = window // 2
    smoothed = []
    for index, point in enumerate(points):
        samples = points[
            max(0, index - radius) : min(len(points), index + radius + 1)
        ]
        smoothed.append(
            (
                point[0],
                point[1],
                statistics.median(sample[2] for sample in samples),
                statistics.median(sample[3] for sample in samples),
            )
        )
    return smoothed


def _hampel_limits(
    values: Sequence[float],
    *,
    window: int = 11,
    deviations: float = 3.0,
) -> list[float]:
    radius = window // 2
    limits = []
    for index in range(len(values)):
        samples = values[
            max(0, index - radius) : min(len(values), index + radius + 1)
        ]
        center = statistics.median(samples)
        mad = statistics.median(abs(value - center) for value in samples)
        robust_sigma = 1.4826 * mad
        limits.append(center + deviations * max(robust_sigma, 0.15))
    return limits


def _build_robust_track(
    raw_points: Sequence[tuple[int, int, float, float]],
    *,
    fps: float,
) -> tuple[list[dict[str, float | int | bool]], dict[str, float | int]]:
    smoothed = _median_smooth(raw_points)
    raw_distance = 0.0
    raw_speeds: list[float] = []
    for previous, point in zip(raw_points, raw_points[1:]):
        frame_gap = point[0] - previous[0]
        if frame_gap <= 0:
            continue
        distance = math.hypot(point[2] - previous[2], point[3] - previous[3])
        raw_distance += distance
        raw_speeds.append(distance * fps / frame_gap)

    candidate_speeds: list[float] = []
    for previous, point in zip(smoothed, smoothed[1:]):
        frame_gap = point[0] - previous[0]
        candidate_speeds.append(
            (
                math.hypot(point[2] - previous[2], point[3] - previous[3])
                * fps
                / frame_gap
            )
            if frame_gap > 0
            else 0.0
        )
    limits = _hampel_limits(candidate_speeds)

    track: list[dict[str, float | int | bool]] = []
    accepted = smoothed[0] if smoothed else None
    if accepted is not None:
        track.append(
            {
                "frame": accepted[0],
                "timestamp_us": accepted[1],
                "x_m": round(accepted[2], 3),
                "y_m": round(accepted[3], 3),
                "speed_mps": 0.0,
                "valid": True,
            }
        )
    effective_speeds: list[float] = []
    effective_distance = 0.0
    effective_duration = 0.0
    rejected = 0
    for index, point in enumerate(smoothed[1:]):
        assert accepted is not None
        frame_gap = point[0] - accepted[0]
        speed = 0.0
        distance = 0.0
        valid = frame_gap > 0
        if valid:
            distance = math.hypot(point[2] - accepted[2], point[3] - accepted[3])
            speed = distance * fps / frame_gap
            valid = speed <= limits[index]
        if valid:
            accepted = point
            effective_distance += distance
            effective_duration += frame_gap / fps
            effective_speeds.append(speed)
        else:
            rejected += 1
        track.append(
            {
                "frame": point[0],
                "timestamp_us": point[1],
                "x_m": round(point[2], 3),
                "y_m": round(point[3], 3),
                "speed_mps": round(speed, 3) if valid else 0.0,
                "valid": valid,
            }
        )

    segment_count = max(len(smoothed) - 1, 0)
    valid_count = segment_count - rejected
    return track, {
        "raw_distance_m": round(raw_distance, 2),
        "raw_max_speed_mps": round(max(raw_speeds, default=0.0), 2),
        "effective_distance_m": effective_distance,
        "effective_duration_seconds": effective_duration,
        "effective_speed_p95_mps": _percentile(effective_speeds, 0.95),
        "rejected_segment_count": rejected,
        "valid_segment_count": valid_count,
        "total_segment_count": segment_count,
    }


def _build_recovery_metrics(
    track: Sequence[dict[str, float | int]],
    *,
    fps: float,
    departure_threshold_m: float = 1.25,
    return_threshold_m: float = 0.75,
) -> dict[str, object]:
    if not track:
        return {
            "base_position_m": None,
            "excursion_count": 0,
            "completed_returns": 0,
            "return_rate": 0.0,
            "average_latency_seconds": None,
            "events": [],
        }
    base_x = statistics.median(float(point["x_m"]) for point in track)
    base_y = statistics.median(float(point["y_m"]) for point in track)
    active: dict[str, float | int] | None = None
    events: list[dict[str, float | int]] = []
    excursion_count = 0
    for point in track:
        distance = math.hypot(
            float(point["x_m"]) - base_x,
            float(point["y_m"]) - base_y,
        )
        if active is None and distance >= departure_threshold_m:
            excursion_count += 1
            active = {
                "departure_frame": int(point["frame"]),
                "max_distance_m": distance,
            }
            continue
        if active is None:
            continue
        active["max_distance_m"] = max(
            float(active["max_distance_m"]),
            distance,
        )
        if distance <= return_threshold_m:
            departure_frame = int(active["departure_frame"])
            return_frame = int(point["frame"])
            events.append(
                {
                    "departure_frame": departure_frame,
                    "return_frame": return_frame,
                    "latency_seconds": round(
                        (return_frame - departure_frame) / fps,
                        3,
                    ),
                    "max_distance_m": round(
                        float(active["max_distance_m"]),
                        3,
                    ),
                }
            )
            active = None
    latencies = [float(event["latency_seconds"]) for event in events]
    return {
        "base_position_m": {
            "x_m": round(base_x, 3),
            "y_m": round(base_y, 3),
        },
        "excursion_count": excursion_count,
        "completed_returns": len(events),
        "return_rate": round(
            len(events) / excursion_count if excursion_count else 0.0,
            3,
        ),
        "average_latency_seconds": (
            round(sum(latencies) / len(latencies), 3)
            if latencies
            else None
        ),
        "events": events,
    }


def build_player_movement_metrics(
    pose_frames: Sequence[PlayerPoseFrame],
    court_points: Sequence[Sequence[float]],
    *,
    fps: float,
) -> dict[str, object]:
    players: dict[str, dict[str, object]] = {}
    for side in ("top", "bottom"):
        raw_points: list[tuple[int, int, float, float]] = []
        heatmap = [[0 for _ in range(3)] for _ in range(3)]
        for pose in pose_frames:
            keypoints = (
                pose.top_keypoints if side == "top" else pose.bottom_keypoints
            )
            if keypoints is None:
                continue
            x_m, y_m = map_point_to_court(_foot_point(keypoints), court_points)
            x_zone = min(int(x_m / (COURT_WIDTH_M / 3)), 2)
            y_zone = min(int(y_m / (COURT_LENGTH_M / 3)), 2)
            heatmap[y_zone][x_zone] += 1
            raw_points.append(
                (pose.frame, pose.timestamp_us, x_m, y_m)
            )
        track, diagnostics = _build_robust_track(raw_points, fps=fps)
        segment_count = int(diagnostics["total_segment_count"])
        valid_ratio = (
            int(diagnostics["valid_segment_count"]) / segment_count
            if segment_count
            else 0.0
        )
        has_enough_evidence = valid_ratio >= MOVEMENT_VALID_RATIO_THRESHOLD
        effective_duration = float(
            diagnostics["effective_duration_seconds"]
        )
        effective_distance = float(diagnostics["effective_distance_m"])
        valid_track = [point for point in track if point["valid"]]
        players[side] = {
            "track": track,
            "distance_m": (
                round(effective_distance, 2) if has_enough_evidence else None
            ),
            "average_speed_mps": (
                round(effective_distance / effective_duration, 2)
                if has_enough_evidence and effective_duration > 0
                else None
            ),
            "max_effective_speed_mps": (
                round(float(diagnostics["effective_speed_p95_mps"]), 2)
                if has_enough_evidence
                else None
            ),
            "trajectory_valid_ratio": round(valid_ratio, 3),
            "validation_status": "missing_evidence",
            "quality_label": "2D候选",
            "heatmap": heatmap,
            "recovery": _build_recovery_metrics(valid_track, fps=fps),
            "diagnostics": diagnostics,
        }
    return players
