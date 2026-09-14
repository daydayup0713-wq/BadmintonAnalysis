from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from .state_machine import AnalysisStage, validate_transition


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Repository:
    def __init__(
        self,
        db_path: str | Path,
        *,
        journal_mode: str = "WAL",
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        normalized_journal_mode = journal_mode.upper()
        if normalized_journal_mode not in {"DELETE", "WAL"}:
            raise ValueError("journal_mode must be DELETE or WAL")
        self.connection.execute(f"PRAGMA journal_mode = {normalized_journal_mode}")

    @_synchronized
    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS athletes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                handedness TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                athlete_top_id TEXT REFERENCES athletes(id),
                athlete_bottom_id TEXT REFERENCES athletes(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                source_path TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                checkpoint_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS annotation_revisions (
                id TEXT PRIMARY KEY,
                job_id TEXT REFERENCES analysis_jobs(id),
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value_json TEXT NOT NULL,
                new_value_json TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_results (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES analysis_jobs(id),
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(job_id, kind, version)
            );
            """
        )
        revision_columns = {
            row["name"]
            for row in self.connection.execute(
                "PRAGMA table_info(annotation_revisions)"
            ).fetchall()
        }
        if "job_id" not in revision_columns:
            self.connection.execute(
                "ALTER TABLE annotation_revisions ADD COLUMN job_id TEXT"
            )
        self.connection.commit()

    @_synchronized
    def close(self) -> None:
        self.connection.close()

    @_synchronized
    def create_athlete(
        self,
        name: str,
        *,
        handedness: str | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("athlete name is required")
        row = {
            "id": _id("athlete"),
            "name": name.strip(),
            "handedness": handedness,
            "created_at": _now(),
        }
        self.connection.execute(
            """
            INSERT INTO athletes(id, name, handedness, created_at)
            VALUES(:id, :name, :handedness, :created_at)
            """,
            row,
        )
        self.connection.commit()
        return row

    @_synchronized
    def list_athletes(self) -> list[dict[str, Any]]:
        records = self.connection.execute(
            "SELECT * FROM athletes ORDER BY created_at DESC"
        ).fetchall()
        return [dict(record) for record in records]

    @_synchronized
    def get_athlete(self, athlete_id: str) -> dict[str, Any]:
        record = self.connection.execute(
            "SELECT * FROM athletes WHERE id = ?",
            (athlete_id,),
        ).fetchone()
        if record is None:
            raise KeyError(athlete_id)
        sessions = self.connection.execute(
            """
            SELECT *,
                CASE
                    WHEN athlete_top_id = ? THEN 'top'
                    ELSE 'bottom'
                END AS slot
            FROM sessions
            WHERE athlete_top_id = ? OR athlete_bottom_id = ?
            ORDER BY created_at DESC
            """,
            (athlete_id, athlete_id, athlete_id),
        ).fetchall()
        session_rows = [dict(session) for session in sessions]
        session_ids = [session["id"] for session in session_rows]
        jobs: list[dict[str, Any]] = []
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            job_records = self.connection.execute(
                f"""
                SELECT id FROM analysis_jobs
                WHERE session_id IN ({placeholders})
                ORDER BY created_at DESC
                """,
                session_ids,
            ).fetchall()
            jobs = [self.get_job(job["id"]) for job in job_records]
        return {
            **dict(record),
            "sessions": session_rows,
            "jobs": jobs,
        }

    @_synchronized
    def create_session(
        self,
        *,
        title: str,
        athlete_top_id: str | None = None,
        athlete_bottom_id: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": _id("session"),
            "title": title.strip(),
            "athlete_top_id": athlete_top_id,
            "athlete_bottom_id": athlete_bottom_id,
            "created_at": _now(),
        }
        self.connection.execute(
            """
            INSERT INTO sessions(
                id, title, athlete_top_id, athlete_bottom_id, created_at
            ) VALUES(
                :id, :title, :athlete_top_id, :athlete_bottom_id, :created_at
            )
            """,
            row,
        )
        self.connection.commit()
        return row

    @_synchronized
    def list_sessions(self) -> list[dict[str, Any]]:
        records = self.connection.execute(
            """
            SELECT
                sessions.*,
                top.name AS athlete_top_name,
                bottom.name AS athlete_bottom_name
            FROM sessions
            LEFT JOIN athletes AS top ON top.id = sessions.athlete_top_id
            LEFT JOIN athletes AS bottom ON bottom.id = sessions.athlete_bottom_id
            ORDER BY sessions.created_at DESC
            """
        ).fetchall()
        return [dict(record) for record in records]

    @_synchronized
    def create_job(self, *, session_id: str, source_path: str) -> dict[str, Any]:
        timestamp = _now()
        row = {
            "id": _id("job"),
            "session_id": session_id,
            "source_path": source_path,
            "stage": AnalysisStage.UPLOADED.value,
            "progress": 0.0,
            "checkpoint_json": "{}",
            "error_message": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.connection.execute(
            """
            INSERT INTO analysis_jobs(
                id, session_id, source_path, stage, progress,
                checkpoint_json, error_message, created_at, updated_at
            ) VALUES(
                :id, :session_id, :source_path, :stage, :progress,
                :checkpoint_json, :error_message, :created_at, :updated_at
            )
            """,
            row,
        )
        self.connection.commit()
        return self.get_job(row["id"])

    @_synchronized
    def get_job(self, job_id: str) -> dict[str, Any]:
        record = self.connection.execute(
            "SELECT * FROM analysis_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if record is None:
            raise KeyError(job_id)
        result = dict(record)
        result["checkpoint"] = json.loads(result.pop("checkpoint_json"))
        return result

    @_synchronized
    def list_jobs(self) -> list[dict[str, Any]]:
        records = self.connection.execute(
            "SELECT id FROM analysis_jobs ORDER BY created_at DESC"
        ).fetchall()
        return [self.get_job(record["id"]) for record in records]

    @_synchronized
    def update_job_stage(
        self,
        job_id: str,
        stage: AnalysisStage,
        *,
        progress: float,
        checkpoint: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if not 0 <= progress <= 1:
            raise ValueError("progress must be between 0 and 1")
        current = self.get_job(job_id)
        validate_transition(AnalysisStage(current["stage"]), stage)
        self.connection.execute(
            """
            UPDATE analysis_jobs
            SET stage = ?, progress = ?, checkpoint_json = ?,
                error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                stage.value,
                progress,
                json.dumps(checkpoint or {}, ensure_ascii=False),
                error_message,
                _now(),
                job_id,
            ),
        )
        self.connection.commit()
        return self.get_job(job_id)

    @_synchronized
    def update_job_progress(
        self,
        job_id: str,
        *,
        progress: float,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not 0 <= progress <= 1:
            raise ValueError("progress must be between 0 and 1")
        self.get_job(job_id)
        self.connection.execute(
            """
            UPDATE analysis_jobs
            SET progress = ?, checkpoint_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                progress,
                json.dumps(checkpoint or {}, ensure_ascii=False),
                _now(),
                job_id,
            ),
        )
        self.connection.commit()
        return self.get_job(job_id)

    @_synchronized
    def create_revision(
        self,
        *,
        job_id: str,
        entity_type: str,
        entity_id: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        reason: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": _id("revision"),
            "job_id": job_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_name": field_name,
            "old_value_json": json.dumps(old_value, ensure_ascii=False),
            "new_value_json": json.dumps(new_value, ensure_ascii=False),
            "reason": reason,
            "created_at": _now(),
        }
        self.connection.execute(
            """
            INSERT INTO annotation_revisions(
                id, job_id, entity_type, entity_id, field_name,
                old_value_json, new_value_json, reason, created_at
            ) VALUES(
                :id, :job_id, :entity_type, :entity_id, :field_name,
                :old_value_json, :new_value_json, :reason, :created_at
            )
            """,
            row,
        )
        self.connection.commit()
        return {
            key: value
            for key, value in row.items()
            if key not in {"old_value_json", "new_value_json"}
        } | {
            "old_value": old_value,
            "new_value": new_value,
        }

    @_synchronized
    def list_revisions(self, job_id: str) -> list[dict[str, Any]]:
        records = self.connection.execute(
            """
            SELECT * FROM annotation_revisions
            WHERE job_id = ?
            ORDER BY created_at ASC
            """,
            (job_id,),
        ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(record).items()
                    if key not in {"old_value_json", "new_value_json"}
                },
                "old_value": json.loads(record["old_value_json"]),
                "new_value": json.loads(record["new_value_json"]),
            }
            for record in records
        ]

    @_synchronized
    def save_result(
        self,
        *,
        job_id: str,
        kind: str,
        payload: Any,
        version: int = 1,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO analysis_results(
                id, job_id, kind, payload_json, version, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                _id("result"),
                job_id,
                kind,
                json.dumps(payload, ensure_ascii=False),
                version,
                _now(),
            ),
        )
        self.connection.commit()

    @_synchronized
    def get_result(
        self,
        job_id: str,
        kind: str,
        *,
        version: int = 1,
    ) -> Any:
        record = self.connection.execute(
            """
            SELECT payload_json FROM analysis_results
            WHERE job_id = ? AND kind = ? AND version = ?
            """,
            (job_id, kind, version),
        ).fetchone()
        if record is None:
            raise KeyError((job_id, kind, version))
        return json.loads(record["payload_json"])
