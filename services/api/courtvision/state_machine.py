from __future__ import annotations

from enum import Enum


class AnalysisStage(str, Enum):
    UPLOADED = "uploaded"
    AWAITING_RESULTS = "awaiting_results"
    VALIDATING = "validating"
    TRANSCODING = "transcoding"
    CALIBRATING = "calibrating"
    SEGMENTING = "segmenting"
    POSE_TRACKING = "pose_tracking"
    SHUTTLE_TRACKING = "shuttle_tracking"
    EVENT_DETECTION = "event_detection"
    METRICS = "metrics"
    REVIEW_REQUIRED = "review_required"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    RETRYING = "retrying"


class InvalidStageTransition(ValueError):
    pass


PIPELINE = (
    AnalysisStage.UPLOADED,
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
)


def next_stage(stage: AnalysisStage) -> AnalysisStage:
    if stage not in PIPELINE:
        raise InvalidStageTransition(f"{stage.value} has no pipeline successor")
    index = PIPELINE.index(stage)
    if index == len(PIPELINE) - 1:
        return AnalysisStage.COMPLETED
    return PIPELINE[index + 1]


def validate_transition(current: AnalysisStage, target: AnalysisStage) -> None:
    if (
        current is AnalysisStage.UPLOADED
        and target is AnalysisStage.AWAITING_RESULTS
    ):
        return
    if (
        current is AnalysisStage.AWAITING_RESULTS
        and target is AnalysisStage.METRICS
    ):
        return
    if current is AnalysisStage.FAILED and target is AnalysisStage.RETRYING:
        return
    if current in PIPELINE and target is AnalysisStage.RETRYING:
        return
    if current is AnalysisStage.RETRYING and target in PIPELINE:
        return
    if target in {AnalysisStage.FAILED, AnalysisStage.CANCELED}:
        return
    if current in PIPELINE and target is next_stage(current):
        return
    raise InvalidStageTransition(
        f"cannot transition from {current.value} to {target.value}"
    )
