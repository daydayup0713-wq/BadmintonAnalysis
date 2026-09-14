from __future__ import annotations

import unittest

from courtvision.pipeline import AnalysisPipeline, PipelineContext, PipelineStage
from courtvision.repository import Repository
from courtvision.state_machine import AnalysisStage


class RecordingStage(PipelineStage):
    def __init__(self, target_stage: AnalysisStage, calls: list[str]):
        self.target_stage = target_stage
        self.calls = calls

    def run(self, context: PipelineContext) -> dict[str, object]:
        self.calls.append(self.target_stage.value)
        return {"stage": self.target_stage.value}


class FailingOnceStage(RecordingStage):
    def __init__(self, target_stage: AnalysisStage, calls: list[str]):
        super().__init__(target_stage, calls)
        self.failed = False

    def run(self, context: PipelineContext) -> dict[str, object]:
        self.calls.append(self.target_stage.value)
        if not self.failed:
            self.failed = True
            raise RuntimeError("temporary gpu failure")
        return {"stage": self.target_stage.value}


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository(":memory:", journal_mode="DELETE")
        self.repo.initialize()
        session = self.repo.create_session(title="pipeline test")
        self.job = self.repo.create_job(
            session_id=session["id"],
            source_path="videos/test.mp4",
        )

    def tearDown(self) -> None:
        self.repo.close()

    def test_runs_sequential_stages_and_persists_results(self) -> None:
        calls: list[str] = []
        pipeline = AnalysisPipeline(
            self.repo,
            [
                RecordingStage(AnalysisStage.VALIDATING, calls),
                RecordingStage(AnalysisStage.TRANSCODING, calls),
            ],
        )

        pipeline.run(self.job["id"])

        self.assertEqual(calls, ["validating", "transcoding"])
        self.assertEqual(self.repo.get_job(self.job["id"])["stage"], "transcoding")
        self.assertEqual(
            self.repo.get_result(self.job["id"], "transcoding"),
            {"stage": "transcoding"},
        )

    def test_retries_the_failed_stage_from_checkpoint(self) -> None:
        calls: list[str] = []
        failing = FailingOnceStage(AnalysisStage.VALIDATING, calls)
        pipeline = AnalysisPipeline(self.repo, [failing])

        with self.assertRaisesRegex(RuntimeError, "temporary gpu failure"):
            pipeline.run(self.job["id"])

        failed = self.repo.get_job(self.job["id"])
        self.assertEqual(failed["stage"], "failed")
        self.assertEqual(failed["checkpoint"]["resume_stage"], "validating")

        pipeline.run(self.job["id"])

        self.assertEqual(calls, ["validating", "validating"])
        self.assertEqual(self.repo.get_job(self.job["id"])["stage"], "validating")

    def test_retries_an_active_stage_left_by_process_interruption(self) -> None:
        for index, stage in enumerate(
            (
                AnalysisStage.VALIDATING,
                AnalysisStage.TRANSCODING,
                AnalysisStage.CALIBRATING,
                AnalysisStage.SEGMENTING,
                AnalysisStage.POSE_TRACKING,
                AnalysisStage.SHUTTLE_TRACKING,
            ),
            start=1,
        ):
            self.repo.update_job_stage(
                self.job["id"],
                stage,
                progress=index / 9,
                checkpoint={"active_stage": stage.value},
            )
        calls: list[str] = []
        pipeline = AnalysisPipeline(
            self.repo,
            [
                RecordingStage(AnalysisStage.SHUTTLE_TRACKING, calls),
                RecordingStage(AnalysisStage.EVENT_DETECTION, calls),
            ],
        )

        pipeline.run(self.job["id"])

        self.assertEqual(calls, ["shuttle_tracking", "event_detection"])
        self.assertEqual(
            self.repo.get_result(self.job["id"], "shuttle_tracking"),
            {"stage": "shuttle_tracking"},
        )


if __name__ == "__main__":
    unittest.main()
