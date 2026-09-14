from __future__ import annotations

import unittest

from courtvision.contracts import DataOrigin, PlayerPoseFrame
from courtvision.metrics import build_player_movement_metrics


COURT = [
    [100, 100],
    [500, 100],
    [90, 300],
    [510, 300],
    [80, 600],
    [520, 600],
]


def pose_at(x: float, y: float) -> list[list[float]]:
    points = [[x, y - 40] for _ in range(17)]
    points[15] = [x - 3, y]
    points[16] = [x + 3, y]
    return points


class MovementMetricTests(unittest.TestCase):
    def test_rejects_pose_jump_from_effective_speed(self) -> None:
        frames = []
        x_positions = [300] * 8 + [470] * 3 + [300] * 8
        for frame, x in enumerate(x_positions):
            frames.append(
                PlayerPoseFrame(
                    frame=frame,
                    timestamp_us=frame * 100_000,
                    top_keypoints=pose_at(x, 220),
                    bottom_keypoints=pose_at(300, 500),
                    confidence=0.9,
                    provider_version="test",
                    origin=DataOrigin.EXTERNAL,
                )
            )

        metrics = build_player_movement_metrics(frames, COURT, fps=10)
        top = metrics["top"]

        self.assertGreater(
            top["diagnostics"]["raw_max_speed_mps"],
            top["max_effective_speed_mps"],
        )
        self.assertGreater(top["trajectory_valid_ratio"], 0.8)
        self.assertEqual(top["validation_status"], "missing_evidence")
        self.assertEqual(top["quality_label"], "2D候选")

    def test_hides_motion_values_when_valid_ratio_is_below_threshold(self) -> None:
        frames = []
        x_positions = [300] * 5 + [470] * 3 + [300] * 5
        for frame, x in enumerate(x_positions):
            frames.append(
                PlayerPoseFrame(
                    frame=frame,
                    timestamp_us=frame * 100_000,
                    top_keypoints=pose_at(x, 220),
                    bottom_keypoints=pose_at(300, 500),
                    confidence=0.9,
                    provider_version="test",
                    origin=DataOrigin.EXTERNAL,
                )
            )

        top = build_player_movement_metrics(frames, COURT, fps=10)["top"]

        self.assertLess(top["trajectory_valid_ratio"], 0.8)
        self.assertIsNone(top["distance_m"])
        self.assertIsNone(top["average_speed_mps"])
        self.assertIsNone(top["max_effective_speed_mps"])

    def test_measures_departure_and_return_to_observed_base(self) -> None:
        frames = [
            PlayerPoseFrame(
                frame=0,
                timestamp_us=0,
                top_keypoints=pose_at(300, 220),
                bottom_keypoints=pose_at(300, 500),
                confidence=0.9,
                provider_version="test",
                origin=DataOrigin.EXTERNAL,
            ),
            PlayerPoseFrame(
                frame=10,
                timestamp_us=1_000_000,
                top_keypoints=pose_at(470, 220),
                bottom_keypoints=pose_at(470, 500),
                confidence=0.9,
                provider_version="test",
                origin=DataOrigin.EXTERNAL,
            ),
            PlayerPoseFrame(
                frame=20,
                timestamp_us=2_000_000,
                top_keypoints=pose_at(300, 220),
                bottom_keypoints=pose_at(300, 500),
                confidence=0.9,
                provider_version="test",
                origin=DataOrigin.EXTERNAL,
            ),
        ]

        metrics = build_player_movement_metrics(frames, COURT, fps=10)
        recovery = metrics["bottom"]["recovery"]

        self.assertEqual(recovery["excursion_count"], 1)
        self.assertEqual(recovery["completed_returns"], 1)
        self.assertEqual(recovery["return_rate"], 1.0)
        self.assertEqual(recovery["events"][0]["latency_seconds"], 1.0)


if __name__ == "__main__":
    unittest.main()
