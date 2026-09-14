from __future__ import annotations

import math
import unittest

from pydantic import ValidationError

from courtvision.importing import ExternalAnalysisImport


def valid_payload() -> dict:
    return {
        "provider": "external-lab",
        "provider_version": "2026.09",
        "video": {
            "fps": 30,
            "width": 1280,
            "height": 720,
            "total_frames": 300,
            "duration_seconds": 10,
        },
        "rallies": [],
        "poses": [
            {
                "frame": 12,
                "timestamp_us": 400_000,
                "top_keypoints": [[float(index), 20.0] for index in range(17)],
                "bottom_keypoints": None,
                "confidence": 0.91,
            }
        ],
        "shuttle": [],
        "hits": [],
        "shots": [],
    }


class ExternalAnalysisImportValidationTests(unittest.TestCase):
    def test_requires_non_blank_provider_identity(self) -> None:
        payload = valid_payload()
        payload["provider"] = "   "

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)

    def test_pose_requires_exactly_seventeen_keypoints(self) -> None:
        payload = valid_payload()
        payload["poses"][0]["top_keypoints"] = [[1.0, 2.0]]

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)

    def test_pose_rejects_non_finite_coordinates(self) -> None:
        payload = valid_payload()
        payload["poses"][0]["top_keypoints"][0][0] = math.nan

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)

    def test_pose_frame_must_be_inside_video(self) -> None:
        payload = valid_payload()
        payload["poses"][0]["frame"] = 300

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)

    def test_nested_external_confidence_stays_in_unit_interval(self) -> None:
        payload = valid_payload()
        payload["hits"] = [{"frame": 30, "confidence": 1.01}]

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
