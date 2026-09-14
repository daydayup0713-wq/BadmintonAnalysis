from __future__ import annotations

import unittest

from courtvision.state_machine import (
    AnalysisStage,
    InvalidStageTransition,
    next_stage,
    validate_transition,
)


class AnalysisStateMachineTests(unittest.TestCase):
    def test_happy_path_matches_product_pipeline(self) -> None:
        stage = AnalysisStage.UPLOADED
        expected = [
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
        ]

        actual = []
        while stage is not AnalysisStage.COMPLETED:
            stage = next_stage(stage)
            actual.append(stage)

        self.assertEqual(actual, expected)

    def test_cannot_skip_pipeline_stage(self) -> None:
        with self.assertRaises(InvalidStageTransition):
            validate_transition(
                AnalysisStage.UPLOADED,
                AnalysisStage.SHUTTLE_TRACKING,
            )

    def test_failed_job_can_retry_same_stage(self) -> None:
        validate_transition(
            AnalysisStage.FAILED,
            AnalysisStage.RETRYING,
        )

    def test_interrupted_active_stage_can_enter_retrying(self) -> None:
        validate_transition(
            AnalysisStage.SHUTTLE_TRACKING,
            AnalysisStage.RETRYING,
        )

    def test_uploaded_job_can_wait_for_external_results(self) -> None:
        validate_transition(
            AnalysisStage.UPLOADED,
            AnalysisStage.AWAITING_RESULTS,
        )

    def test_waiting_job_can_start_platform_metrics(self) -> None:
        validate_transition(
            AnalysisStage.AWAITING_RESULTS,
            AnalysisStage.METRICS,
        )

    def test_waiting_job_cannot_skip_directly_to_review(self) -> None:
        with self.assertRaises(InvalidStageTransition):
            validate_transition(
                AnalysisStage.AWAITING_RESULTS,
                AnalysisStage.REVIEW_REQUIRED,
            )


if __name__ == "__main__":
    unittest.main()
