from __future__ import annotations

import unittest

from courtvision.repository import Repository
from courtvision.state_machine import AnalysisStage


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository(":memory:", journal_mode="DELETE")
        self.repo.initialize()

    def tearDown(self) -> None:
        self.repo.close()

    def test_creates_athlete_session_and_job(self) -> None:
        athlete = self.repo.create_athlete("陈昊", handedness="right")
        session = self.repo.create_session(
            title="周六对抗训练",
            athlete_top_id=athlete["id"],
        )
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="videos/test1.mp4",
        )

        self.assertEqual(job["stage"], AnalysisStage.UPLOADED.value)
        self.assertEqual(job["session_id"], session["id"])

    def test_lists_athletes_sessions_and_athlete_jobs(self) -> None:
        athlete = self.repo.create_athlete("林涛", handedness="left")
        session = self.repo.create_session(
            title="晚间训练",
            athlete_bottom_id=athlete["id"],
        )
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="videos/training.mp4",
        )

        self.assertEqual(self.repo.list_athletes(), [athlete])
        self.assertEqual(self.repo.list_sessions()[0]["id"], session["id"])
        detail = self.repo.get_athlete(athlete["id"])
        self.assertEqual(detail["sessions"][0]["slot"], "bottom")
        self.assertEqual(detail["jobs"][0]["id"], job["id"])

    def test_checkpoint_update_is_persisted(self) -> None:
        session = self.repo.create_session(title="基准测试")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="videos/test2.mp4",
        )

        self.repo.update_job_stage(
            job["id"],
            AnalysisStage.VALIDATING,
            progress=0.24,
            checkpoint={"probe_frame": 120},
        )
        stored = self.repo.get_job(job["id"])

        self.assertEqual(stored["stage"], "validating")
        self.assertEqual(stored["checkpoint"], {"probe_frame": 120})
        self.assertAlmostEqual(stored["progress"], 0.24)

    def test_annotation_revision_keeps_old_and_new_values(self) -> None:
        session = self.repo.create_session(title="revision test")
        job = self.repo.create_job(
            session_id=session["id"],
            source_path="videos/test1.mp4",
        )
        revision = self.repo.create_revision(
            job_id=job["id"],
            entity_type="shot",
            entity_id="shot-12",
            field_name="classification",
            old_value={"label": "clear"},
            new_value={"label": "smash"},
            reason="人工复核",
        )

        self.assertEqual(revision["old_value"], {"label": "clear"})
        self.assertEqual(revision["new_value"], {"label": "smash"})
        self.assertEqual(
            self.repo.list_revisions(job["id"])[0]["entity_id"],
            "shot-12",
        )


if __name__ == "__main__":
    unittest.main()
