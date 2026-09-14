from __future__ import annotations

import unittest

from courtvision.contracts import DataOrigin, PlayerPoseFrame
from courtvision.identity import (
    assign_stable_identities,
    identity_confident_ratio,
)


def pose(
    scale: float,
    offset_y: float,
    *,
    leg_ratio: float = 1.0,
) -> list[list[float]]:
    base = [
        [0, 0],
        [-1, -1],
        [1, -1],
        [-2, -1],
        [2, -1],
        [-2, 3],
        [2, 3],
        [-3, 6],
        [3, 6],
        [-4, 9],
        [4, 9],
        [-2, 9],
        [2, 9],
        [-2, 14],
        [2, 14],
        [-2, 19],
        [2, 19],
    ]
    return [
        [
            x * scale + 100,
            (
                y
                if index < 13
                else 9 + (y - 9) * leg_ratio
            )
            * scale
            + offset_y,
        ]
        for index, (x, y) in enumerate(base)
    ]


class IdentityTests(unittest.TestCase):
    def test_keeps_physical_identity_when_players_swap_sides(self) -> None:
        frames = [
            PlayerPoseFrame(
                frame=0,
                timestamp_us=0,
                top_keypoints=pose(1.0, 100),
                bottom_keypoints=pose(1.35, 400, leg_ratio=1.35),
                confidence=0.9,
                provider_version="test",
                origin=DataOrigin.EXTERNAL,
            ),
            PlayerPoseFrame(
                frame=100,
                timestamp_us=3_333_333,
                top_keypoints=pose(1.35, 100, leg_ratio=1.35),
                bottom_keypoints=pose(1.0, 400),
                confidence=0.9,
                provider_version="test",
                origin=DataOrigin.EXTERNAL,
            ),
        ]

        identities = assign_stable_identities(frames)

        self.assertEqual(identities[0]["top_athlete_id"], "athlete-1")
        self.assertEqual(identities[0]["bottom_athlete_id"], "athlete-2")
        self.assertEqual(identities[1]["top_athlete_id"], "athlete-2")
        self.assertEqual(identities[1]["bottom_athlete_id"], "athlete-1")

    def test_reports_ratio_of_frames_safe_for_automatic_identity(self) -> None:
        identities = [
            {
                "confidence": 0.95,
                "top_athlete_id": "athlete-1",
                "bottom_athlete_id": "athlete-2",
            },
            {
                "confidence": 0.81,
                "top_athlete_id": "athlete-1",
                "bottom_athlete_id": "athlete-2",
            },
            {
                "confidence": 0.79,
                "top_athlete_id": "athlete-1",
                "bottom_athlete_id": "athlete-2",
            },
            {
                "confidence": 0.0,
                "top_athlete_id": None,
                "bottom_athlete_id": None,
            },
        ]

        self.assertEqual(identity_confident_ratio(identities), 0.5)


if __name__ == "__main__":
    unittest.main()
