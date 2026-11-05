"""Plano local de prática com prioridades explícitas, sem previsão de domínio."""

from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3

from ..storage.material_validation import references_current
from .grading import OBJECTIVE_TYPES
from .progress import progress_from_connection


def build_study_plan(
    database: str | Path,
    *,
    target_accuracy: float = 0.8,
    limit: int = 5,
    material_id: str | None = None,
) -> dict:
    """Prioriza questões fracas, diagnóstico e consolidação da versão atual.

    Materiais, referências e histórico são lidos na mesma transação. Recomendações
    relacionadas compartilham chunk_id, não uma relevância semântica inferida.
    O banco deve estar inicializado por Corpus, MaterialStore e StudyStore.
    """
    if (
        isinstance(target_accuracy, bool)
        or not isinstance(target_accuracy, (int, float))
        or not 0 < target_accuracy <= 1
        or not math.isfinite(target_accuracy)
    ):
        raise ValueError("A meta de acurácia deve ser um número finito maior que zero e até 1.")
    if type(limit) is not int or limit < 1:
        raise ValueError("O limite deve ser um inteiro positivo.")
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute("BEGIN")
            progress = progress_from_connection(connection, material_id=material_id)
            history = {
                (group["material_id"], group["material_version"]): group
                for group in progress["by_material"]
            }
            resources = []
            candidates = []
            rows = connection.execute(
                "SELECT material_id, version, body FROM materials WHERE status = 'approved'"
            ).fetchall()
            for row in rows:
                snapshot = {**json.loads(row["body"]), "status": "requires_review"}
                if not references_current(snapshot, connection):
                    continue
                kind = snapshot["kind"]
                if kind in ("aula", "flashcards"):
                    chunks = {
                        citation["chunk_id"]
                        for item in snapshot["items"]
                        for citation in item["citations"]
                    }
                    resources.append((row, snapshot, chunks))
                    continue
                if kind not in OBJECTIVE_TYPES or (
                    material_id is not None and row["material_id"] != material_id
                ):
                    continue
                group = history.get((row["material_id"], row["version"]))
                accuracy = group["accuracy"] if group is not None else None
                weak_items = [
                    item for item in group["items"] if item["accuracy"] < target_accuracy
                ] if group is not None else []
                attempts = group["completed_sessions"] if group is not None else 0
                if weak_items:
                    action = "review_errors"
                    priority = (0, min(item["accuracy"] for item in weak_items), attempts)
                elif group is None:
                    action = "diagnostic"
                    priority = (1, 0, 0)
                else:
                    action = "consolidate"
                    priority = (2, accuracy, attempts)
                candidates.append((
                    (*priority, row["material_id"]), row, snapshot, group, weak_items, action
                ))

            tasks = []
            for rank, (_, row, snapshot, group, weak_items, action) in enumerate(
                sorted(candidates, key=lambda entry: entry[0])[:limit], start=1
            ):
                focus = (
                    [snapshot["items"][item["item_index"]] for item in weak_items]
                    if weak_items else snapshot["items"]
                )
                sources = {}
                for item in focus:
                    for citation in item["citations"]:
                        sources[citation["chunk_id"]] = {
                            key: citation[key]
                            for key in ("doc_id", "chunk_id", "title", "source", "page")
                        }
                focus_chunks = set(sources)
                related = []
                for resource_row, resource, chunks in resources:
                    shared = chunks & focus_chunks
                    if shared:
                        related.append({
                            "material_id": resource_row["material_id"],
                            "material_version": resource_row["version"],
                            "kind": resource["kind"],
                            "title": resource["title"],
                            "shared_chunk_ids": sorted(shared),
                        })
                related.sort(key=lambda resource: (
                    0 if resource["kind"] == "aula" else 1, resource["material_id"]
                ))
                tasks.append({
                    "priority": rank,
                    "material_id": row["material_id"],
                    "material_version": row["version"],
                    "kind": snapshot["kind"],
                    "topic": snapshot["topic"],
                    "title": snapshot["title"],
                    "difficulty": snapshot["difficulty"],
                    "action": action,
                    "completed_sessions": group["completed_sessions"] if group is not None else 0,
                    "accuracy": group["accuracy"] if group is not None else None,
                    "weak_items": weak_items,
                    "sources": [sources[key] for key in sorted(sources)],
                    "resources": related[:3],
                })
            return {"target_accuracy": float(target_accuracy), "tasks": tasks}
