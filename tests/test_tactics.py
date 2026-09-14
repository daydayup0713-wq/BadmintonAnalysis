from __future__ import annotations

import unittest

from courtvision.tactics import (
    classify_court_zone,
    enrich_rally_tactics,
)


COURT = [
    [100, 100],
    [500, 100],
    [90, 300],
    [510, 300],
    [80, 600],
    [520, 600],
]


class TacticsTests(unittest.TestCase):
    def test_classifies_point_into_player_side_and_grid_zone(self) -> None:
        zone = classify_court_zone([300, 500], COURT)

        self.assertEqual(zone["court_side"], "bottom")
        self.assertEqual(zone["longitudinal"], "rear")
        self.assertEqual(zone["lateral"], "center")
        self.assertTrue(zone["in_court"])

    def test_enriches_shots_and_rally_winner_candidate(self) -> None:
        rallies = [
            {
                "start_frame": 0,
                "end_frame": 30,
                "start_timestamp_us": 0,
                "end_timestamp_us": 1_000_000,
            }
        ]
        shots = [
            {
                "id": "shot-5",
                "hit_frame": 5,
                "timestamp_us": 166_667,
                "player": "top",
                "label": "smash",
                "confidence": 0.6,
            }
        ]
        tracks = [
            {
                "name": "rally-1",
                "points": [
                    {"frame": 5, "x": 300, "y": 180, "visible": True},
                    {"frame": 20, "x": 300, "y": 520, "visible": True},
                    {"frame": 30, "x": 305, "y": 530, "visible": True},
                ],
            }
        ]

        result = enrich_rally_tactics(rallies, shots, tracks, COURT)

        self.assertEqual(result["shots"][0]["landing_zone"]["court_side"], "bottom")
        self.assertEqual(result["rallies"][0]["winner_candidate"], "top")
        self.assertLess(result["rallies"][0]["confidence"], 0.7)

    def test_records_attack_defense_transition(self) -> None:
        rallies = [{"start_frame": 0, "end_frame": 30}]
        shots = [
            {
                "id": "shot-5",
                "hit_frame": 5,
                "timestamp_us": 166_667,
                "player": "top",
                "label": "smash",
                "confidence": 0.8,
            },
            {
                "id": "shot-15",
                "hit_frame": 15,
                "timestamp_us": 500_000,
                "player": "bottom",
                "label": "drive",
                "confidence": 0.8,
            },
        ]
        tracks = [
            {
                "points": [
                    {"frame": 5, "x": 300, "y": 180, "visible": True},
                    {"frame": 14, "x": 300, "y": 520, "visible": True},
                    {"frame": 15, "x": 300, "y": 520, "visible": True},
                    {"frame": 30, "x": 300, "y": 180, "visible": True},
                ]
            }
        ]

        result = enrich_rally_tactics(rallies, shots, tracks, COURT)

        self.assertEqual(result["shots"][0]["hitter_phase"], "attack")
        self.assertEqual(result["shots"][0]["opponent_phase"], "defense")
        self.assertEqual(
            result["rallies"][0]["phase_transitions"][0]["player"],
            "bottom",
        )
        self.assertEqual(
            result["rallies"][0]["phase_transitions"][0]["from_phase"],
            "defense",
        )
        self.assertEqual(
            result["rallies"][0]["phase_transitions"][0]["to_phase"],
            "attack",
        )


if __name__ == "__main__":
    unittest.main()
