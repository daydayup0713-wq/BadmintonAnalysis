from __future__ import annotations

import unittest

from courtvision.acceptance import av_sync_delta, validate_long_video_probe


class AcceptanceTests(unittest.TestCase):
    def test_accepts_sixty_minute_probe_with_synced_streams(self) -> None:
        probe = {
            "format": {"duration": "3600.04"},
            "streams": [
                {"codec_type": "video", "duration": "3600.00"},
                {"codec_type": "audio", "duration": "3600.03"},
            ],
        }

        validate_long_video_probe(probe)

        self.assertAlmostEqual(av_sync_delta(probe), 0.03)

    def test_rejects_short_acceptance_video(self) -> None:
        with self.assertRaisesRegex(ValueError, "60 minutes"):
            validate_long_video_probe(
                {
                    "format": {"duration": "3590"},
                    "streams": [
                        {"codec_type": "video", "duration": "3590"},
                        {"codec_type": "audio", "duration": "3590"},
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
