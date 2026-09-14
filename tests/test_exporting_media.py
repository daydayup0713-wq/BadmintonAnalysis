from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4

from courtvision.exporting import export_rally_clips, render_overlay_video


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg and ffprobe are required")
class ExportingMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(".test-tmp")
        root.mkdir(parents=True, exist_ok=True)
        self.output = root / f"exporting-media-{uuid4().hex}"
        self.output.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.output, ignore_errors=True)

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

    def _make_video(
        self,
        name: str,
        *,
        with_audio: bool,
        audio_duration: float = 1.0,
        shortest: bool = True,
    ) -> Path:
        output = self.output / name
        command = [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=10:duration=1",
        ]
        if with_audio:
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    (
                        "sine=frequency=1000:sample_rate=48000:"
                        f"duration={audio_duration}"
                    ),
                ]
            )
            if shortest:
                command.append("-shortest")
        command.extend(
            [
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
            ]
        )
        if with_audio:
            command.extend(["-c:a", "aac", "-b:a", "96k"])
        command.append(str(output))
        self._run(command)
        return output

    def _probe(self, path: Path) -> dict:
        completed = self._run(
            [
                str(FFPROBE),
                "-v",
                "error",
                "-show_entries",
                (
                    "format=duration:"
                    "stream=index,codec_type,codec_name,width,height,"
                    "avg_frame_rate,nb_frames,duration"
                ),
                "-of",
                "json",
                str(path),
            ]
        )
        return json.loads(completed.stdout)

    def _audio_hash(self, path: Path) -> str:
        completed = self._run(
            [
                str(FFMPEG),
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-c",
                "copy",
                "-f",
                "hash",
                "-hash",
                "md5",
                "-",
            ]
        )
        return completed.stdout.strip()

    def _render_payloads(self) -> tuple[dict, dict, dict]:
        keypoints = [[80 + index * 2, 50 + index * 3] for index in range(17)]
        summary = {
            "calibration": {
                "court_points": [
                    [80, 70],
                    [240, 70],
                    [70, 120],
                    [250, 120],
                    [50, 220],
                    [270, 220],
                ],
                "net_points": [
                    [60, 100],
                    [60, 145],
                    [260, 145],
                    [260, 100],
                ],
            },
            "metrics": {
                "players": {
                    "top": {
                        "track": [
                            {
                                "frame": 2,
                                "timestamp_us": 200000,
                                "x_m": 2.0,
                                "y_m": 3.0,
                                "speed_mps": 1.0,
                            }
                        ]
                    },
                    "bottom": {"track": []},
                }
            },
        }
        pose = {
            "frames": [
                {
                    "frame": 2,
                    "top_keypoints": keypoints,
                    "bottom_keypoints": None,
                }
            ]
        }
        shuttle = {
            "rallies": [
                {
                    "points": [
                        {
                            "frame": 2,
                            "x": 160,
                            "y": 100,
                            "visible": True,
                        }
                    ]
                }
            ]
        }
        return summary, pose, shuttle

    def test_overlay_preserves_original_aac_packets(self) -> None:
        source = self._make_video("source-with-audio.mp4", with_audio=True)
        summary, pose, shuttle = self._render_payloads()

        output = render_overlay_video(
            source,
            summary,
            pose,
            shuttle,
            self.output / "overlay-audio",
        )

        probe = self._probe(output)
        streams = probe["streams"]
        video_stream = next(
            stream for stream in streams if stream["codec_type"] == "video"
        )
        audio_streams = [
            stream for stream in streams if stream["codec_type"] == "audio"
        ]
        self.assertEqual(video_stream["width"], 600)
        self.assertEqual(video_stream["height"], 240)
        self.assertEqual(len(audio_streams), 1)
        self.assertEqual(audio_streams[0]["codec_name"], "aac")
        self.assertEqual(self._audio_hash(output), self._audio_hash(source))
        self.assertFalse((output.parent / "analysis-silent.mp4").exists())

    def test_overlay_preserves_trailing_aac_packet_after_video_ends(self) -> None:
        source = self._make_video(
            "source-with-trailing-audio.mp4",
            with_audio=True,
            audio_duration=1.05,
            shortest=False,
        )
        summary, pose, shuttle = self._render_payloads()

        output = render_overlay_video(
            source,
            summary,
            pose,
            shuttle,
            self.output / "overlay-trailing-audio",
        )

        self.assertEqual(self._audio_hash(output), self._audio_hash(source))

    def test_overlay_accepts_source_without_audio(self) -> None:
        source = self._make_video("source-silent.mp4", with_audio=False)
        summary, pose, shuttle = self._render_payloads()

        output = render_overlay_video(
            source,
            summary,
            pose,
            shuttle,
            self.output / "overlay-silent",
        )

        streams = self._probe(output)["streams"]
        self.assertEqual(
            [stream["codec_type"] for stream in streams],
            ["video"],
        )

    def test_rally_clip_uses_inclusive_frame_duration(self) -> None:
        source = self._make_video("rally-source.mp4", with_audio=True)

        outputs = export_rally_clips(
            source,
            [{"start_frame": 2, "end_frame": 5}],
            self.output / "clips",
            fps=10.0,
        )

        self.assertEqual(len(outputs), 1)
        probe = self._probe(outputs[0])
        self.assertAlmostEqual(float(probe["format"]["duration"]), 0.4, delta=0.08)
        self.assertEqual(
            {stream["codec_type"] for stream in probe["streams"]},
            {"video", "audio"},
        )

    def test_rally_clip_rejects_invalid_boundaries(self) -> None:
        source = self.output / "unused.mp4"
        cases = [
            (0.0, {"start_frame": 0, "end_frame": 1}, "fps must be positive"),
            (10.0, {"start_frame": -1, "end_frame": 1}, "start_frame"),
            (10.0, {"start_frame": 4, "end_frame": 3}, "end_frame"),
        ]
        for fps, rally, message in cases:
            with self.subTest(fps=fps, rally=rally):
                with self.assertRaisesRegex(ValueError, message):
                    export_rally_clips(
                        source,
                        [rally],
                        self.output / "invalid-clips",
                        fps=fps,
                    )

    def test_empty_rally_export_returns_empty_bundle(self) -> None:
        outputs = export_rally_clips(
            self.output / "unused.mp4",
            rallies=[],
            output_dir=self.output / "empty-clips",
            fps=10.0,
        )

        self.assertEqual(outputs, [])


if __name__ == "__main__":
    unittest.main()
