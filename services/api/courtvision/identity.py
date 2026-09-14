from __future__ import annotations

import math
from typing import Sequence

from .contracts import PlayerPoseFrame


BONES = (
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)


def pose_signature(keypoints: Sequence[Sequence[float]]) -> list[float]:
    shoulder_width = max(math.dist(keypoints[5], keypoints[6]), 1e-6)
    lengths = [
        math.dist(keypoints[first], keypoints[second]) / shoulder_width
        for first, second in BONES
    ]
    torso = math.dist(
        (
            (keypoints[5][0] + keypoints[6][0]) / 2,
            (keypoints[5][1] + keypoints[6][1]) / 2,
        ),
        (
            (keypoints[11][0] + keypoints[12][0]) / 2,
            (keypoints[11][1] + keypoints[12][1]) / 2,
        ),
    )
    lengths.append(torso / shoulder_width)
    return lengths


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    return math.sqrt(
        sum((left - right) ** 2 for left, right in zip(first, second))
        / max(len(first), 1)
    )


def _update(
    centroid: list[float],
    signature: Sequence[float],
    count: int,
) -> list[float]:
    weight = min(count, 30)
    return [
        (old * weight + new) / (weight + 1)
        for old, new in zip(centroid, signature)
    ]


def assign_stable_identities(
    frames: Sequence[PlayerPoseFrame],
) -> list[dict[str, object]]:
    centroids: dict[str, list[float]] = {}
    counts = {"athlete-1": 0, "athlete-2": 0}
    result: list[dict[str, object]] = []
    for frame in frames:
        if frame.top_keypoints is None or frame.bottom_keypoints is None:
            result.append(
                {
                    "frame": frame.frame,
                    "timestamp_us": frame.timestamp_us,
                    "top_athlete_id": None,
                    "bottom_athlete_id": None,
                    "confidence": 0.0,
                    "origin": frame.origin.value,
                }
            )
            continue
        top_signature = pose_signature(frame.top_keypoints)
        bottom_signature = pose_signature(frame.bottom_keypoints)
        if not centroids:
            top_id, bottom_id = "athlete-1", "athlete-2"
            centroids[top_id] = top_signature
            centroids[bottom_id] = bottom_signature
            confidence = 0.5
        else:
            straight = _distance(
                top_signature,
                centroids["athlete-1"],
            ) + _distance(
                bottom_signature,
                centroids["athlete-2"],
            )
            swapped = _distance(
                top_signature,
                centroids["athlete-2"],
            ) + _distance(
                bottom_signature,
                centroids["athlete-1"],
            )
            if straight <= swapped:
                top_id, bottom_id = "athlete-1", "athlete-2"
            else:
                top_id, bottom_id = "athlete-2", "athlete-1"
            margin = abs(straight - swapped)
            confidence = min(0.95, 0.5 + margin / max(straight + swapped, 1e-6))
        for athlete_id, signature in (
            (top_id, top_signature),
            (bottom_id, bottom_signature),
        ):
            centroids[athlete_id] = _update(
                centroids[athlete_id],
                signature,
                counts[athlete_id],
            )
            counts[athlete_id] += 1
        result.append(
            {
                "frame": frame.frame,
                "timestamp_us": frame.timestamp_us,
                "top_athlete_id": top_id,
                "bottom_athlete_id": bottom_id,
                "confidence": confidence,
                "model_version": "solo:pose-proportion-identity:v1",
                "origin": frame.origin.value,
            }
        )
    return result


def identity_confident_ratio(
    identities: Sequence[dict[str, object]],
    *,
    confidence_threshold: float = 0.8,
) -> float:
    if not identities:
        return 0.0
    confident = sum(
        float(identity.get("confidence", 0.0)) >= confidence_threshold
        and identity.get("top_athlete_id") is not None
        and identity.get("bottom_athlete_id") is not None
        for identity in identities
    )
    return confident / len(identities)
