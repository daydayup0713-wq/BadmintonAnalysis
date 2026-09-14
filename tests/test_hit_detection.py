from __future__ import annotations

import unittest

from courtvision.hit_detection import detect_trajectory_turns


class HitDetectionTests(unittest.TestCase):
    def test_detects_a_high_velocity_direction_change(self) -> None:
        x = [10, 20, 30, 40, 50, 40, 30, 20, 10]
        y = [100] * len(x)

        hits = detect_trajectory_turns(
            x,
            y,
            threshold=5,
            window=2,
            closeness=1,
        )

        self.assertEqual(hits, [4])

    def test_merges_nearby_x_and_y_candidates(self) -> None:
        x = [0, 4, 8, 12, 16, 12, 8, 4, 0]
        y = [0, 0, 3, 8, 12, 8, 3, 0, 0]

        hits = detect_trajectory_turns(
            x,
            y,
            threshold=2,
            window=2,
            closeness=2,
        )

        self.assertEqual(hits, [4])


if __name__ == "__main__":
    unittest.main()
