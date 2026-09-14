from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .evaluation import evaluate_manifest
from .importing import ExternalAnalysisImport, import_external_results
from .repository import Repository
from .state_machine import AnalysisStage


class AthleteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    handedness: str | None = None


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    athlete_top_id: str | None = None
    athlete_bottom_id: str | None = None


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    source_path: str


class DemoBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    entity_type: str
    entity_id: str
    field_name: str
    old_value: Any
    new_value: Any
    reason: str | None = None


def create_app(
    *,
    repository: Repository | None = None,
    repo_root: Path | None = None,
) -> FastAPI:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    owned_repository = repository is None
    repo = repository or Repository(root / "data" / "courtvision.sqlite3")
    repo.initialize()

    app = FastAPI(
        title="BadmintonAnalysis API",
        version="0.1.0",
        description="Provider-neutral badminton analysis, review and export service",
    )
    app.state.repository = repo
    app.state.repo_root = root
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:56177",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if owned_repository:
        @app.on_event("shutdown")
        def close_repository() -> None:
            repo.close()

    def get_job_or_404(job_id: str) -> dict[str, Any]:
        try:
            return repo.get_job(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job not found") from error

    def get_result_or_none(job_id: str, kind: str) -> Any:
        try:
            return repo.get_result(job_id, kind)
        except KeyError:
            return None

    def build_summary(job_id: str) -> dict[str, Any]:
        job = get_job_or_404(job_id)
        segmentation = get_result_or_none(job_id, "segmenting") or {}
        events = get_result_or_none(job_id, "event_detection") or {}
        pose = get_result_or_none(job_id, "pose_tracking") or {}
        metrics = get_result_or_none(job_id, "metrics")
        review = get_result_or_none(job_id, "review_required") or {}
        rallies = [
            {**item, "id": item.get("id", f"rally-{index}")}
            for index, item in enumerate(
                events.get("rallies", segmentation.get("rallies", [])),
                start=1,
            )
        ]
        shots = [
            {
                **item,
                "id": item.get(
                    "id",
                    f"shot-{item.get('hit_frame', index)}",
                ),
            }
            for index, item in enumerate(events.get("shots", []), start=1)
        ]
        revisions = repo.list_revisions(job_id)
        entities = {
            ("shot", item.get("id")): item
            for item in shots
            if item.get("id")
        }
        entities.update(
            {
                ("rally", item.get("id")): item
                for item in rallies
                if item.get("id")
            }
        )
        for revision in revisions:
            entity = entities.get(
                (revision["entity_type"], revision["entity_id"])
            )
            if entity is None:
                continue
            entity[revision["field_name"]] = revision["new_value"]
            entity["origin"] = "human"
            entity["revised"] = True
        video = get_result_or_none(job_id, "validating")
        calibration = get_result_or_none(job_id, "calibrating")
        return {
            "job": job,
            "video": video,
            "calibration": calibration,
            "rallies": rallies,
            "hits": events.get("hits", []),
            "shots": shots,
            "identities": pose.get("identities", []),
            "metrics": metrics,
            "review": review,
            "revisions": revisions,
        }

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "BadmintonAnalysis",
            "analysis_mode": "external_results",
        }

    @app.get("/api/evaluation/acceptance")
    def acceptance_evaluation() -> dict[str, Any]:
        report_path = (
            root / "docs" / "acceptance" / "acceptance-evaluation.json"
        )
        if report_path.is_file():
            try:
                return json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"acceptance report is unreadable: {error}",
                ) from error
        return evaluate_manifest({"schema_version": 1, "metrics": {}})

    @app.post("/api/athletes", status_code=201)
    def create_athlete(payload: AthleteCreate) -> dict[str, Any]:
        return repo.create_athlete(
            payload.name,
            handedness=payload.handedness,
        )

    @app.get("/api/athletes")
    def list_athletes() -> list[dict[str, Any]]:
        return repo.list_athletes()

    @app.get("/api/athletes/{athlete_id}")
    def get_athlete(athlete_id: str) -> dict[str, Any]:
        try:
            return repo.get_athlete(athlete_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail="athlete not found",
            ) from error

    @app.post("/api/sessions", status_code=201)
    def create_session(payload: SessionCreate) -> dict[str, Any]:
        return repo.create_session(
            title=payload.title,
            athlete_top_id=payload.athlete_top_id,
            athlete_bottom_id=payload.athlete_bottom_id,
        )

    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        return repo.list_sessions()

    @app.post("/api/jobs", status_code=201)
    def create_job(payload: JobCreate) -> dict[str, Any]:
        try:
            job = repo.create_job(
                session_id=payload.session_id,
                source_path=payload.source_path,
            )
            return repo.update_job_stage(
                job["id"],
                AnalysisStage.AWAITING_RESULTS,
                progress=0.1,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/uploads", status_code=201)
    def upload_video(
        title: str,
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        extension = Path(file.filename or "").suffix.lower()
        if extension not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise HTTPException(status_code=415, detail="unsupported video format")
        upload_dir = root / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / f"{uuid.uuid4().hex}{extension}"
        with destination.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        session = repo.create_session(title=title)
        job = repo.create_job(
            session_id=session["id"],
            source_path=str(destination),
        )
        job = repo.update_job_stage(
            job["id"],
            AnalysisStage.AWAITING_RESULTS,
            progress=0.1,
        )
        return {"session": session, "job": job}

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return repo.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return get_job_or_404(job_id)

    @app.get("/api/jobs/{job_id}/results/{kind}")
    def get_result(job_id: str, kind: str) -> Any:
        get_job_or_404(job_id)
        result = get_result_or_none(job_id, kind)
        if result is None:
            raise HTTPException(status_code=404, detail="result not found")
        return result

    @app.get("/api/jobs/{job_id}/summary")
    def get_summary(job_id: str) -> dict[str, Any]:
        return build_summary(job_id)

    @app.post("/api/jobs/{job_id}/results/import")
    def import_results(
        job_id: str,
        payload: ExternalAnalysisImport,
    ) -> dict[str, Any]:
        get_job_or_404(job_id)
        try:
            import_external_results(repo, job_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return build_summary(job_id)

    @app.get("/api/jobs/{job_id}/video")
    def get_video(job_id: str) -> FileResponse:
        job = get_job_or_404(job_id)
        path = Path(job["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="video not found")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/jobs/{job_id}/run")
    def run_job(job_id: str) -> None:
        get_job_or_404(job_id)
        raise HTTPException(status_code=409, detail="external_results_required")

    @app.post("/api/jobs/{job_id}/exports")
    def create_exports(job_id: str) -> dict[str, Any]:
        from .exporting import (
            export_csv_bundle,
            export_json_summary,
            export_pdf_report,
            export_rally_clips,
            render_overlay_video,
        )

        job = get_job_or_404(job_id)
        if job["stage"] == AnalysisStage.COMPLETED.value:
            existing = get_result_or_none(job_id, "rendering")
            if existing is not None:
                return existing
        retry_render = (
            (
                job["stage"] == AnalysisStage.FAILED.value
                and job["checkpoint"].get("resume_stage") == "rendering"
            )
            or (
                job["stage"] == AnalysisStage.RENDERING.value
                and job["checkpoint"].get("active_stage") == "rendering"
            )
        )
        if job["stage"] != AnalysisStage.REVIEW_REQUIRED.value and not retry_render:
            raise HTTPException(
                status_code=409,
                detail="job must be reviewable or retrying rendering",
            )
        summary = build_summary(job_id)
        source = Path(job["source_path"])
        transcoding = get_result_or_none(job_id, "transcoding") or {}
        proxy_path = Path(transcoding.get("proxy_path", source))
        if proxy_path.is_file():
            source = proxy_path
        output_dir = root / "exports" / job_id
        if retry_render:
            repo.update_job_stage(
                job_id,
                AnalysisStage.RETRYING,
                progress=job["progress"],
                checkpoint=job["checkpoint"],
            )
        repo.update_job_stage(
            job_id,
            AnalysisStage.RENDERING,
            progress=0.95,
            checkpoint={"active_stage": "rendering"},
        )
        try:
            json_path = export_json_summary(summary, output_dir)
            csv_paths = export_csv_bundle(summary, output_dir)
            pdf_path = export_pdf_report(summary, output_dir)
            pose = repo.get_result(job_id, "pose_tracking")
            shuttle = repo.get_result(job_id, "shuttle_tracking")
            video_path = render_overlay_video(
                source,
                summary,
                pose,
                shuttle,
                output_dir,
            )
            metadata = summary.get("video") or {}
            clip_paths = export_rally_clips(
                source,
                summary["rallies"],
                output_dir,
                fps=float(metadata["fps"]),
            )
            payload = {
                "json": str(json_path),
                "shots_csv": str(csv_paths["shots"]),
                "movement_csv": str(csv_paths["movement"]),
                "pdf": str(pdf_path),
                "video": str(video_path),
                "rally_clips": [str(path) for path in clip_paths],
            }
            repo.save_result(job_id=job_id, kind="rendering", payload=payload)
            repo.update_job_stage(
                job_id,
                AnalysisStage.COMPLETED,
                progress=1.0,
                checkpoint={"completed_stage": "rendering"},
            )
            return payload
        except Exception as error:
            repo.update_job_stage(
                job_id,
                AnalysisStage.FAILED,
                progress=0.95,
                checkpoint={"resume_stage": "rendering"},
                error_message=str(error),
            )
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.get("/api/jobs/{job_id}/exports/{artifact}")
    def download_export(job_id: str, artifact: str) -> FileResponse:
        get_job_or_404(job_id)
        rendering = get_result_or_none(job_id, "rendering")
        if rendering is None:
            raise HTTPException(status_code=404, detail="exports not found")
        allowed = {
            "json": rendering.get("json"),
            "shots.csv": rendering.get("shots_csv"),
            "movement.csv": rendering.get("movement_csv"),
            "report.pdf": rendering.get("pdf"),
            "video.mp4": rendering.get("video"),
        }
        path_value = allowed.get(artifact)
        if path_value is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        path = Path(path_value)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="artifact file missing")
        return FileResponse(path, filename=path.name)

    @app.get("/api/jobs/{job_id}/exports/rallies/{clip_name}")
    def download_rally_clip(job_id: str, clip_name: str) -> FileResponse:
        get_job_or_404(job_id)
        rendering = get_result_or_none(job_id, "rendering")
        if rendering is None:
            raise HTTPException(status_code=404, detail="exports not found")
        clip = next(
            (
                Path(path_value)
                for path_value in rendering.get("rally_clips", [])
                if Path(path_value).name == clip_name
            ),
            None,
        )
        if clip is None:
            raise HTTPException(status_code=404, detail="rally clip not found")
        if not clip.is_file():
            raise HTTPException(
                status_code=404,
                detail="rally clip file missing",
            )
        return FileResponse(clip, filename=clip.name)

    @app.post("/api/demo/bootstrap", status_code=201)
    def bootstrap_demo(payload: DemoBootstrap) -> dict[str, Any]:
        fixture_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "synthetic-demo.json"
        )
        fixture = ExternalAnalysisImport.model_validate_json(
            fixture_path.read_text(encoding="utf-8")
        )
        session = repo.create_session(title="合成羽毛球分析示例")
        job = repo.create_job(
            session_id=session["id"],
            source_path=str(root / "data" / "synthetic-demo.mp4"),
        )
        repo.update_job_stage(
            job["id"],
            AnalysisStage.AWAITING_RESULTS,
            progress=0.1,
        )
        import_external_results(repo, job["id"], fixture)
        return {
            "session": session,
            **build_summary(job["id"]),
        }

    @app.post("/api/revisions", status_code=201)
    def create_revision(payload: RevisionCreate) -> dict[str, Any]:
        get_job_or_404(payload.job_id)
        return repo.create_revision(
            job_id=payload.job_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            field_name=payload.field_name,
            old_value=payload.old_value,
            new_value=payload.new_value,
            reason=payload.reason,
        )

    @app.get("/api/jobs/{job_id}/revisions")
    def list_revisions(job_id: str) -> list[dict[str, Any]]:
        get_job_or_404(job_id)
        return repo.list_revisions(job_id)

    return app
