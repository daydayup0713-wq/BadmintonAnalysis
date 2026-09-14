from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Gate:
    threshold: float
    operator: str
    display_name: str

    def passes(self, value: float) -> bool:
        if self.operator == ">=":
            return value >= self.threshold
        return value <= self.threshold


GATES = {
    "rally_boundary_f1": Gate(0.90, ">=", "Rally boundary F1"),
    "identity_frame_accuracy": Gate(
        0.98,
        ">=",
        "Identity per-frame accuracy",
    ),
    "court_position_median_error_m": Gate(
        0.40,
        "<=",
        "Court position median error (m)",
    ),
    "raw_trajectory_coverage": Gate(
        0.80,
        ">=",
        "Valid-rally raw trajectory coverage",
    ),
    "hit_f1": Gate(0.80, ">=", "Hit F1"),
    "landing_zone_accuracy": Gate(0.80, ">=", "Landing-zone accuracy"),
    "coarse_shot_macro_f1": Gate(0.70, ">=", "Coarse shot macro F1"),
    "pose_pck_0_2": Gate(0.85, ">=", "Pose PCK@0.2"),
}


class EvidenceError(ValueError):
    pass


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{field} must be a finite number")
    return result


def _threshold_payload(name: str) -> dict[str, Any]:
    gate = GATES[name]
    return {
        "operator": gate.operator,
        "value": gate.threshold,
    }


def _missing_result(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": GATES[name].display_name,
        "status": "missing_evidence",
        "value": None,
        "threshold": _threshold_payload(name),
        "details": {"reason": reason},
    }


def _measured_result(
    name: str,
    value: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": GATES[name].display_name,
        "status": "pass" if GATES[name].passes(value) else "fail",
        "value": value,
        "threshold": _threshold_payload(name),
        "details": details,
    }


def _evidence_pair(
    metrics: Mapping[str, Any],
    name: str,
) -> tuple[Any, Any]:
    section = metrics.get(name)
    if not isinstance(section, Mapping):
        raise EvidenceError(f"metrics.{name} is missing")
    if "ground_truth" not in section or section["ground_truth"] is None:
        raise EvidenceError(f"metrics.{name}.ground_truth is missing")
    if "predictions" not in section or section["predictions"] is None:
        raise EvidenceError(f"metrics.{name}.predictions is missing")
    return section["ground_truth"], section["predictions"]


def _event_groups(value: Any, field: str) -> dict[str, list[float]]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{field} must be an object of event lists")
    groups: dict[str, list[float]] = {}
    for group_id, events in value.items():
        if not isinstance(group_id, str) or not _is_sequence(events):
            raise EvidenceError(f"{field} must map string IDs to event lists")
        groups[group_id] = [
            _number(event, f"{field}.{group_id}") for event in events
        ]
    return groups


def _count_event_matches(
    ground_truth: Sequence[float],
    predictions: Sequence[float],
    tolerance: float,
) -> int:
    truth = sorted(ground_truth)
    predicted = sorted(predictions)
    truth_index = 0
    prediction_index = 0
    matched = 0
    while truth_index < len(truth) and prediction_index < len(predicted):
        truth_value = truth[truth_index]
        prediction_value = predicted[prediction_index]
        if prediction_value < truth_value - tolerance:
            prediction_index += 1
        elif truth_value < prediction_value - tolerance:
            truth_index += 1
        else:
            matched += 1
            truth_index += 1
            prediction_index += 1
    return matched


def _event_f1(
    name: str,
    ground_truth_value: Any,
    prediction_value: Any,
    *,
    tolerance: float,
    tolerance_name: str,
) -> dict[str, Any]:
    ground_truth = _event_groups(ground_truth_value, "ground_truth")
    predictions = _event_groups(prediction_value, "predictions")
    true_positives = sum(
        _count_event_matches(
            ground_truth.get(group_id, []),
            predictions.get(group_id, []),
            tolerance,
        )
        for group_id in set(ground_truth) | set(predictions)
    )
    truth_count = sum(len(events) for events in ground_truth.values())
    prediction_count = sum(len(events) for events in predictions.values())
    if truth_count == 0 and prediction_count == 0:
        raise EvidenceError("ground_truth and predictions contain no events")
    false_positives = prediction_count - true_positives
    false_negatives = truth_count - true_positives
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = (
        true_positives / precision_denominator
        if precision_denominator
        else 0.0
    )
    recall = (
        true_positives / recall_denominator if recall_denominator else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return _measured_result(
        name,
        f1,
        {
            tolerance_name: tolerance,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
        },
    )


def _label_mapping(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{field} must be an object of sample labels")
    labels: dict[str, str] = {}
    for sample_id, label in value.items():
        if not isinstance(sample_id, str) or not isinstance(label, str):
            raise EvidenceError(
                f"{field} must map string sample IDs to string labels"
            )
        labels[sample_id] = label
    return labels


def _require_label_overlap(
    ground_truth: Mapping[str, str],
    predictions: Mapping[str, str],
) -> None:
    if not ground_truth:
        raise EvidenceError("ground_truth contains no labeled samples")
    if not set(ground_truth).intersection(predictions):
        raise EvidenceError(
            "predictions contain no sample IDs present in ground_truth"
        )


def _accuracy(
    name: str,
    ground_truth_value: Any,
    prediction_value: Any,
) -> dict[str, Any]:
    ground_truth = _label_mapping(ground_truth_value, "ground_truth")
    predictions = _label_mapping(prediction_value, "predictions")
    _require_label_overlap(ground_truth, predictions)
    correct = sum(
        predictions.get(sample_id) == expected
        for sample_id, expected in ground_truth.items()
    )
    sample_count = len(ground_truth)
    return _measured_result(
        name,
        correct / sample_count,
        {
            "sample_count": sample_count,
            "correct_count": correct,
            "missing_prediction_count": sum(
                sample_id not in predictions for sample_id in ground_truth
            ),
        },
    )


def _point(value: Any, field: str) -> tuple[float, float]:
    if not _is_sequence(value) or len(value) != 2:
        raise EvidenceError(f"{field} must be a two-number point")
    return (
        _number(value[0], f"{field}[0]"),
        _number(value[1], f"{field}[1]"),
    )


def _point_mapping(
    value: Any,
    field: str,
) -> dict[str, tuple[float, float]]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{field} must be an object of sample points")
    points: dict[str, tuple[float, float]] = {}
    for sample_id, point_value in value.items():
        if not isinstance(sample_id, str):
            raise EvidenceError(f"{field} sample IDs must be strings")
        points[sample_id] = _point(
            point_value,
            f"{field}.{sample_id}",
        )
    return points


def _court_position_error(
    ground_truth_value: Any,
    prediction_value: Any,
) -> dict[str, Any]:
    ground_truth = _point_mapping(ground_truth_value, "ground_truth")
    predictions = _point_mapping(prediction_value, "predictions")
    if not ground_truth:
        raise EvidenceError("ground_truth contains no court-position samples")
    missing = sorted(set(ground_truth) - set(predictions))
    if missing:
        raise EvidenceError(
            f"predictions are missing {len(missing)} ground-truth samples"
        )
    errors = [
        math.dist(point, predictions[sample_id])
        for sample_id, point in ground_truth.items()
    ]
    return _measured_result(
        "court_position_median_error_m",
        statistics.median(errors),
        {
            "sample_count": len(errors),
            "minimum_error_m": min(errors),
            "maximum_error_m": max(errors),
        },
    )


def _id_groups(value: Any, field: str) -> dict[str, set[str]]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{field} must be an object of sample-ID lists")
    groups: dict[str, set[str]] = {}
    for group_id, sample_ids in value.items():
        if not isinstance(group_id, str) or not _is_sequence(sample_ids):
            raise EvidenceError(
                f"{field} must map string IDs to sample-ID lists"
            )
        if any(not isinstance(sample_id, str) for sample_id in sample_ids):
            raise EvidenceError(f"{field} sample IDs must be strings")
        groups[group_id] = set(sample_ids)
    return groups


def _raw_trajectory_coverage(
    ground_truth_value: Any,
    prediction_value: Any,
) -> dict[str, Any]:
    ground_truth = _id_groups(ground_truth_value, "ground_truth")
    predictions = _id_groups(prediction_value, "predictions")
    expected = {
        (group_id, sample_id)
        for group_id, sample_ids in ground_truth.items()
        for sample_id in sample_ids
    }
    if not expected:
        raise EvidenceError("ground_truth contains no valid-rally samples")
    detected = {
        (group_id, sample_id)
        for group_id, sample_ids in predictions.items()
        for sample_id in sample_ids
    }
    detected_expected = expected.intersection(detected)
    return _measured_result(
        "raw_trajectory_coverage",
        len(detected_expected) / len(expected),
        {
            "expected_raw_sample_count": len(expected),
            "detected_raw_sample_count": len(detected_expected),
            "unexpected_prediction_count": len(detected - expected),
        },
    )


def _coarse_shot_macro_f1(
    ground_truth_value: Any,
    prediction_value: Any,
) -> dict[str, Any]:
    ground_truth = _label_mapping(ground_truth_value, "ground_truth")
    predictions = _label_mapping(prediction_value, "predictions")
    _require_label_overlap(ground_truth, predictions)
    classes = sorted(
        set(ground_truth.values())
        | {
            predictions[sample_id]
            for sample_id in ground_truth
            if sample_id in predictions
        }
    )
    per_class: dict[str, dict[str, Any]] = {}
    for label in classes:
        true_positives = sum(
            expected == label and predictions.get(sample_id) == label
            for sample_id, expected in ground_truth.items()
        )
        false_positives = sum(
            expected != label and predictions.get(sample_id) == label
            for sample_id, expected in ground_truth.items()
        )
        false_negatives = sum(
            expected == label and predictions.get(sample_id) != label
            for sample_id, expected in ground_truth.items()
        )
        denominator = (
            2 * true_positives + false_positives + false_negatives
        )
        f1 = 2 * true_positives / denominator if denominator else 0.0
        per_class[label] = {
            "f1": f1,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "support": sum(
                expected == label for expected in ground_truth.values()
            ),
        }
    macro_f1 = statistics.mean(
        class_result["f1"] for class_result in per_class.values()
    )
    return _measured_result(
        "coarse_shot_macro_f1",
        macro_f1,
        {
            "sample_count": len(ground_truth),
            "class_count": len(classes),
            "missing_prediction_count": sum(
                sample_id not in predictions for sample_id in ground_truth
            ),
            "per_class": per_class,
        },
    )


def _pose_ground_truth(
    value: Any,
) -> dict[str, tuple[tuple[float, float], float]]:
    if not isinstance(value, Mapping):
        raise EvidenceError("ground_truth must be an object of pose keypoints")
    samples: dict[str, tuple[tuple[float, float], float]] = {}
    for sample_id, sample in value.items():
        if not isinstance(sample_id, str) or not isinstance(sample, Mapping):
            raise EvidenceError(
                "pose ground_truth must map string IDs to point records"
            )
        if "point" not in sample or "reference_length" not in sample:
            raise EvidenceError(
                f"ground_truth.{sample_id} requires point and reference_length"
            )
        reference_length = _number(
            sample["reference_length"],
            f"ground_truth.{sample_id}.reference_length",
        )
        if reference_length <= 0:
            raise EvidenceError("pose reference_length must be greater than 0")
        samples[sample_id] = (
            _point(sample["point"], f"ground_truth.{sample_id}.point"),
            reference_length,
        )
    return samples


def _pose_pck(
    ground_truth_value: Any,
    prediction_value: Any,
) -> dict[str, Any]:
    ground_truth = _pose_ground_truth(ground_truth_value)
    predictions = _point_mapping(prediction_value, "predictions")
    if not ground_truth:
        raise EvidenceError("ground_truth contains no pose keypoints")
    missing = sorted(set(ground_truth) - set(predictions))
    if missing:
        raise EvidenceError(
            f"predictions are missing {len(missing)} pose keypoints"
        )
    correct = 0
    for sample_id, (expected, reference_length) in ground_truth.items():
        distance = math.dist(expected, predictions[sample_id])
        if distance <= 0.2 * reference_length + 1e-12:
            correct += 1
    return _measured_result(
        "pose_pck_0_2",
        correct / len(ground_truth),
        {
            "normalization_fraction": 0.2,
            "keypoint_count": len(ground_truth),
            "correct_keypoint_count": correct,
        },
    )


Evaluator = Callable[[Any, Any], dict[str, Any]]


EVALUATORS: dict[str, Evaluator] = {
    "rally_boundary_f1": lambda ground_truth, predictions: _event_f1(
        "rally_boundary_f1",
        ground_truth,
        predictions,
        tolerance=1.0,
        tolerance_name="tolerance_seconds",
    ),
    "identity_frame_accuracy": lambda ground_truth, predictions: _accuracy(
        "identity_frame_accuracy",
        ground_truth,
        predictions,
    ),
    "court_position_median_error_m": _court_position_error,
    "raw_trajectory_coverage": _raw_trajectory_coverage,
    "hit_f1": lambda ground_truth, predictions: _event_f1(
        "hit_f1",
        ground_truth,
        predictions,
        tolerance=3.0,
        tolerance_name="tolerance_frames",
    ),
    "landing_zone_accuracy": lambda ground_truth, predictions: _accuracy(
        "landing_zone_accuracy",
        ground_truth,
        predictions,
    ),
    "coarse_shot_macro_f1": _coarse_shot_macro_f1,
    "pose_pck_0_2": _pose_pck,
}


def evaluate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be a JSON object")
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest.schema_version must be 1")
    metrics = manifest.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("manifest.metrics must be a JSON object")

    results: dict[str, dict[str, Any]] = {}
    for name, evaluator in EVALUATORS.items():
        try:
            ground_truth, predictions = _evidence_pair(metrics, name)
            results[name] = evaluator(ground_truth, predictions)
        except (EvidenceError, TypeError, ValueError) as error:
            results[name] = _missing_result(name, str(error))

    summary = {
        "passed": sum(
            result["status"] == "pass" for result in results.values()
        ),
        "failed": sum(
            result["status"] == "fail" for result in results.values()
        ),
        "missing_evidence": sum(
            result["status"] == "missing_evidence"
            for result in results.values()
        ),
    }
    if summary["missing_evidence"]:
        status = "missing_evidence"
    elif summary["failed"]:
        status = "fail"
    else:
        status = "pass"
    return {
        "schema_version": 1,
        "status": status,
        "passed": status == "pass",
        "summary": summary,
        "metrics": results,
    }
