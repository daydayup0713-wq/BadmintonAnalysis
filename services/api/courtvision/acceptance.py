from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def probe_media(path: str | Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-2000:])
    return json.loads(completed.stdout)


def _stream_duration(probe: dict[str, Any], codec_type: str) -> float:
    streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == codec_type
    ]
    if not streams:
        raise ValueError(f"{codec_type} stream is required")
    value = streams[0].get("duration")
    if value is None:
        value = probe.get("format", {}).get("duration")
    return float(value)


def av_sync_delta(probe: dict[str, Any]) -> float:
    return abs(
        _stream_duration(probe, "video")
        - _stream_duration(probe, "audio")
    )


def validate_long_video_probe(
    probe: dict[str, Any],
    *,
    minimum_seconds: float = 3599.0,
    sync_tolerance_seconds: float = 0.15,
) -> None:
    duration = float(probe.get("format", {}).get("duration", 0))
    if duration < minimum_seconds:
        raise ValueError("acceptance video must be at least 60 minutes")
    delta = av_sync_delta(probe)
    if delta > sync_tolerance_seconds:
        raise ValueError(
            f"audio/video duration delta {delta:.3f}s exceeds tolerance"
        )
