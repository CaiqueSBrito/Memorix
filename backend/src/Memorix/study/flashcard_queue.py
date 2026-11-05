"""Fila local de cartões novos ou vencidos, sem expor verso ou evidências."""

from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from ..storage.material_validation import references_current
from .flashcard_schedule import utc_instant


def cards_from_connection(
    connection: sqlite3.Connection,
    *,
    material_id: str | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> dict:
    """Lê um snapshot na transação do chamador, que deve usar sqlite3.Row.

    O banco já deve conter os esquemas de Corpus, MaterialStore e FlashcardStore.
    Não abre ou encerra transações, nem reserva cartões para uma sessão.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("O limite deve ser um inteiro positivo.")
    instant = utc_instant(now)
    if material_id is not None:
        if not isinstance(material_id, str) or not material_id.strip():
            raise ValueError("Identificador de material inválido.")
        rows = connection.execute(
            "SELECT material_id, body, status, version FROM materials WHERE material_id = ?",
            (material_id,),
        ).fetchall()
        if not rows:
            raise ValueError("Material não encontrado.")
    else:
        rows = connection.execute(
            "SELECT material_id, body, status, version FROM materials WHERE status = 'approved'"
        ).fetchall()

    candidates = []
    for row in rows:
        if row["status"] != "approved":
            continue
        snapshot = {**json.loads(row["body"]), "status": "requires_review"}
        if snapshot.get("kind") != "flashcards" or not references_current(snapshot, connection):
            continue
        states = {
            state["item_index"]: state
            for state in connection.execute(
                "SELECT item_index, box, state_version, due_at FROM flashcard_states "
                "WHERE material_id = ? AND material_version = ?",
                (row["material_id"], row["version"]),
            )
        }
        for item_index, item in enumerate(snapshot["items"]):
            state = states.get(item_index)
            due = None if state is None else utc_instant(datetime.fromisoformat(state["due_at"]))
            if due is not None and due > instant:
                continue
            card = {
                "material_id": row["material_id"],
                "material_version": row["version"],
                "item_index": item_index,
                "title": snapshot["title"],
                "topic": snapshot["topic"],
                "difficulty": snapshot["difficulty"],
                "front": item["front"],
                "box": 0 if state is None else state["box"],
                "due_at": None if due is None else due.isoformat(),
                "state_version": 0 if state is None else state["state_version"],
            }
            priority = (due is None, instant if due is None else due, row["material_id"], item_index)
            candidates.append((priority, card))
    candidates.sort(key=lambda candidate: candidate[0])
    return {"as_of": instant.isoformat(), "cards": [card for _, card in candidates[:limit]]}


def flashcard_queue(
    database: str | Path,
    *,
    material_id: str | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> dict:
    """Consulta consistente e somente leitura com uma conexão própria e fechada."""
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute("BEGIN")
            return cards_from_connection(connection, material_id=material_id, limit=limit, now=now)
