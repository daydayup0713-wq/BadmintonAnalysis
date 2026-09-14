from __future__ import annotations

import math
import statistics
from typing import Sequence

from .contracts import PlayerPoseFrame
from .metrics import COURT_LENGTH_M, COURT_WIDTH_M, map_point_to_court


def joint_angle(
    first: Sequence[float],
    vertex: Sequence[float],
    third: Sequence[float],
) -> float:
    vector_a = (first[0] - vertex[0], first[1] - vertex[1])
    vector_b = (third[0] - vertex[0], third[1] - vertex[1])
    length_a = math.hypot(*vector_a)
    length_b = math.hypot(*vector_b)
    if length_a == 0 or length_b == 0:
        return 0.0
    cosine = (
        vector_a[0] * vector_b[0] + vector_a[1] * vector_b[1]
    ) / (length_a * length_b)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine))))


def wrist_acceleration(
    points: Sequence[tuple[int, float, float]],
    *,
    fps: float,
) -> list[dict[str, float | int]]:
    if fps <= 0:
        raise ValueError("fps must be positive")
    velocities: list[tuple[int, float, float]] = []
    for index in range(1, len(points)):
        frame_gap = points[index][0] - points[index - 1][0]
        if frame_gap <= 0:
            continue
        dt = frame_gap / fps
        velocities.append(
            (
                points[index][0],
                (points[index][1] - points[index - 1][1]) / dt,
                (points[index][2] - points[index - 1][2]) / dt,
            )
        )
    result = []
    for index in range(1, len(velocities)):
        frame_gap = velocities[index][0] - velocities[index - 1][0]
        if frame_gap <= 0:
            continue
        dt = frame_gap / fps
        ax = (velocities[index][1] - velocities[index - 1][1]) / dt
        ay = (velocities[index][2] - velocities[index - 1][2]) / dt
        result.append(
            {
                "frame": velocities[index][0],
                "acceleration_px_s2": math.hypot(ax, ay),
            }
        )
    return result


def _midpoint(
    first: Sequence[float],
    second: Sequence[float],
) -> tuple[float, float]:
    return (
        (first[0] + second[0]) / 2,
        (first[1] + second[1]) / 2,
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


def _smooth_wrist_track(
    points: Sequence[tuple[int, float, float, float]],
    *,
    window: int = 5,
) -> list[tuple[int, float, float, float]]:
    if len(points) < window:
        return list(points)
    radius = window // 2
    result = []
    for index, point in enumerate(points):
        samples = points[
            max(0, index - radius) : min(len(points), index + radius + 1)
        ]
        result.append(
            (
                point[0],
                statistics.median(sample[1] for sample in samples),
                statistics.median(sample[2] for sample in samples),
                statistics.median(sample[3] for sample in samples),
            )
        )
    return result


def _normalized_wrist_speeds(
    points: Sequence[tuple[int, float, float, float]],
    *,
    fps: float,
) -> list[tuple[int, float]]:
    smoothed = _smooth_wrist_track(points)
    speeds = []
    for previous, point in zip(smoothed, smoothed[1:]):
        frame_gap = point[0] - previous[0]
        if frame_gap <= 0:
            continue
        distance = math.hypot(point[1] - previous[1], point[2] - previous[2])
        speeds.append(
            (
                point[0],
                distance * fps / frame_gap / max(point[3], 1.0),
            )
        )
    return speeds


def build_swing_metrics(
    frames: Sequence[PlayerPoseFrame],
    hits: Sequence[dict[str, object]],
    court_points: Sequence[Sequence[float]],
    *,
    fps: float,
    duration_seconds: float,
) -> dict[str, object]:
    if fps <= 0:
        raise ValueError("fps must be positive")
    wrist_speeds: dict[str, list[tuple[int, float]]] = {}
    foot_positions: dict[str, dict[int, tuple[float, float]]] = {}
    for side in ("top", "bottom"):
        left: list[tuple[int, float, float, float]] = []
        right: list[tuple[int, float, float, float]] = []
        foot_positions[side] = {}
        for frame in frames:
            keypoints = (
                frame.top_keypoints if side == "top" else frame.bottom_keypoints
            )
            if keypoints is None:
                continue
            shoulder_width = max(math.dist(keypoints[5], keypoints[6]), 1.0)
            left.append(
                (
                    frame.frame,
                    keypoints[9][0],
                    keypoints[9][1],
                    shoulder_width,
                )
            )
            right.append(
                (
                    frame.frame,
                    keypoints[10][0],
                    keypoints[10][1],
                    shoulder_width,
                )
            )
            foot = _midpoint(keypoints[15], keypoints[16])
            foot_positions[side][frame.frame] = map_point_to_court(
                foot,
                court_points,
            )
        wrist_speeds[side] = [
            *_normalized_wrist_speeds(left, fps=fps),
            *_normalized_wrist_speeds(right, fps=fps),
        ]

    raw_events: list[dict[str, object]] = []
    for hit in hits:
        side = str(hit.get("player", "unknown"))
        if side not in {"top", "bottom"}:
            continue
        hit_frame = int(hit["frame"])
        nearby = [
            speed
            for frame, speed in wrist_speeds[side]
            if abs(frame - hit_frame) <= 3
        ]
        position = foot_positions[side].get(hit_frame)
        if position is None:
            candidates = [
                (abs(frame - hit_frame), point)
                for frame, point in foot_positions[side].items()
                if abs(frame - hit_frame) <= 3
            ]
            position = min(candidates, default=(0, (0.0, 0.0)))[1]
        raw_events.append(
            {
                "frame": hit_frame,
                "timestamp_us": int(hit.get("timestamp_us", 0)),
                "player": side,
                "confidence": float(hit.get("confidence", 0.0)),
                "raw_normalized_wrist_speed": max(nearby, default=0.0),
                "x_m": position[0],
                "y_m": position[1],
            }
        )

    raw_values = [
        float(event["raw_normalized_wrist_speed"]) for event in raw_events
    ]
    lower = _percentile(raw_values, 0.1)
    upper = _percentile(raw_values, 0.9)
    scale = max(upper - lower, 1e-9)
    for event in raw_events:
        raw_value = float(event["raw_normalized_wrist_speed"])
        event["intensity_index"] = round(
            min(max((raw_value - lower) / scale * 100, 0.0), 100.0)
        )
        event["x_ratio"] = min(max(float(event["x_m"]) / COURT_WIDTH_M, 0), 1)
        event["y_ratio"] = min(max(float(event["y_m"]) / COURT_LENGTH_M, 0), 1)

    timeline_bins = max(1, math.ceil(duration_seconds / 0.5))
    result: dict[str, object] = {}
    for side in ("top", "bottom"):
        events = [event for event in raw_events if event["player"] == side]
        spatial_values = [[[] for _ in range(3)] for _ in range(6)]
        timeline_values = [[] for _ in range(timeline_bins)]
        timeline_low_confidence = [0 for _ in range(timeline_bins)]
        for event in events:
            row = min(int(float(event["y_ratio"]) * 6), 5)
            column = min(int(float(event["x_ratio"]) * 3), 2)
            spatial_values[row][column].append(
                int(event["intensity_index"])
            )
            bin_index = min(
                int(int(event["timestamp_us"]) / 1_000_000 / 0.5),
                timeline_bins - 1,
            )
            timeline_values[bin_index].append(
                int(event["intensity_index"])
            )
            if float(event["confidence"]) < 0.7:
                timeline_low_confidence[bin_index] += 1
        result[side] = {
            "hit_count": len(events),
            "low_confidence_hit_count": sum(
                float(event["confidence"]) < 0.7 for event in events
            ),
            "average_intensity_index": (
                round(
                    statistics.mean(
                        int(event["intensity_index"]) for event in events
                    )
                )
                if events
                else None
            ),
            "peak_intensity_index": max(
                (int(event["intensity_index"]) for event in events),
                default=None,
            ),
            "events": events,
            "spatial_heatmap": [
                [
                    round(statistics.mean(values)) if values else 0
                    for values in row
                ]
                for row in spatial_values
            ],
            "timeline_heatmap": [
                {
                    "start_seconds": round(index * 0.5, 3),
                    "end_seconds": round(
                        min((index + 1) * 0.5, duration_seconds),
                        3,
                    ),
                    "intensity_index": (
                        round(statistics.mean(values)) if values else 0
                    ),
                    "event_count": len(values),
                    "low_confidence_count": timeline_low_confidence[index],
                }
                for index, values in enumerate(timeline_values)
            ],
            "validation_status": "missing_evidence",
            "quality_label": "2D相对指数",
        }
    result["definition"] = {
        "window_frames": 3,
        "normalization": "shoulder_width",
        "scale": "per_video_p10_p90",
        "physical_force": False,
    }
    return result


def analyze_pose_biomechanics(
    frames: Sequence[PlayerPoseFrame],
    *,
    fps: float,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for side in ("top", "bottom"):
        samples = []
        left_wrist: list[tuple[int, float, float]] = []
        right_wrist: list[tuple[int, float, float]] = []
        foot_points: list[tuple[int, float, float]] = []
        lunge_candidates = []
        for frame in frames:
            keypoints = (
                frame.top_keypoints if side == "top" else frame.bottom_keypoints
            )
            if keypoints is None:
                continue
            shoulders = _midpoint(keypoints[5], keypoints[6])
            hips = _midpoint(keypoints[11], keypoints[12])
            torso_dx = shoulders[0] - hips[0]
            torso_dy = shoulders[1] - hips[1]
            lean = math.degrees(math.atan2(torso_dx, max(-torso_dy, 1e-6)))
            left_knee = joint_angle(keypoints[11], keypoints[13], keypoints[15])
            right_knee = joint_angle(
                keypoints[12],
                keypoints[14],
                keypoints[16],
            )
            ankle_gap = math.dist(keypoints[15], keypoints[16])
            shoulder_width = max(math.dist(keypoints[5], keypoints[6]), 1.0)
            is_lunge = (
                min(left_knee, right_knee) < 115
                and ankle_gap / shoulder_width > 1.2
            )
            if is_lunge:
                lunge_candidates.append(frame.frame)
            left_wrist.append(
                (frame.frame, keypoints[9][0], keypoints[9][1])
            )
            right_wrist.append(
                (frame.frame, keypoints[10][0], keypoints[10][1])
            )
            foot = _midpoint(keypoints[15], keypoints[16])
            foot_points.append((frame.frame, foot[0], foot[1]))
            samples.append(
                {
                    "frame": frame.frame,
                    "timestamp_us": frame.timestamp_us,
                    "torso_lean_deg_2d": round(lean, 2),
                    "left_knee_angle_deg_2d": round(left_knee, 2),
                    "right_knee_angle_deg_2d": round(right_knee, 2),
                    "lunge_candidate": is_lunge,
                }
            )
        wrist_values = [
            *wrist_acceleration(left_wrist, fps=fps),
            *wrist_acceleration(right_wrist, fps=fps),
        ]
        start_candidates = []
        previous_speed = 0.0
        for index in range(1, len(foot_points)):
            frame_gap = foot_points[index][0] - foot_points[index - 1][0]
            if frame_gap <= 0:
                continue
            speed = (
                math.hypot(
                    foot_points[index][1] - foot_points[index - 1][1],
                    foot_points[index][2] - foot_points[index - 1][2],
                )
                * fps
                / frame_gap
            )
            if previous_speed < 45 and speed >= 120:
                start_candidates.append(foot_points[index][0])
            previous_speed = speed
        result[side] = {
            "samples": samples,
            "max_wrist_acceleration_px_s2": round(
                max(
                    (
                        float(item["acceleration_px_s2"])
                        for item in wrist_values
                    ),
                    default=0.0,
                ),
                2,
            ),
            "start_step_candidates": start_candidates,
            "lunge_candidates": lunge_candidates,
            "quality_note": (
                "2D single-camera candidate metric; validate against labeled "
                "motion samples before coaching use."
            ),
        }
    return result
