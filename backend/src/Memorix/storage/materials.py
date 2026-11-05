"""Persistência e revisão humana local de materiais no banco do acervo."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .material_validation import references_current, validate_draft


_STATUSES = ("requires_review", "approved", "rejected")


class MaterialStore:
    """Uma conexão própria; o banco deve ter sido inicializado pelo Corpus.

    A revisão registra uma decisão humana, não uma avaliação semântica automática.
    Use como context manager para fechar a conexão.
    """

    def __init__(self, database: str | Path):
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS materials (
                    material_id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('requires_review', 'approved', 'rejected')),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_at TEXT
                )
                """
            )
        except Exception:
            self._connection.close()
            raise

    def __enter__(self) -> "MaterialStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _find(self, material_id: str) -> sqlite3.Row:
        if not isinstance(material_id, str) or not material_id.strip():
            raise ValueError("Identificador de material inválido.")
        row = self._connection.execute(
            "SELECT * FROM materials WHERE material_id = ?", (material_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Material não encontrado.")
        return row

    @staticmethod
    def _check_version(row: sqlite3.Row, expected_version: int) -> None:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("A versão esperada deve ser um inteiro positivo.")
        if row["version"] != expected_version:
            raise ValueError("A versão do material mudou; consulte-o novamente.")

    @staticmethod
    def _body(draft: dict) -> str:
        return json.dumps(
            {key: value for key, value in draft.items() if key != "status"},
            ensure_ascii=False,
        )

    @staticmethod
    def _draft(row: sqlite3.Row) -> dict:
        return {**json.loads(row["body"]), "status": "requires_review"}

    def _record(self, row: sqlite3.Row, *, include_items: bool = True) -> dict:
        draft = self._draft(row)
        current = references_current(draft, self._connection)
        if not include_items:
            del draft["items"]
        return {
            **draft,
            "material_id": row["material_id"],
            "version": row["version"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "reviewed_at": row["reviewed_at"],
            "sources_current": current,
        }

    def create(self, payload: object) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            draft = validate_draft(payload, self._connection)
            material_id = str(uuid4())
            now = datetime.now(timezone.utc).isoformat()
            self._connection.execute(
                "INSERT INTO materials "
                "(material_id, body, status, version, created_at, updated_at, reviewed_at) "
                "VALUES (?, ?, 'requires_review', 1, ?, ?, NULL)",
                (material_id, self._body(draft), now, now),
            )
            return self._record(self._find(material_id))

    def get(self, material_id: str) -> dict:
        with self._connection:
            self._connection.execute("BEGIN")
            return self._record(self._find(material_id))

    def list_materials(self, *, status: str | None = None, limit: int = 20) -> list[dict]:
        if status is not None and status not in _STATUSES:
            raise ValueError("Estado de material inválido.")
        if type(limit) is not int or limit < 1:
            raise ValueError("O limite deve ser um inteiro positivo.")
        query = "SELECT * FROM materials"
        parameters: list = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC, material_id ASC LIMIT ?"
        parameters.append(limit)
        with self._connection:
            self._connection.execute("BEGIN")
            rows = self._connection.execute(query, parameters).fetchall()
            return [self._record(row, include_items=False) for row in rows]

    def update(self, material_id: str, payload: object, *, expected_version: int) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._find(material_id)
            self._check_version(row, expected_version)
            draft = validate_draft(payload, self._connection)
            now = datetime.now(timezone.utc).isoformat()
            self._connection.execute(
                "UPDATE materials SET body = ?, status = 'requires_review', "
                "version = version + 1, updated_at = ?, reviewed_at = NULL "
                "WHERE material_id = ?",
                (self._body(draft), now, material_id),
            )
            return self._record(self._find(material_id))

    def review(self, material_id: str, decision: str, *, expected_version: int) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if decision not in ("approve", "reject"):
                raise ValueError("Decisão de revisão inválida.")
            row = self._find(material_id)
            self._check_version(row, expected_version)
            if row["status"] != "requires_review":
                raise ValueError("O material não está aguardando revisão.")
            if decision == "approve":
                validate_draft(self._draft(row), self._connection)
            now = datetime.now(timezone.utc).isoformat()
            status = "approved" if decision == "approve" else "rejected"
            self._connection.execute(
                "UPDATE materials SET status = ?, version = version + 1, "
                "updated_at = ?, reviewed_at = ? WHERE material_id = ?",
                (status, now, now, material_id),
            )
            return self._record(self._find(material_id))
