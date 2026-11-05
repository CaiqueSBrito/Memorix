"""Prática local de flashcards com revelação explícita e histórico imutável."""

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from ..study.flashcard_queue import cards_from_connection
from ..study.flashcard_schedule import RATINGS, schedule_review, utc_instant
from .material_validation import references_current, validate_draft


_STATUSES = ("in_progress", "completed")


class FlashcardStore:
    """Uma conexão própria ao acervo inicializado por Corpus e MaterialStore."""

    def __init__(self, database: str | Path):
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS flashcard_states (
                    material_id TEXT NOT NULL REFERENCES materials(material_id),
                    material_version INTEGER NOT NULL CHECK(material_version > 0),
                    item_index INTEGER NOT NULL CHECK(item_index >= 0),
                    box INTEGER NOT NULL CHECK(box BETWEEN 0 AND 6),
                    state_version INTEGER NOT NULL CHECK(state_version >= 1),
                    due_at TEXT NOT NULL,
                    last_reviewed_at TEXT NOT NULL,
                    PRIMARY KEY(material_id, material_version, item_index)
                );
                CREATE TABLE IF NOT EXISTS flashcard_sessions (
                    session_id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL REFERENCES materials(material_id),
                    material_version INTEGER NOT NULL CHECK(material_version > 0),
                    snapshot_json TEXT NOT NULL,
                    selection_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed')),
                    position INTEGER NOT NULL CHECK(position >= 0),
                    revealed INTEGER NOT NULL CHECK(revealed IN (0, 1)),
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS flashcard_reviews (
                    session_id TEXT NOT NULL REFERENCES flashcard_sessions(session_id),
                    item_index INTEGER NOT NULL CHECK(item_index >= 0),
                    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                    rating TEXT NOT NULL CHECK(rating IN ('again', 'hard', 'good', 'easy')),
                    box INTEGER NOT NULL CHECK(box BETWEEN 0 AND 6),
                    due_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, item_index),
                    UNIQUE(session_id, ordinal)
                );
                """
            )
        except Exception:
            self._connection.close()
            raise

    def __enter__(self) -> "FlashcardStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _find(self, session_id: str) -> sqlite3.Row:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Identificador de sessão inválido.")
        row = self._connection.execute(
            "SELECT * FROM flashcard_sessions WHERE session_id = ?", (session_id,)
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

    def _state(self, row: sqlite3.Row, item_index: int) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM flashcard_states "
            "WHERE material_id = ? AND material_version = ? AND item_index = ?",
            (row["material_id"], row["material_version"], item_index),
        ).fetchone()

    def _summary(self, row: sqlite3.Row, snapshot: dict, selection: list) -> dict:
        material = self._connection.execute(
            "SELECT status, version FROM materials WHERE material_id = ?",
            (row["material_id"],),
        ).fetchone()
        card_current = None
        if row["status"] == "in_progress":
            selected = selection[row["position"]]
            state = self._state(row, selected["item_index"])
            card_current = (0 if state is None else state["state_version"]) == selected["state_version"]
        return {
            "session_id": row["session_id"],
            "material_id": row["material_id"],
            "material_version": row["material_version"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "title": snapshot["title"],
            "topic": snapshot["topic"],
            "difficulty": snapshot["difficulty"],
            "total_cards": len(selection),
            "completed_cards": row["position"],
            "material_current": (
                material is not None
                and material["status"] == "approved"
                and material["version"] == row["material_version"]
            ),
            "sources_current": references_current(snapshot, self._connection),
            "card_current": card_current,
        }

    @staticmethod
    def _require_current(record: dict, *, allow_stale_card: bool = False) -> None:
        if not record["material_current"] or not record["sources_current"]:
            raise ValueError("O material ou suas fontes mudaram; inicie uma nova sessão após revisão.")
        if not allow_stale_card and not record["card_current"]:
            raise ValueError("Este cartão já foi revisado em outra sessão.")

    def _record(self, row: sqlite3.Row, *, allow_stale_card: bool = False) -> dict:
        snapshot = json.loads(row["snapshot_json"])
        selection = json.loads(row["selection_json"])
        record = self._summary(row, snapshot, selection)
        record["card"] = None
        if row["status"] == "in_progress":
            self._require_current(record, allow_stale_card=allow_stale_card)
            if record["card_current"]:
                item_index = selection[row["position"]]["item_index"]
                item = snapshot["items"][item_index]
                card = {
                    "item_index": item_index,
                    "front": item["front"],
                    "revealed": bool(row["revealed"]),
                }
                if row["revealed"]:
                    card.update(back=item["back"], citations=item["citations"])
                record["card"] = card
        record["reviews"] = [
            dict(review) for review in self._connection.execute(
                "SELECT item_index, rating, box, due_at, reviewed_at "
                "FROM flashcard_reviews WHERE session_id = ? ORDER BY ordinal",
                (row["session_id"],),
            )
        ]
        return record

    def _active(self, row: sqlite3.Row, expected_item: int) -> tuple[dict, sqlite3.Row | None]:
        if type(expected_item) is not int or expected_item < 0:
            raise ValueError("O cartão esperado deve ser um inteiro não negativo.")
        if row["status"] != "in_progress":
            raise ValueError("Esta sessão já foi concluída.")
        selection = json.loads(row["selection_json"])
        selected = selection[row["position"]]
        if expected_item != selected["item_index"]:
            raise ValueError("O cartão atual mudou; consulte a sessão novamente.")
        snapshot = json.loads(row["snapshot_json"])
        self._require_current(self._summary(row, snapshot, selection))
        return selected, self._state(row, expected_item)

    def start(
        self, material_id: str, *, expected_version: int, limit: int = 20,
        now: datetime | None = None,
    ) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if type(expected_version) is not int or expected_version < 1:
                raise ValueError("A versão esperada deve ser um inteiro positivo.")
            if type(limit) is not int or limit < 1:
                raise ValueError("O limite deve ser um inteiro positivo.")
            instant = utc_instant(now)
            material = self._material(material_id)
            if material["version"] != expected_version:
                raise ValueError("A versão do material mudou; consulte-o novamente.")
            if material["status"] != "approved":
                raise ValueError("Somente materiais aprovados podem iniciar uma sessão.")
            snapshot = validate_draft(
                {**json.loads(material["body"]), "status": "requires_review"},
                self._connection,
            )
            if snapshot["kind"] != "flashcards":
                raise ValueError("Esta prática exige um material de flashcards.")
            cards = cards_from_connection(
                self._connection, material_id=material_id, limit=limit, now=instant,
            )["cards"]
            if not cards:
                raise ValueError("Não há cartões novos ou vencidos neste material.")
            selection = [
                {"item_index": card["item_index"], "state_version": card["state_version"]}
                for card in cards
            ]
            session_id = str(uuid4())
            self._connection.execute(
                "INSERT INTO flashcard_sessions "
                "(session_id, material_id, material_version, snapshot_json, selection_json, "
                "status, position, revealed, created_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, 'in_progress', 0, 0, ?, NULL)",
                (session_id, material_id, expected_version,
                 json.dumps(snapshot, ensure_ascii=False), json.dumps(selection), instant.isoformat()),
            )
            return self._record(self._find(session_id))

    def get(self, session_id: str) -> dict:
        with self._connection:
            self._connection.execute("BEGIN")
            return self._record(self._find(session_id))

    def reveal(self, session_id: str, *, expected_item: int) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._find(session_id)
            self._active(row, expected_item)
            if not row["revealed"]:
                self._connection.execute(
                    "UPDATE flashcard_sessions SET revealed = 1 WHERE session_id = ?", (session_id,)
                )
            return self._record(self._find(session_id))

    def rate(
        self, session_id: str, rating: str, *, expected_item: int,
        now: datetime | None = None,
    ) -> dict:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._find(session_id)
            selected, state = self._active(row, expected_item)
            if not row["revealed"]:
                raise ValueError("Revele o verso antes de avaliar o cartão.")
            if not isinstance(rating, str) or rating not in RATINGS:
                raise ValueError("Autoavaliação não suportada.")
            instant = utc_instant(now)
            if instant < utc_instant(datetime.fromisoformat(row["created_at"])):
                raise ValueError("A revisão não pode anteceder a sessão.")
            if state is not None and instant < utc_instant(datetime.fromisoformat(state["last_reviewed_at"])):
                raise ValueError("A revisão não pode anteceder a revisão anterior.")
            scheduled = schedule_review(0 if state is None else state["box"], rating, instant)
            self._connection.execute(
                "INSERT INTO flashcard_states "
                "(material_id, material_version, item_index, box, state_version, due_at, last_reviewed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(material_id, material_version, item_index) DO UPDATE SET "
                "box = excluded.box, state_version = excluded.state_version, "
                "due_at = excluded.due_at, last_reviewed_at = excluded.last_reviewed_at",
                (row["material_id"], row["material_version"], expected_item, scheduled["box"],
                 selected["state_version"] + 1, scheduled["due_at"], instant.isoformat()),
            )
            self._connection.execute(
                "INSERT INTO flashcard_reviews "
                "(session_id, item_index, ordinal, rating, box, due_at, reviewed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, expected_item, row["position"], rating, scheduled["box"],
                 scheduled["due_at"], instant.isoformat()),
            )
            next_position = row["position"] + 1
            completed = next_position == len(json.loads(row["selection_json"]))
            self._connection.execute(
                "UPDATE flashcard_sessions SET position = ?, revealed = 0, status = ?, "
                "completed_at = ? WHERE session_id = ?",
                (next_position, "completed" if completed else "in_progress",
                 instant.isoformat() if completed else None, session_id),
            )
            # A concurrent review of the next card must not undo this valid review.
            return self._record(self._find(session_id), allow_stale_card=True)

    def list_sessions(self, *, status: str | None = None, limit: int = 20) -> list[dict]:
        if status is not None and status not in _STATUSES:
            raise ValueError("Estado de sessão inválido.")
        if type(limit) is not int or limit < 1:
            raise ValueError("O limite deve ser um inteiro positivo.")
        query = "SELECT * FROM flashcard_sessions"
        parameters: list = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC, session_id ASC LIMIT ?"
        parameters.append(limit)
        with self._connection:
            self._connection.execute("BEGIN")
            return [
                self._summary(row, json.loads(row["snapshot_json"]), json.loads(row["selection_json"]))
                for row in self._connection.execute(query, parameters).fetchall()
            ]
