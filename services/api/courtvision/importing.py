from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .biomechanics import build_swing_metrics
from .contracts import DataOrigin, PlayerPoseFrame
from .metrics import build_player_movement_metrics
from .repository import Repository
from .state_machine import AnalysisStage


def _validate_keypoints(
    keypoints: list[list[float]] | None,
) -> list[list[float]] | None:
    if keypoints is None:
        return None
    if len(keypoints) != 17:
        raise ValueError("player pose requires exactly 17 keypoints")
    for point in keypoints:
        if len(point) != 2:
            raise ValueError("each keypoint requires finite x and y coordinates")
        if not all(math.isfinite(coordinate) for coordinate in point):
            raise ValueError("each keypoint requires finite x and y coordinates")
    return keypoints


def _validate_point_collection(
    points: list[list[float]] | None,
    *,
    required: int,
    label: str,
) -> list[list[float]] | None:
    if points is None:
        return None
    if len(points) != required:
        raise ValueError(f"{label} requires exactly {required} points")
    for point in points:
        if len(point) != 2 or not all(
            math.isfinite(coordinate) for coordinate in point
        ):
            raise ValueError(f"{label} points require finite x and y coordinates")
    return points


def _validate_nested_observations(
    value: Any,
    *,
    total_frames: int,
) -> None:
    if isinstance(value, list):
        for item in value:
            _validate_nested_observations(item, total_frames=total_frames)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key == "confidence":
            if (
                not isinstance(item, (int, float))
                or isinstance(item, bool)
                or not math.isfinite(float(item))
                or not 0 <= float(item) <= 1
            ):
                raise ValueError("confidence must be between 0 and 1")
        if key in {"frame", "start_frame", "end_frame", "hit_frame"}:
            if (
                not isinstance(item, int)
                or isinstance(item, bool)
                or not 0 <= item < total_frames
            ):
                raise ValueError("frame must be inside the imported video")
        _validate_nested_observations(item, total_frames=total_frames)


class VideoImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fps: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    total_frames: int = Field(gt=0)
    duration_seconds: float = Field(gt=0)


class PoseImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame: int = Field(ge=0)
    timestamp_us: int = Field(ge=0)
    top_keypoints: list[list[float]] | None = None
    bottom_keypoints: list[list[float]] | None = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("top_keypoints", "bottom_keypoints")
    @classmethod
    def validate_keypoints(
        cls,
        value: list[list[float]] | None,
    ) -> list[list[float]] | None:
        return _validate_keypoints(value)


class ExternalAnalysisImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    provider_version: str = Field(min_length=1, max_length=100)
    video: VideoImport
    court_points: list[list[float]] | None = None
    net_points: list[list[float]] | None = None
    rallies: list[dict[str, Any]] = Field(default_factory=list)
    poses: list[PoseImport] = Field(default_factory=list)
    shuttle: list[dict[str, Any]] = Field(default_factory=list)
    hits: list[dict[str, Any]] = Field(default_factory=list)
    shots: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("provider", "provider_version")
    @classmethod
    def require_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider identity must not be blank")
        return normalized

    @field_validator("court_points")
    @classmethod
    def validate_court_points(
        cls,
        value: list[list[float]] | None,
    ) -> list[list[float]] | None:
        return _validate_point_collection(
            value,
            required=6,
            label="court calibration",
        )

    @field_validator("net_points")
    @classmethod
    def validate_net_points(
        cls,
        value: list[list[float]] | None,
    ) -> list[list[float]] | None:
        return _validate_point_collection(
            value,
            required=4,
            label="net calibration",
        )

    @model_validator(mode="after")
    def validate_observations(self) -> "ExternalAnalysisImport":
        total_frames = self.video.total_frames
        for pose in self.poses:
            if pose.frame >= total_frames:
                raise ValueError("pose frame must be inside the imported video")
        for collection in (self.rallies, self.shuttle, self.hits, self.shots):
            _validate_nested_observations(
                collection,
                total_frames=total_frames,
            )
        return self


def _missing_evidence(payload: ExternalAnalysisImport) -> list[str]:
    missing = []
    if not payload.poses:
        missing.append("pose")
    if not payload.court_points or len(payload.court_points) < 6:
        missing.append("court_calibration")
    if not payload.shuttle:
        missing.append("shuttle_trajectory")
    if not payload.hits:
        missing.append("hit_events")
    if not payload.shots:
        missing.append("shot_classification")
    return missing


def import_external_results(
    repository: Repository,
    job_id: str,
    payload: ExternalAnalysisImport,
) -> dict[str, Any]:
    provenance = {
        "provider": payload.provider,
        "provider_version": payload.provider_version,
    }
    repository.get_job(job_id)
    repository.save_result(
        job_id=job_id,
        kind="external_import",
        payload=provenance,
    )
    repository.save_result(
        job_id=job_id,
        kind="validating",
        payload=payload.video.model_dump(),
    )
    repository.save_result(
        job_id=job_id,
        kind="calibrating",
        payload={
            "court_points": payload.court_points,
            "net_points": payload.net_points,
            "origin": DataOrigin.EXTERNAL.value,
            **provenance,
        },
    )
    repository.save_result(
        job_id=job_id,
        kind="segmenting",
        payload={
            "rallies": payload.rallies,
            "origin": DataOrigin.EXTERNAL.value,
        },
    )

    pose_frames = [
        PlayerPoseFrame(
            frame=pose.frame,
            timestamp_us=pose.timestamp_us,
            top_keypoints=pose.top_keypoints,
            bottom_keypoints=pose.bottom_keypoints,
            confidence=pose.confidence,
            provider_version=(
                f"{payload.provider}:{payload.provider_version}"
            ),
            origin=DataOrigin.EXTERNAL,
        )
        for pose in payload.poses
    ]
    normalized_poses = [
        {
            "frame": pose.frame,
            "timestamp_us": pose.timestamp_us,
            "top_keypoints": pose.top_keypoints,
            "bottom_keypoints": pose.bottom_keypoints,
            "confidence": pose.confidence,
            "provider": payload.provider,
            "provider_version": payload.provider_version,
            "origin": DataOrigin.EXTERNAL.value,
        }
        for pose in pose_frames
    ]
    repository.save_result(
        job_id=job_id,
        kind="pose_tracking",
        payload={"frames": normalized_poses, "identities": []},
    )
    repository.save_result(
        job_id=job_id,
        kind="shuttle_tracking",
        payload={
            "points": payload.shuttle,
            "origin": DataOrigin.EXTERNAL.value,
        },
    )
    repository.save_result(
        job_id=job_id,
        kind="event_detection",
        payload={
            "rallies": payload.rallies,
            "hits": payload.hits,
            "shots": payload.shots,
            "origin": DataOrigin.EXTERNAL.value,
        },
    )

    can_calculate = bool(pose_frames and payload.court_points)
    metrics: dict[str, Any] = {
        "available": can_calculate,
        "missing_evidence": _missing_evidence(payload),
    }
    if can_calculate:
        assert payload.court_points is not None
        metrics.update(
            {
                "players": build_player_movement_metrics(
                    pose_frames,
                    payload.court_points,
                    fps=payload.video.fps,
                ),
                "swings": build_swing_metrics(
                    pose_frames,
                    payload.hits,
                    payload.court_points,
                    fps=payload.video.fps,
                    duration_seconds=payload.video.duration_seconds,
                ),
            }
        )
    repository.save_result(
        job_id=job_id,
        kind="metrics",
        payload=metrics,
    )

    missing_evidence = _missing_evidence(payload)
    review = {
        "status": AnalysisStage.REVIEW_REQUIRED.value,
        "missing_evidence": missing_evidence,
        "issue_count": len(missing_evidence),
    }
    repository.save_result(
        job_id=job_id,
        kind="review_required",
        payload=review,
    )
    checkpoint = {**provenance, "imported": True}
    repository.update_job_stage(
        job_id,
        AnalysisStage.METRICS,
        progress=0.9,
        checkpoint=checkpoint,
    )
    return repository.update_job_stage(
        job_id,
        AnalysisStage.REVIEW_REQUIRED,
        progress=0.95,
        checkpoint=checkpoint,
    )
