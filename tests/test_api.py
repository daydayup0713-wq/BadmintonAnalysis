from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from courtvision.api import create_app
from courtvision.repository import Repository
from courtvision.state_machine import AnalysisStage


REPO_ROOT = Path(__file__).resolve().parents[1]


def synthetic_payload() -> dict:
    fixture = (
        REPO_ROOT
        / "services"
        / "api"
        / "courtvision"
        / "fixtures"
        / "synthetic-demo.json"
    )
    return json.loads(fixture.read_text(encoding="utf-8"))


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository(":memory:", journal_mode="DELETE")
        self.repo.initialize()
        self.client = TestClient(
            create_app(repository=self.repo, repo_root=REPO_ROOT)
        )

    def tearDown(self) -> None:
        self.client.close()
        self.repo.close()

    def test_health_identifies_provider_neutral_platform(self) -> None:
        health = self.client.get("/api/health")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            health.json(),
            {
                "status": "ok",
                "service": "BadmintonAnalysis",
                "analysis_mode": "external_results",
            },
        )

    def test_model_and_runtime_routes_are_absent(self) -> None:
        self.assertEqual(self.client.get("/api/models").status_code, 404)
        self.assertEqual(self.client.get("/api/runtime").status_code, 404)

    def test_lists_athletes_sessions_and_athlete_detail(self) -> None:
        athlete = self.client.post(
            "/api/athletes",
            json={"name": "周宁", "handedness": "right"},
        ).json()
        session = self.client.post(
            "/api/sessions",
            json={
                "title": "周末对抗",
                "athlete_top_id": athlete["id"],
            },
        ).json()
        job = self.client.post(
            "/api/jobs",
            json={
                "session_id": session["id"],
                "source_path": "videos/test.mp4",
            },
        ).json()

        athletes = self.client.get("/api/athletes")
        sessions = self.client.get("/api/sessions")
        detail = self.client.get(f"/api/athletes/{athlete['id']}")

        self.assertEqual(athletes.status_code, 200)
        self.assertEqual(athletes.json()[0]["name"], "周宁")
        self.assertEqual(sessions.json()[0]["title"], "周末对抗")
        self.assertEqual(detail.json()["jobs"][0]["id"], job["id"])
        self.assertEqual(job["stage"], "awaiting_results")

    def test_upload_waits_for_external_results(self) -> None:
        response = self.client.post(
            "/api/uploads?title=Training",
            files={"file": ("clip.mp4", b"video", "video/mp4")},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["job"]["stage"], "awaiting_results")

    def test_run_route_requires_external_results(self) -> None:
        session = self.repo.create_session(title="external task")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="uploads/new.mp4",
        )

        response = self.client.post(f"/api/jobs/{job['id']}/run")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "external_results_required")

    def test_import_endpoint_returns_reviewable_summary(self) -> None:
        session = self.client.post(
            "/api/sessions",
            json={"title": "Import task"},
        ).json()
        job = self.client.post(
            "/api/jobs",
            json={
                "session_id": session["id"],
                "source_path": "uploads/import.mp4",
            },
        ).json()

        response = self.client.post(
            f"/api/jobs/{job['id']}/results/import",
            json=synthetic_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["stage"], "review_required")
        self.assertEqual(len(response.json()["rallies"]), 1)
        self.assertEqual(len(response.json()["hits"]), 2)

    def test_bootstraps_synthetic_analysis_and_returns_summary(self) -> None:
        response = self.client.post("/api/demo/bootstrap", json={})

        self.assertEqual(response.status_code, 201)
        job_id = response.json()["job"]["id"]
        summary = self.client.get(f"/api/jobs/{job_id}/summary")

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["job"]["stage"], "review_required")
        self.assertEqual(len(summary.json()["rallies"]), 1)
        self.assertEqual(len(summary.json()["hits"]), 2)
        self.assertEqual(summary.json()["identities"], [])

    def test_records_human_correction(self) -> None:
        bootstrap = self.client.post("/api/demo/bootstrap", json={}).json()
        job_id = bootstrap["job"]["id"]
        shot = bootstrap["shots"][0]
        revision = self.client.post(
            "/api/revisions",
            json={
                "job_id": job_id,
                "entity_type": "shot",
                "entity_id": shot["id"],
                "field_name": "label",
                "old_value": shot["label"],
                "new_value": "smash",
                "reason": "manual review",
            },
        )

        self.assertEqual(revision.status_code, 201)
        self.assertEqual(revision.json()["new_value"], "smash")
        corrected = self.client.get(f"/api/jobs/{job_id}/summary").json()
        corrected_shot = next(
            item for item in corrected["shots"] if item["id"] == shot["id"]
        )
        self.assertEqual(corrected_shot["label"], "smash")
        self.assertEqual(corrected_shot["origin"], "human")

    def test_summary_adds_stable_entity_ids_for_human_correction(
        self,
    ) -> None:
        session = self.repo.create_session(title="external task")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="external.mp4",
        )
        self.repo.save_result(
            job_id=job["id"],
            kind="event_detection",
            payload={
                "rallies": [{"start_frame": 273, "end_frame": 547}],
                "shots": [
                    {
                        "hit_frame": 280,
                        "player": "top",
                        "label": "drop_or_push",
                    }
                ],
            },
        )

        summary = self.client.get(f"/api/jobs/{job['id']}/summary").json()

        self.assertEqual(summary["rallies"][0]["id"], "rally-1")
        self.assertEqual(summary["shots"][0]["id"], "shot-280")
        revision = self.client.post(
            "/api/revisions",
            json={
                "job_id": job["id"],
                "entity_type": "shot",
                "entity_id": "shot-280",
                "field_name": "player",
                "old_value": "top",
                "new_value": "bottom",
                "reason": "browser review",
            },
        )
        self.assertEqual(revision.status_code, 201)
        corrected = self.client.get(f"/api/jobs/{job['id']}/summary").json()
        self.assertEqual(corrected["shots"][0]["player"], "bottom")
        self.assertEqual(corrected["shots"][0]["origin"], "human")

    def test_downloads_only_rendered_rally_clips(self) -> None:
        clip = REPO_ROOT / "README.md"
        session = self.repo.create_session(title="rendered task")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="rendered.mp4",
        )
        self.repo.save_result(
            job_id=job["id"],
            kind="rendering",
            payload={"rally_clips": [str(clip)]},
        )
        response = self.client.get(
            f"/api/jobs/{job['id']}/exports/rallies/{clip.name}"
        )
        unknown = self.client.get(
            f"/api/jobs/{job['id']}/exports/rallies/unknown.mp4"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, clip.read_bytes())
        self.assertEqual(unknown.status_code, 404)

    def test_retries_rendering_left_active_by_process_interruption(self) -> None:
        session = self.repo.create_session(title="interrupted rendering")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path=str(REPO_ROOT / "README.md"),
        )
        for index, stage in enumerate(
            (
                AnalysisStage.VALIDATING,
                AnalysisStage.TRANSCODING,
                AnalysisStage.CALIBRATING,
                AnalysisStage.SEGMENTING,
                AnalysisStage.POSE_TRACKING,
                AnalysisStage.SHUTTLE_TRACKING,
                AnalysisStage.EVENT_DETECTION,
                AnalysisStage.METRICS,
                AnalysisStage.REVIEW_REQUIRED,
                AnalysisStage.RENDERING,
            ),
            start=1,
        ):
            self.repo.update_job_stage(
                job["id"],
                stage,
                progress=min(index / 10, 0.95),
                checkpoint={"active_stage": stage.value},
            )
        self.repo.save_result(
            job_id=job["id"],
            kind="validating",
            payload={"fps": 10.0},
        )
        self.repo.save_result(
            job_id=job["id"],
            kind="pose_tracking",
            payload={"frames": [], "identities": []},
        )
        self.repo.save_result(
            job_id=job["id"],
            kind="shuttle_tracking",
            payload={"rallies": []},
        )
        output = REPO_ROOT / "exports" / job["id"]

        with (
            patch(
                "courtvision.exporting.export_json_summary",
                return_value=output / "analysis.json",
            ),
            patch(
                "courtvision.exporting.export_csv_bundle",
                return_value={
                    "shots": output / "shots.csv",
                    "movement": output / "movement.csv",
                },
            ),
            patch(
                "courtvision.exporting.export_pdf_report",
                return_value=output / "analysis-report.pdf",
            ),
            patch(
                "courtvision.exporting.render_overlay_video",
                return_value=output / "analysis-video.mp4",
            ),
            patch(
                "courtvision.exporting.export_rally_clips",
                return_value=[],
            ),
        ):
            response = self.client.post(f"/api/jobs/{job['id']}/exports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.repo.get_job(job["id"])["stage"],
            AnalysisStage.COMPLETED.value,
        )

    def test_returns_existing_exports_for_completed_job(self) -> None:
        session = self.repo.create_session(title="completed export")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path=str(REPO_ROOT / "README.md"),
        )
        for index, stage in enumerate(
            (
                AnalysisStage.VALIDATING,
                AnalysisStage.TRANSCODING,
                AnalysisStage.CALIBRATING,
                AnalysisStage.SEGMENTING,
                AnalysisStage.POSE_TRACKING,
                AnalysisStage.SHUTTLE_TRACKING,
                AnalysisStage.EVENT_DETECTION,
                AnalysisStage.METRICS,
                AnalysisStage.REVIEW_REQUIRED,
                AnalysisStage.RENDERING,
                AnalysisStage.COMPLETED,
            ),
            start=1,
        ):
            self.repo.update_job_stage(
                job["id"],
                stage,
                progress=min(index / 11, 1.0),
                checkpoint={"completed_stage": stage.value},
            )
        rendering = {
            "json": "analysis.json",
            "shots_csv": "shots.csv",
            "movement_csv": "movement.csv",
            "pdf": "analysis-report.pdf",
            "video": "analysis-video.mp4",
            "rally_clips": ["rallies/rally-001.mp4"],
        }
        self.repo.save_result(
            job_id=job["id"],
            kind="rendering",
            payload=rendering,
        )

        response = self.client.post(f"/api/jobs/{job['id']}/exports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), rendering)


if __name__ == "__main__":
    unittest.main()
