from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
