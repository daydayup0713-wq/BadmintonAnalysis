from __future__ import annotations

import builtins
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

from courtvision.exporting import (
    export_csv_bundle,
    export_json_summary,
    export_pdf_report,
)


class ExportingTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(".test-tmp")
        root.mkdir(parents=True, exist_ok=True)
        self.output = root / f"exporting-{uuid4().hex}"
        self.output.mkdir()
        self.summary = {
            "job": {"id": "job_test"},
            "shots": [
                {
                    "hit_frame": 10,
                    "timestamp_us": 333333,
                    "player": "bottom",
                    "label": "smash",
                    "confidence": 0.8,
                }
            ],
            "metrics": {
                "players": {
                    "top": {
                        "track": [
                            {
                                "frame": 10,
                                "timestamp_us": 333333,
                                "x_m": 2.1,
                                "y_m": 3.2,
                                "speed_mps": 1.5,
                            }
                        ]
                    },
                    "bottom": {"track": []},
                }
            },
            "rallies": [{"start_frame": 10, "end_frame": 20}],
            "review": {
                "quality_issues": [
                    {
                        "code": "LOW_POSE_COVERAGE",
                        "message": "Pose coverage is below 80%.",
                    }
                ]
            },
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.output, ignore_errors=True)

    def test_exports_json_and_csv_without_losing_confidence(self) -> None:
        json_path = export_json_summary(self.summary, self.output)
        csv_paths = export_csv_bundle(self.summary, self.output)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        shot_csv = csv_paths["shots"].read_text(encoding="utf-8-sig")

        self.assertEqual(payload["shots"][0]["confidence"], 0.8)
        self.assertIn("confidence", shot_csv)
        self.assertIn("smash", shot_csv)

    def test_csv_ignores_unlisted_movement_metadata(self) -> None:
        self.summary["metrics"]["players"]["top"]["track"][0].update(
            {
                "confidence": 0.75,
                "origin": "external",
            }
        )

        csv_paths = export_csv_bundle(self.summary, self.output)

        movement_csv = csv_paths["movement"].read_text(encoding="utf-8-sig")
        self.assertIn("top,10,333333,2.1,3.2,1.5", movement_csv)
        self.assertNotIn("confidence", movement_csv)

    def test_pdf_falls_back_to_dependency_free_document(self) -> None:
        real_import = builtins.__import__

        def import_without_reportlab(name, *args, **kwargs):
            if name == "reportlab" or name.startswith("reportlab."):
                raise ModuleNotFoundError("reportlab disabled for fallback test")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=import_without_reportlab):
            pdf_path = export_pdf_report(self.summary, self.output)

        payload = pdf_path.read_bytes()
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertTrue(payload.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"BadmintonAnalysis Report", payload)
        self.assertIn(b"Shot candidates: 1", payload)
        self.assertIn(b"LOW_POSE_COVERAGE", payload)


if __name__ == "__main__":
    unittest.main()
