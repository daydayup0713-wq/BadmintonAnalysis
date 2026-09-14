from __future__ import annotations

import math
import unittest
from pathlib import Path

from pydantic import ValidationError

from courtvision.importing import ExternalAnalysisImport, import_external_results
from courtvision.repository import Repository
from courtvision.state_machine import AnalysisStage


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

    def test_court_calibration_requires_six_finite_points(self) -> None:
        payload = valid_payload()
        payload["court_points"] = [[100.0, 100.0] for _ in range(5)]

        with self.assertRaises(ValidationError):
            ExternalAnalysisImport.model_validate(payload)


class ExternalAnalysisPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository(":memory:", journal_mode="DELETE")
        self.repo.initialize()
        session = self.repo.create_session(title="External import")
        self.job = self.repo.create_job(
            session_id=session["id"],
            source_path="uploads/external.mp4",
        )
        self.repo.update_job_stage(
            self.job["id"],
            AnalysisStage.AWAITING_RESULTS,
            progress=0.1,
        )

    def tearDown(self) -> None:
        self.repo.close()

    def test_import_saves_platform_results_and_requires_review(self) -> None:
        payload = valid_payload()
        payload["court_points"] = [
            [100.0, 100.0],
            [500.0, 100.0],
            [90.0, 300.0],
            [510.0, 300.0],
            [80.0, 600.0],
            [520.0, 600.0],
        ]

        result = import_external_results(
            self.repo,
            self.job["id"],
            ExternalAnalysisImport.model_validate(payload),
        )

        self.assertEqual(result["stage"], "review_required")
        self.assertEqual(
            self.repo.get_result(self.job["id"], "external_import"),
            {"provider": "external-lab", "provider_version": "2026.09"},
        )
        pose = self.repo.get_result(self.job["id"], "pose_tracking")
        self.assertEqual(pose["frames"][0]["origin"], "external")
        self.assertEqual(
            pose["frames"][0]["provider_version"],
            "2026.09",
        )
        self.assertIn("players", self.repo.get_result(self.job["id"], "metrics"))
        self.assertEqual(
            result["checkpoint"],
            {
                "provider": "external-lab",
                "provider_version": "2026.09",
                "imported": True,
            },
        )

    def test_empty_import_marks_missing_evidence_without_events(self) -> None:
        payload = valid_payload()
        payload["poses"] = []

        result = import_external_results(
            self.repo,
            self.job["id"],
            ExternalAnalysisImport.model_validate(payload),
        )

        self.assertEqual(result["stage"], "review_required")
        review = self.repo.get_result(self.job["id"], "review_required")
        self.assertEqual(review["status"], "review_required")
        self.assertIn("pose", review["missing_evidence"])
        events = self.repo.get_result(self.job["id"], "event_detection")
        self.assertEqual(events["hits"], [])
        self.assertEqual(events["shots"], [])
        metrics = self.repo.get_result(self.job["id"], "metrics")
        self.assertFalse(metrics["available"])

    def test_bundled_synthetic_fixture_completes_import(self) -> None:
        fixture_path = (
            Path(__file__).parents[1]
            / "services"
            / "api"
            / "courtvision"
            / "fixtures"
            / "synthetic-demo.json"
        )
        payload = ExternalAnalysisImport.model_validate_json(
            fixture_path.read_text(encoding="utf-8")
        )

        result = import_external_results(self.repo, self.job["id"], payload)

        self.assertEqual(payload.provider, "synthetic-demo")
        self.assertEqual(result["stage"], "review_required")
        self.assertTrue(
            self.repo.get_result(self.job["id"], "metrics")["available"]
        )


if __name__ == "__main__":
    unittest.main()
