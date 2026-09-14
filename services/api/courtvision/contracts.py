from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class CoordinateSpace(str, Enum):
    SOURCE_PIXEL = "source_pixel"
    PROXY_PIXEL = "proxy_pixel"
    COURT_METER = "court_meter"


class DataOrigin(str, Enum):
    MODEL = "model"
    EXTERNAL = "external"
    INTERPOLATED = "interpolated"
    HUMAN = "human"


class PlayerSide(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    UNKNOWN = "unknown"


def _validate_keypoints(
    keypoints: list[list[float]] | None,
) -> None:
    if keypoints is None:
        return
    if len(keypoints) != 17:
        raise ValueError("player pose requires 17 keypoints")
    if any(len(point) != 2 for point in keypoints):
        raise ValueError("each keypoint requires x and y coordinates")


def _validate_observation(frame: int, timestamp_us: int, confidence: float) -> None:
    if frame < 0:
        raise ValueError("frame must be non-negative")
    if timestamp_us < 0:
        raise ValueError("timestamp_us must be non-negative")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


def _wire_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_wire_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ShuttleTrackPoint:
    frame: int
    timestamp_us: int
    x: float
    y: float
    visible: bool
    confidence: float
    coordinate_space: CoordinateSpace
    model_version: str
    origin: DataOrigin

    def __post_init__(self) -> None:
        _validate_observation(self.frame, self.timestamp_us, self.confidence)
        if not self.model_version.strip():
            raise ValueError("model_version is required")

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class PlayerPoseFrame:
    frame: int
    timestamp_us: int
    top_keypoints: list[list[float]] | None
    bottom_keypoints: list[list[float]] | None
    confidence: float
    model_version: str
    origin: DataOrigin

    def __post_init__(self) -> None:
        _validate_observation(self.frame, self.timestamp_us, self.confidence)
        _validate_keypoints(self.top_keypoints)
        _validate_keypoints(self.bottom_keypoints)
        if not self.model_version.strip():
            raise ValueError("model_version is required")

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class CourtCalibration:
    frame: int
    timestamp_us: int
    court_points: list[list[float]]
    net_points: list[list[float]]
    confidence: float
    model_version: str
    origin: DataOrigin = DataOrigin.MODEL

    def __post_init__(self) -> None:
        _validate_observation(self.frame, self.timestamp_us, self.confidence)
        if len(self.court_points) != 6:
            raise ValueError("court calibration requires six court points")
        if len(self.net_points) != 4:
            raise ValueError("court calibration requires four net points")

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class RallyBoundary:
    start_frame: int
    end_frame: int
    start_timestamp_us: int
    end_timestamp_us: int
    confidence: float
    model_version: str
    origin: DataOrigin = DataOrigin.MODEL

    def __post_init__(self) -> None:
        _validate_observation(
            self.start_frame,
            self.start_timestamp_us,
            self.confidence,
        )
        if self.end_frame <= self.start_frame:
            raise ValueError("rally end_frame must be after start_frame")
        if self.end_timestamp_us <= self.start_timestamp_us:
            raise ValueError("rally end time must be after start time")

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class HitEvent:
    frame: int
    timestamp_us: int
    player: PlayerSide
    confidence: float
    model_version: str
    origin: DataOrigin = DataOrigin.MODEL

    def __post_init__(self) -> None:
        _validate_observation(self.frame, self.timestamp_us, self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class ShotClassification:
    hit_frame: int
    timestamp_us: int
    player: PlayerSide
    label: str
    confidence: float
    model_version: str
    origin: DataOrigin

    def __post_init__(self) -> None:
        _validate_observation(
            self.hit_frame,
            self.timestamp_us,
            self.confidence,
        )
        if not self.label.strip():
            raise ValueError("shot label is required")
        if not self.model_version.strip():
            raise ValueError("model_version is required")

    def to_dict(self) -> dict[str, Any]:
        return _wire_value(asdict(self))


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    message: str
    severity: str
    frame_start: int | None = None
    frame_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
