"""Sessões locais de questionários aprovados, sem gabarito antes do envio."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from ..study.grading import grade_answers, present_questions
from .material_validation import references_current, validate_draft


_STATUSES = ("in_progress", "completed")


class StudyStore:
    """Uma conexão própria ao acervo já inicializado por Corpus e MaterialStore."""

    def __init__(self, database: str | Path):
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS study_sessions (
                    session_id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL REFERENCES materials(material_id),
                    material_version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed')),
                    answers_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
        except Exception:
            self._connection.close()
            raise

    def __enter__(self) -> "StudyStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _find(self, session_id: str) -> sqlite3.Row:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Identificador de sessão inválido.")
        row = self._connection.execute(
            "SELECT * FROM study_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Sessão não encontrada.")
        return row

    def _material(self, material_id: str) -> sqlite3.Row:
        if not isinstance(material_id, str) or not material_id.strip():
            raise ValueError("Identificador de material inválido.")
        row = self._connection.execute(
            "SELECT * FROM materials WHERE material_id = ?", (material_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Material não encontrado.")
        return row

    def _summary(self, row: sqlite3.Row, snapshot: dict) -> dict:
        material = self._connection.execute(
            "SELECT status, version FROM materials WHERE material_id = ?",
            (row["material_id"],),
        ).fetchone()
        return {
            "session_id": row["session_id"],
            "material_id": row["material_id"],
            "material_version": row["material_version"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "kind": snapshot["kind"],
            "topic": snapshot["topic"],
            "title": snapshot["title"],
            "difficulty": snapshot["difficulty"],
            "material_current": (
                material is not None
                and material["status"] == "approved"
                and material["version"] == row["material_version"]
            ),
            "sources_current": references_current(snapshot, self._connection),
        }

    @staticmethod
    def _require_current(record: dict) -> None:
        if not record["material_current"] or not record["sources_current"]:
            raise ValueError("O material ou suas fontes mudaram; inicie uma nova sessão após revisão.")

    def _record(self, row: sqlite3.Row, *, include_details: bool = True) -> dict:
        snapshot = json.loads(row["snapshot_json"])
        record = self._summary(row, snapshot)
        if include_details:
            if row["status"] == "in_progress":
                self._require_current(record)
                record["questions"] = present_questions(snapshot)
            else:
                record["result"] = grade_answers(snapshot, json.loads(row["answers_json"]))
        return record

    def start(self, material_id: str, *, expected_version: int) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if type(expected_version) is not int or expected_version < 1:
                raise ValueError("A versão esperada deve ser um inteiro positivo.")
            material = self._material(material_id)
            if material["version"] != expected_version:
                raise ValueError("A versão do material mudou; consulte-o novamente.")
            if material["status"] != "approved":
                raise ValueError("Somente materiais aprovados podem iniciar uma sessão.")
            snapshot = validate_draft(
                {**json.loads(material["body"]), "status": "requires_review"},
                self._connection,
            )
            questions = present_questions(snapshot)
            session_id = str(uuid4())
            now = datetime.now(timezone.utc).isoformat()
            self._connection.execute(
                "INSERT INTO study_sessions "
                "(session_id, material_id, material_version, snapshot_json, status, "
                "answers_json, created_at, completed_at) "
                "VALUES (?, ?, ?, ?, 'in_progress', NULL, ?, NULL)",
                (session_id, material_id, expected_version,
                 json.dumps(snapshot, ensure_ascii=False), now),
            )
            record = self._summary(self._find(session_id), snapshot)
            self._require_current(record)
            return {**record, "questions": questions}

    def get(self, session_id: str) -> dict:
        with self._connection:
            self._connection.execute("BEGIN")
            return self._record(self._find(session_id))

    def submit(self, session_id: str, answers: object) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._find(session_id)
            if row["status"] != "in_progress":
                raise ValueError("Esta sessão já foi concluída; não é possível reenviar respostas.")
            snapshot = json.loads(row["snapshot_json"])
            record = self._summary(row, snapshot)
            self._require_current(record)
            result = grade_answers(snapshot, answers)
            now = datetime.now(timezone.utc).isoformat()
            self._connection.execute(
                "UPDATE study_sessions SET answers_json = ?, status = 'completed', "
                "completed_at = ? WHERE session_id = ?",
                (json.dumps(answers, ensure_ascii=False), now, session_id),
            )
            return {**record, "status": "completed", "completed_at": now, "result": result}

    def list_sessions(self, *, status: str | None = None, limit: int = 20) -> list[dict]:
        if status is not None and status not in _STATUSES:
            raise ValueError("Estado de sessão inválido.")
        if type(limit) is not int or limit < 1:
            raise ValueError("O limite deve ser um inteiro positivo.")
        query = "SELECT * FROM study_sessions"
        parameters: list = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC, session_id ASC LIMIT ?"
        parameters.append(limit)
        with self._connection:
            self._connection.execute("BEGIN")
            rows = self._connection.execute(query, parameters).fetchall()
            return [self._record(row, include_details=False) for row in rows]
