from __future__ import annotations

from typing import Any, Sequence


def classify_court_zone(
    point: Sequence[float],
    court_points: Sequence[Sequence[float]],
) -> dict[str, Any]:
    if len(court_points) != 6:
        raise ValueError("court zone classification requires six court points")
    top_y = (court_points[0][1] + court_points[1][1]) / 2
    bottom_y = (court_points[4][1] + court_points[5][1]) / 2
    height = max(bottom_y - top_y, 1e-6)
    y_ratio = (point[1] - top_y) / height
    interpolation = min(max(y_ratio, 0.0), 1.0)
    left_x = court_points[0][0] + (
        court_points[4][0] - court_points[0][0]
    ) * interpolation
    right_x = court_points[1][0] + (
        court_points[5][0] - court_points[1][0]
    ) * interpolation
    width = max(right_x - left_x, 1e-6)
    x_ratio = (point[0] - left_x) / width
    in_court = 0.0 <= y_ratio <= 1.0 and 0.0 <= x_ratio <= 1.0
    court_side = "top" if y_ratio < 0.5 else "bottom"
    if x_ratio < 1 / 3:
        lateral = "left"
    elif x_ratio > 2 / 3:
        lateral = "right"
    else:
        lateral = "center"
    distance_from_net = abs(y_ratio - 0.5) * 2
    if distance_from_net < 0.25:
        longitudinal = "front"
    elif distance_from_net >= 0.5:
        longitudinal = "rear"
    else:
        longitudinal = "mid"
    return {
        "in_court": in_court,
        "court_side": court_side,
        "lateral": lateral,
        "longitudinal": longitudinal,
        "zone": f"{court_side}-{longitudinal}-{lateral}",
        "x_ratio": round(x_ratio, 4),
        "y_ratio": round(y_ratio, 4),
    }


def _visible_points(
    points: list[dict[str, Any]],
    start_frame: int,
    end_frame: int,
) -> list[dict[str, Any]]:
    return [
        point
        for point in points
        if start_frame <= point["frame"] <= end_frame
        and point.get("visible", True)
        and (point.get("x", 0) != 0 or point.get("y", 0) != 0)
    ]


def _hitter_phase(label: str) -> str:
    if label in {"smash", "drive", "net_or_drop", "drop_or_push"}:
        return "attack"
    if label == "unknown":
        return "unknown"
    return "neutral"


def enrich_rally_tactics(
    rallies: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    tracks: list[dict[str, Any]],
    court_points: Sequence[Sequence[float]],
) -> dict[str, list[dict[str, Any]]]:
    all_points = sorted(
        (
            point
            for rally_track in tracks
            for point in rally_track.get("points", [])
        ),
        key=lambda item: item["frame"],
    )
    enriched_shots: list[dict[str, Any]] = []
    enriched_rallies: list[dict[str, Any]] = []
    for rally_index, boundary in enumerate(rallies, start=1):
        rally_id = boundary.get("id", f"rally-{rally_index}")
        rally_shots = [
            shot
            for shot in shots
            if boundary["start_frame"]
            <= shot["hit_frame"]
            <= boundary["end_frame"]
        ]
        player_phases = {"top": "unknown", "bottom": "unknown"}
        phase_transitions: list[dict[str, Any]] = []
        for shot_index, shot in enumerate(rally_shots):
            next_frame = (
                rally_shots[shot_index + 1]["hit_frame"] - 1
                if shot_index + 1 < len(rally_shots)
                else boundary["end_frame"]
            )
            segment = _visible_points(
                all_points,
                shot["hit_frame"],
                next_frame,
            )
            start_zone = None
            landing_zone = None
            if segment:
                start_zone = classify_court_zone(
                    [segment[0]["x"], segment[0]["y"]],
                    court_points,
                )
                landing_zone = classify_court_zone(
                    [segment[-1]["x"], segment[-1]["y"]],
                    court_points,
                )
            hitter = shot.get("player", "unknown")
            hitter_phase = _hitter_phase(str(shot.get("label", "unknown")))
            opponent = (
                "bottom"
                if hitter == "top"
                else "top" if hitter == "bottom" else "unknown"
            )
            opponent_phase = (
                "defense" if hitter_phase == "attack" else "neutral"
            )
            for player, phase in (
                (hitter, hitter_phase),
                (opponent, opponent_phase),
            ):
                if player not in player_phases or phase == "unknown":
                    continue
                previous_phase = player_phases[player]
                if (
                    previous_phase in {"attack", "defense"}
                    and phase in {"attack", "defense"}
                    and previous_phase != phase
                ):
                    phase_transitions.append(
                        {
                            "frame": shot["hit_frame"],
                            "timestamp_us": shot.get("timestamp_us"),
                            "player": player,
                            "from_phase": previous_phase,
                            "to_phase": phase,
                            "confidence": shot.get("confidence", 0.0),
                        }
                    )
                player_phases[player] = phase
            enriched_shots.append(
                {
                    **shot,
                    "id": shot.get("id", f"shot-{shot['hit_frame']}"),
                    "rally_id": rally_id,
                    "start_zone": start_zone,
                    "landing_zone": landing_zone,
                    "hitter_phase": hitter_phase,
                    "opponent_phase": opponent_phase,
                }
            )

        winner = "unknown"
        outcome_confidence = 0.2
        outcome_reason = "insufficient trajectory"
        if rally_shots:
            final_shot = next(
                item
                for item in reversed(enriched_shots)
                if item["rally_id"] == rally_id
            )
            landing = final_shot.get("landing_zone")
            hitter = final_shot.get("player", "unknown")
            if landing and hitter in {"top", "bottom"}:
                opponent = "bottom" if hitter == "top" else "top"
                if not landing["in_court"]:
                    winner = opponent
                    outcome_reason = "final trajectory leaves court"
                    outcome_confidence = 0.35
                elif landing["court_side"] == opponent:
                    winner = hitter
                    outcome_reason = "unreturned final shot lands on opponent side"
                    outcome_confidence = 0.55
                else:
                    winner = opponent
                    outcome_reason = "final shot remains on hitter side"
                    outcome_confidence = 0.4
        enriched_rallies.append(
            {
                **boundary,
                "id": rally_id,
                "winner_candidate": winner,
                "confidence": min(
                    float(boundary.get("confidence", 0.5)),
                    outcome_confidence,
                ),
                "outcome_reason": outcome_reason,
                "phase_transitions": phase_transitions,
                "origin": boundary.get("origin", "model"),
            }
        )
    return {"shots": enriched_shots, "rallies": enriched_rallies}
