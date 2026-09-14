from __future__ import annotations

import csv
import html
import json
import subprocess
import textwrap
from collections import deque
from pathlib import Path
from typing import Any


SKELETON_EDGES = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)


def export_json_summary(
    summary: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "analysis.json"
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def export_csv_bundle(
    summary: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    shot_path = directory / "shots.csv"
    with shot_path.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "hit_frame",
            "timestamp_us",
            "player",
            "label",
            "confidence",
            "provider_version",
            "origin",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for shot in summary.get("shots", []):
            writer.writerow({field: shot.get(field) for field in fieldnames})

    movement_path = directory / "movement.csv"
    with movement_path.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "player",
            "frame",
            "timestamp_us",
            "x_m",
            "y_m",
            "speed_mps",
            "valid",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        players = (summary.get("metrics") or {}).get("players", {})
        for side in ("top", "bottom"):
            for point in players.get(side, {}).get("track", []):
                row = {"player": side, **point}
                writer.writerow({field: row.get(field) for field in fieldnames})
    return {"shots": shot_path, "movement": movement_path}


def _report_lines(summary: dict[str, Any]) -> list[str]:
    metrics = summary.get("metrics") or {}
    players = metrics.get("players") or {}
    top = players.get("top") or {}
    bottom = players.get("bottom") or {}
    shots = summary.get("shots")
    if shots is None:
        shots = summary.get("hits", [])
    lines = [
        "BadmintonAnalysis Report",
        "",
        (
            "This report was generated locally. Low-confidence results are "
            "candidates and require human review."
        ),
        "",
        "Metric | Top court | Bottom court",
        (
            "Distance (m) | "
            f"{top.get('distance_m', '-')} | {bottom.get('distance_m', '-')}"
        ),
        (
            "Average speed (m/s) | "
            f"{top.get('average_speed_mps', '-')} | "
            f"{bottom.get('average_speed_mps', '-')}"
        ),
        (
            "P95 effective speed (m/s) | "
            f"{top.get('max_effective_speed_mps', '-')} | "
            f"{bottom.get('max_effective_speed_mps', '-')}"
        ),
        f"Rallies: {len(summary.get('rallies', []))}",
        f"Shot candidates: {len(shots)}",
        f"Pose coverage: {float(metrics.get('pose_coverage', 0)) * 100:.1f}%",
    ]
    issues = (summary.get("review") or {}).get("quality_issues") or []
    if issues:
        lines.extend(["", "Quality issues:"])
        for issue in issues:
            lines.append(
                f"{issue.get('code', 'UNKNOWN')}: "
                f"{issue.get('message', '')}"
            )
    return lines


def _ascii_pdf_text(value: Any) -> str:
    text = str(value).encode("ascii", errors="replace").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_basic_pdf(lines: list[str], output: Path) -> None:
    wrapped_lines: list[str] = []
    for line in lines:
        wrapped_lines.extend(textwrap.wrap(line, width=86) or [""])
    pages = [
        wrapped_lines[index : index + 50]
        for index in range(0, max(len(wrapped_lines), 1), 50)
    ]

    objects: dict[int, bytes] = {}
    page_ids = [4 + index * 2 for index in range(len(pages))]
    content_ids = [page_id + 1 for page_id in page_ids]
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"
    ).encode("ascii")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for page_id, content_id, page_lines in zip(page_ids, content_ids, pages):
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R "
            "/MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        commands = [
            "BT",
            "/F1 11 Tf",
            "50 790 Td",
            "14 TL",
        ]
        for line in page_lines:
            commands.append(f"({_ascii_pdf_text(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode("ascii"))
        document.extend(objects[object_id])
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    output.write_bytes(document)


def export_pdf_report(
    summary: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "analysis-report.pdf"
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        _write_basic_pdf(_report_lines(summary), output)
        return output

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "STSong-Light"
    story = [
        Paragraph("BadmintonAnalysis 羽毛球分析报告", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "本报告基于导入的外部分析结果。低置信结果为候选结论，需人工复核。",
            styles["BodyText"],
        ),
        Spacer(1, 14),
    ]
    metrics = summary.get("metrics") or {}
    players = metrics.get("players", {})
    shots = summary.get("shots")
    if shots is None:
        shots = summary.get("hits", [])
    rows = [["指标", "上半场", "下半场"]]
    for label, key in (
        ("跑动距离（米）", "distance_m"),
        ("平均速度（米/秒）", "average_speed_mps"),
        ("最高有效速度 P95（米/秒）", "max_effective_speed_mps"),
    ):
        rows.append(
            [
                label,
                players.get("top", {}).get(key, "—"),
                players.get("bottom", {}).get(key, "—"),
            ]
        )
    rows.extend(
        [
            ["有效回合", len(summary.get("rallies", [])), ""],
            ["击球候选", len(shots), ""],
            [
                "姿态覆盖率",
                f"{metrics.get('pose_coverage', 0) * 100:.1f}%",
                "",
            ],
        ]
    )
    table = Table(rows, colWidths=[210, 110, 110])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#174f3f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dfe4dc")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    issues = summary.get("review", {}).get("quality_issues", [])
    if issues:
        story.extend(
            [
                Spacer(1, 18),
                Paragraph("质量问题", styles["Heading2"]),
            ]
        )
        for issue in issues:
            story.append(
                Paragraph(
                    html.escape(
                        f"{issue.get('code', 'UNKNOWN')}："
                        f"{issue.get('message', '')}"
                    ),
                    styles["BodyText"],
                )
            )
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        title="BadmintonAnalysis Report",
    )
    document.build(story)
    return output


def _draw_skeleton(frame, keypoints, color) -> None:
    import cv2

    if keypoints is None:
        return
    for first, second in SKELETON_EDGES:
        start = tuple(round(value) for value in keypoints[first])
        end = tuple(round(value) for value in keypoints[second])
        cv2.line(frame, start, end, color, 2, cv2.LINE_AA)
    for point in keypoints:
        cv2.circle(
            frame,
            tuple(round(value) for value in point),
            3,
            color,
            -1,
            cv2.LINE_AA,
        )


def _draw_court_and_net(frame, calibration: dict[str, Any]) -> None:
    import cv2

    court = calibration.get("court_points") or []
    net = calibration.get("net_points") or []
    color = (71, 255, 201)
    for first, second in ((0, 1), (0, 4), (1, 5), (4, 5), (2, 3)):
        if len(court) > max(first, second):
            cv2.line(
                frame,
                tuple(round(value) for value in court[first]),
                tuple(round(value) for value in court[second]),
                color,
                2,
                cv2.LINE_AA,
            )
    if len(net) == 4:
        for first, second in ((0, 3), (1, 2), (0, 1), (3, 2)):
            cv2.line(
                frame,
                tuple(round(value) for value in net[first]),
                tuple(round(value) for value in net[second]),
                (72, 191, 255),
                2,
                cv2.LINE_AA,
            )


def _draw_side_panel(
    canvas,
    *,
    video_width: int,
    height: int,
    top_point: dict[str, Any] | None,
    bottom_point: dict[str, Any] | None,
    frame_number: int,
) -> None:
    import cv2

    panel_left = video_width
    canvas[:, panel_left:] = (24, 34, 30)
    cv2.putText(
        canvas,
        "COURT POSITION",
        (panel_left + 28, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (201, 255, 71),
        1,
        cv2.LINE_AA,
    )
    court_width = min(190, canvas.shape[1] - panel_left - 56)
    court_height = min(round(court_width * 13.4 / 6.1), height - 150)
    left = panel_left + (canvas.shape[1] - panel_left - court_width) // 2
    top = 78
    right = left + court_width
    bottom = top + court_height
    cv2.rectangle(canvas, (left, top), (right, bottom), (242, 245, 239), 2)
    cv2.line(
        canvas,
        (left, (top + bottom) // 2),
        (right, (top + bottom) // 2),
        (242, 245, 239),
        2,
    )
    cv2.line(
        canvas,
        ((left + right) // 2, top),
        ((left + right) // 2, bottom),
        (242, 245, 239),
        1,
    )
    for point, color in (
        (top_point, (255, 153, 82)),
        (bottom_point, (71, 255, 201)),
    ):
        if point is None:
            continue
        x = left + round(float(point["x_m"]) / 6.1 * court_width)
        y = top + round(float(point["y_m"]) / 13.4 * court_height)
        cv2.circle(canvas, (x, y), 8, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, (x, y), 12, color, 1, cv2.LINE_AA)
    cv2.putText(
        canvas,
        f"FRAME {frame_number}",
        (panel_left + 28, min(height - 30, bottom + 45)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (173, 185, 178),
        1,
        cv2.LINE_AA,
    )


def render_overlay_video(
    source_video: str | Path,
    summary: dict[str, Any],
    pose_payload: dict[str, Any],
    shuttle_payload: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    import cv2
    import numpy as np

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / "analysis-video.mp4"
    capture = cv2.VideoCapture(str(source_video), cv2.CAP_FFMPEG)
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {source_video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise ValueError(f"invalid video metadata: {source_video}")
    panel_width = 280
    poses = {item["frame"]: item for item in pose_payload.get("frames", [])}
    shuttle = {
        point["frame"]: point
        for rally in shuttle_payload.get("rallies", [])
        for point in rally.get("points", [])
    }
    players = (summary.get("metrics") or {}).get("players", {})
    movement = {
        side: {
            item["frame"]: item
            for item in players.get(side, {}).get("track", [])
        }
        for side in ("top", "bottom")
    }
    calibration = summary.get("calibration") or {}
    trail: deque[tuple[int, int]] = deque(maxlen=14)
    frame_number = 0
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{width + panel_width}x{height}",
        "-framerate",
        f"{fps:.12g}",
        "-i",
        "pipe:0",
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    error: BaseException | None = None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            _draw_court_and_net(frame, calibration)
            pose = poses.get(frame_number)
            if pose:
                _draw_skeleton(frame, pose.get("top_keypoints"), (255, 153, 82))
                _draw_skeleton(
                    frame,
                    pose.get("bottom_keypoints"),
                    (71, 255, 201),
                )
            ball = shuttle.get(frame_number)
            if ball and ball.get("visible"):
                trail.append((round(ball["x"]), round(ball["y"])))
            for index, point in enumerate(trail):
                radius = max(2, round(6 * (index + 1) / len(trail)))
                cv2.circle(frame, point, radius, (71, 255, 201), -1)
            canvas = np.zeros((height, width + panel_width, 3), dtype="uint8")
            canvas[:, :width] = frame
            _draw_side_panel(
                canvas,
                video_width=width,
                height=height,
                top_point=movement["top"].get(frame_number),
                bottom_point=movement["bottom"].get(frame_number),
                frame_number=frame_number,
            )
            if process.stdin is None:
                raise RuntimeError("ffmpeg input pipe is unavailable")
            process.stdin.write(canvas.tobytes())
            frame_number += 1
    except BaseException as caught:
        error = caught
    finally:
        capture.release()
        if process.stdin is not None:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
    stderr = process.stderr.read() if process.stderr is not None else b""
    if process.stderr is not None:
        process.stderr.close()
    return_code = process.wait()
    if error is not None:
        process.kill()
        raise error
    if frame_number == 0:
        raise ValueError(f"video contains no readable frames: {source_video}")
    if return_code != 0:
        message = stderr.decode(errors="replace")
        raise RuntimeError(message[-2000:])
    return output_path


def export_rally_clips(
    source_video: str | Path,
    rallies: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    fps: float,
) -> list[Path]:
    if fps <= 0:
        raise ValueError("fps must be positive")
    validated_rallies: list[tuple[int, int]] = []
    for rally in rallies:
        start_frame = rally.get("start_frame")
        end_frame = rally.get("end_frame")
        if not isinstance(start_frame, int) or start_frame < 0:
            raise ValueError("rally start_frame must be a non-negative integer")
        if not isinstance(end_frame, int) or end_frame < start_frame:
            raise ValueError("rally end_frame must be at least start_frame")
        validated_rallies.append((start_frame, end_frame))

    directory = Path(output_dir) / "rallies"
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index, (start_frame, end_frame) in enumerate(
        validated_rallies,
        start=1,
    ):
        output = directory / f"rally-{index:03d}.mp4"
        start = start_frame / fps
        duration = (end_frame - start_frame + 1) / fps
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-i",
            str(source_video),
            "-t",
            f"{duration:.6f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-2000:])
        outputs.append(output)
    return outputs
