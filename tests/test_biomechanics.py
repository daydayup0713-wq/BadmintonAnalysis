from __future__ import annotations

import unittest

from courtvision.biomechanics import (
    build_swing_metrics,
    joint_angle,
    wrist_acceleration,
)
from courtvision.contracts import DataOrigin, PlayerPoseFrame


COURT = [
    [100, 100],
    [500, 100],
    [90, 300],
    [510, 300],
    [80, 600],
    [520, 600],
]


def pose_at(
    frame: int,
    *,
    top_wrist_x: float,
    bottom_wrist_x: float,
) -> PlayerPoseFrame:
    def player(center_x: float, foot_y: float, wrist_x: float) -> list[list[float]]:
        points = [[center_x, foot_y - 80] for _ in range(17)]
        points[5] = [center_x - 20, foot_y - 70]
        points[6] = [center_x + 20, foot_y - 70]
        points[9] = [wrist_x, foot_y - 50]
        points[10] = [wrist_x, foot_y - 50]
        points[15] = [center_x - 4, foot_y]
        points[16] = [center_x + 4, foot_y]
        return points

    return PlayerPoseFrame(
        frame=frame,
        timestamp_us=frame * 100_000,
        top_keypoints=player(300, 220, top_wrist_x),
        bottom_keypoints=player(300, 500, bottom_wrist_x),
        confidence=0.9,
        provider_version="test",
        origin=DataOrigin.EXTERNAL,
    )


class BiomechanicsTests(unittest.TestCase):
    def test_joint_angle_returns_right_angle(self) -> None:
        angle = joint_angle([0, 1], [0, 0], [1, 0])
        self.assertAlmostEqual(angle, 90.0)

    def test_wrist_acceleration_uses_frame_rate(self) -> None:
        points = [(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 4.0, 0.0)]
        acceleration = wrist_acceleration(points, fps=10)

        self.assertEqual(len(acceleration), 1)
        self.assertAlmostEqual(acceleration[0]["acceleration_px_s2"], 200.0)

    def test_builds_hit_count_and_relative_swing_heatmaps(self) -> None:
        frames = [
            pose_at(
                frame,
                top_wrist_x=300 + (20 if frame in {1, 2, 3} else 0),
                bottom_wrist_x=300 + (60 if frame in {6, 7, 8} else 0),
            )
            for frame in range(12)
        ]
        hits = [
            {
                "frame": 3,
                "timestamp_us": 300_000,
                "player": "top",
                "confidence": 0.8,
            },
            {
                "frame": 8,
                "timestamp_us": 800_000,
                "player": "bottom",
                "confidence": 0.6,
            },
            {
                "frame": 9,
                "timestamp_us": 900_000,
                "player": "unknown",
                "confidence": 0.9,
            },
        ]

        metrics = build_swing_metrics(
            frames,
            hits,
            COURT,
            fps=10,
            duration_seconds=1.2,
        )

        self.assertEqual(metrics["top"]["hit_count"], 1)
        self.assertEqual(metrics["bottom"]["hit_count"], 1)
        self.assertEqual(metrics["bottom"]["low_confidence_hit_count"], 1)
        self.assertGreater(
            metrics["bottom"]["events"][0]["intensity_index"],
            metrics["top"]["events"][0]["intensity_index"],
        )
        self.assertEqual(len(metrics["top"]["spatial_heatmap"]), 6)
        self.assertEqual(len(metrics["top"]["spatial_heatmap"][0]), 3)
        self.assertEqual(len(metrics["top"]["timeline_heatmap"]), 3)
        self.assertEqual(metrics["top"]["validation_status"], "missing_evidence")


if __name__ == "__main__":
    unittest.main()
