from __future__ import annotations

import unittest

from courtvision.contracts import (
    CoordinateSpace,
    DataOrigin,
    PlayerPoseFrame,
    PlayerSide,
    ShotClassification,
    ShuttleTrackPoint,
)


class ShuttleTrackPointTests(unittest.TestCase):
    def test_rejects_confidence_outside_unit_interval(self) -> None:
        with self.assertRaises(ValueError):
            ShuttleTrackPoint(
                frame=10,
                timestamp_us=333_333,
                x=100.0,
                y=50.0,
                visible=True,
                confidence=1.1,
                coordinate_space=CoordinateSpace.SOURCE_PIXEL,
                provider_version="external-track-v1",
                origin=DataOrigin.EXTERNAL,
            )

    def test_serializes_stable_wire_shape(self) -> None:
        point = ShuttleTrackPoint(
            frame=10,
            timestamp_us=333_333,
            x=100.0,
            y=50.0,
            visible=True,
            confidence=0.87,
            coordinate_space=CoordinateSpace.SOURCE_PIXEL,
            provider_version="external-track-v1",
            origin=DataOrigin.EXTERNAL,
        )

        self.assertEqual(
            point.to_dict(),
            {
                "frame": 10,
                "timestamp_us": 333333,
                "x": 100.0,
                "y": 50.0,
                "visible": True,
                "confidence": 0.87,
                "coordinate_space": "source_pixel",
                "provider_version": "external-track-v1",
                "origin": "external",
            },
        )

    def test_player_side_values_are_api_stable(self) -> None:
        self.assertEqual(PlayerSide.TOP.value, "top")
        self.assertEqual(PlayerSide.BOTTOM.value, "bottom")

    def test_pose_frame_requires_seventeen_keypoints_per_player(self) -> None:
        with self.assertRaisesRegex(ValueError, "17 keypoints"):
            PlayerPoseFrame(
                frame=1,
                timestamp_us=33_333,
                top_keypoints=[[1.0, 2.0]],
                bottom_keypoints=None,
                confidence=0.8,
                provider_version="pose:test",
                origin=DataOrigin.EXTERNAL,
            )

    def test_shot_classification_has_stable_wire_shape(self) -> None:
        shot = ShotClassification(
            hit_frame=90,
            timestamp_us=3_000_000,
            player=PlayerSide.BOTTOM,
            label="smash",
            confidence=0.62,
            provider_version="classifier:v1",
            origin=DataOrigin.EXTERNAL,
        )

        self.assertEqual(shot.to_dict()["player"], "bottom")
        self.assertEqual(shot.to_dict()["label"], "smash")


if __name__ == "__main__":
    unittest.main()
