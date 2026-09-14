from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

try:
    from courtvision.evaluation import evaluate_manifest
except ModuleNotFoundError:
    evaluate_manifest = None


def passing_manifest() -> dict:
    return {
        "schema_version": 1,
        "metrics": {
            "rally_boundary_f1": {
                "ground_truth": {"match-1": [10.0, 20.0]},
                "predictions": {"match-1": [10.8, 21.0]},
            },
            "identity_frame_accuracy": {
                "ground_truth": {
                    "match-1:100:near": "player-a",
                    "match-1:100:far": "player-b",
                },
                "predictions": {
                    "match-1:100:near": "player-a",
                    "match-1:100:far": "player-b",
                },
            },
            "court_position_median_error_m": {
                "ground_truth": {
                    "match-1:100:near": [1.0, 2.0],
                    "match-1:100:far": [4.0, 5.0],
                },
                "predictions": {
                    "match-1:100:near": [1.3, 2.0],
                    "match-1:100:far": [4.0, 5.4],
                },
            },
            "raw_trajectory_coverage": {
                "ground_truth": {
                    "match-1:rally-1": ["100", "101", "102", "103", "104"]
                },
                "predictions": {
                    "match-1:rally-1": ["100", "101", "102", "103"]
                },
            },
            "hit_f1": {
                "ground_truth": {"match-1": [100, 200]},
                "predictions": {"match-1": [97, 203]},
            },
            "landing_zone_accuracy": {
                "ground_truth": {
                    "match-1:rally-1": "rear-left",
                    "match-1:rally-2": "front-right",
                },
                "predictions": {
                    "match-1:rally-1": "rear-left",
                    "match-1:rally-2": "front-right",
                },
            },
            "coarse_shot_macro_f1": {
                "ground_truth": {
                    "match-1:hit-1": "smash",
                    "match-1:hit-2": "clear",
                    "match-1:hit-3": "drop",
                },
                "predictions": {
                    "match-1:hit-1": "smash",
                    "match-1:hit-2": "clear",
                    "match-1:hit-3": "drop",
                },
            },
            "pose_pck_0_2": {
                "ground_truth": {
                    "match-1:100:near:left-wrist": {
                        "point": [10.0, 10.0],
                        "reference_length": 10.0,
                    },
                    "match-1:100:near:right-wrist": {
                        "point": [20.0, 20.0],
                        "reference_length": 10.0,
                    },
                },
                "predictions": {
                    "match-1:100:near:left-wrist": [12.0, 10.0],
                    "match-1:100:near:right-wrist": [20.0, 21.0],
                },
            },
        },
    }


class EvaluationTests(unittest.TestCase):
    def evaluate(self, manifest: dict) -> dict:
        self.assertIsNotNone(
            evaluate_manifest,
            "courtvision.evaluation.evaluate_manifest is missing",
        )
        return evaluate_manifest(manifest)

    def test_reports_all_eight_acceptance_metrics_as_passed(self) -> None:
        report = self.evaluate(passing_manifest())

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"], {
            "passed": 8,
            "failed": 0,
            "missing_evidence": 0,
        })
        self.assertEqual(len(report["metrics"]), 8)
        self.assertAlmostEqual(
            report["metrics"]["rally_boundary_f1"]["value"],
            1.0,
        )
        self.assertAlmostEqual(
            report["metrics"]["court_position_median_error_m"]["value"],
            0.35,
        )
        self.assertAlmostEqual(
            report["metrics"]["raw_trajectory_coverage"]["value"],
            0.8,
        )
        self.assertAlmostEqual(
            report["metrics"]["pose_pck_0_2"]["value"],
            1.0,
        )

    def test_marks_a_measured_metric_fail_when_it_misses_its_gate(self) -> None:
        manifest = passing_manifest()
        manifest["metrics"]["raw_trajectory_coverage"]["predictions"] = {
            "match-1:rally-1": ["100", "101", "102"]
        }

        report = self.evaluate(manifest)

        metric = report["metrics"]["raw_trajectory_coverage"]
        self.assertEqual(metric["status"], "fail")
        self.assertAlmostEqual(metric["value"], 0.6)
        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["passed"])

    def test_marks_absent_ground_truth_or_predictions_as_missing_evidence(self) -> None:
        manifest = passing_manifest()
        del manifest["metrics"]["pose_pck_0_2"]["predictions"]

        report = self.evaluate(manifest)

        metric = report["metrics"]["pose_pck_0_2"]
        self.assertEqual(metric["status"], "missing_evidence")
        self.assertIsNone(metric["value"])
        self.assertEqual(report["status"], "missing_evidence")
        self.assertFalse(report["passed"])

    def test_does_not_treat_prediction_confidence_as_identity_accuracy(self) -> None:
        manifest = passing_manifest()
        manifest["metrics"]["identity_frame_accuracy"]["predictions"] = {
            "confidence": 0.999
        }

        report = self.evaluate(manifest)

        metric = report["metrics"]["identity_frame_accuracy"]
        self.assertEqual(metric["status"], "missing_evidence")
        self.assertIsNone(metric["value"])

    def test_event_f1_uses_one_to_one_matches_at_inclusive_tolerances(self) -> None:
        manifest = passing_manifest()
        manifest["metrics"]["rally_boundary_f1"] = {
            "ground_truth": {"match-1": [10.0, 20.0, 30.0]},
            "predictions": {"match-1": [9.0, 21.0, 40.0]},
        }
        manifest["metrics"]["hit_f1"] = {
            "ground_truth": {"match-1": [100, 200, 300]},
            "predictions": {"match-1": [97, 203, 400]},
        }

        report = self.evaluate(manifest)

        rally = report["metrics"]["rally_boundary_f1"]
        hit = report["metrics"]["hit_f1"]
        self.assertAlmostEqual(rally["value"], 2 / 3)
        self.assertEqual(rally["details"]["tolerance_seconds"], 1.0)
        self.assertEqual(rally["details"]["true_positives"], 2)
        self.assertAlmostEqual(hit["value"], 2 / 3)
        self.assertEqual(hit["details"]["tolerance_frames"], 3)
        self.assertEqual(hit["details"]["true_positives"], 2)


class EvaluationCliTests(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]

    def setUp(self) -> None:
        self.case_root = (
            self.repo_root
            / ".test-tmp"
            / "evaluation-cli-tests"
            / self._testMethodName
        )
        self.case_root.mkdir(parents=True, exist_ok=True)

    def run_cli(self, manifest: dict) -> subprocess.CompletedProcess:
        manifest_path = self.case_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                str(self.repo_root / "scripts" / "evaluate_acceptance.py"),
                str(manifest_path),
            ],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_emits_json_and_returns_zero_only_when_all_gates_pass(self) -> None:
        result = self.run_cli(passing_manifest())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

    def test_cli_distinguishes_failed_and_missing_evidence_reports(self) -> None:
        failed = passing_manifest()
        failed["metrics"]["landing_zone_accuracy"]["predictions"] = {
            "match-1:rally-1": "wrong",
            "match-1:rally-2": "wrong",
        }
        missing = copy.deepcopy(passing_manifest())
        del missing["metrics"]["coarse_shot_macro_f1"]["ground_truth"]

        failed_result = self.run_cli(failed)
        missing_result = self.run_cli(missing)

        self.assertEqual(failed_result.returncode, 1, failed_result.stderr)
        self.assertEqual(json.loads(failed_result.stdout)["status"], "fail")
        self.assertEqual(missing_result.returncode, 2, missing_result.stderr)
        self.assertEqual(
            json.loads(missing_result.stdout)["status"],
            "missing_evidence",
        )


if __name__ == "__main__":
    unittest.main()
