"""Acurácia local anônima derivada das tentativas concluídas e imutáveis."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .grading import grade_answers


def progress_summary(database: str | Path, *, material_id: str | None = None) -> dict:
    """Agrega respostas por questão, preservando versões e gabaritos históricos."""
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute("BEGIN")
            return progress_from_connection(connection, material_id=material_id)


def progress_from_connection(
    connection: sqlite3.Connection, *, material_id: str | None = None
) -> dict:
    """Agrega no snapshot do chamador; exige transação aberta e sqlite3.Row."""
    if material_id is not None and (
        not isinstance(material_id, str) or not material_id.strip()
    ):
        raise ValueError("Identificador de material inválido.")

    summary = {
        "completed_sessions": 0,
        "answered_items": 0,
        "correct_items": 0,
        "accuracy": None,
        "by_material": [],
    }
    groups = {}
    if material_id is not None:
        material = connection.execute(
            "SELECT 1 FROM materials WHERE material_id = ?", (material_id,)
        ).fetchone()
        if material is None:
            raise ValueError("Material não encontrado.")
    query = (
        "SELECT material_id, material_version, snapshot_json, answers_json "
        "FROM study_sessions WHERE status = 'completed'"
    )
    parameters = []
    if material_id is not None:
        query += " AND material_id = ?"
        parameters.append(material_id)
    for row in connection.execute(query, parameters):
        snapshot = json.loads(row["snapshot_json"])
        result = grade_answers(snapshot, json.loads(row["answers_json"]))
        key = (row["material_id"], row["material_version"])
        group = groups.get(key)
        if group is None:
            group = {
                "material_id": row["material_id"],
                "material_version": row["material_version"],
                "kind": snapshot["kind"],
                "topic": snapshot["topic"],
                "title": snapshot["title"],
                "completed_sessions": 0,
                "answered_items": 0,
                "correct_items": 0,
                "accuracy": None,
                "items": {},
            }
            groups[key] = group
        for aggregate in (summary, group):
            aggregate["completed_sessions"] += 1
            aggregate["answered_items"] += result["total_count"]
            aggregate["correct_items"] += result["correct_count"]
        for feedback in result["items"]:
            index = feedback["item_index"]
            item = group["items"].get(index)
            if item is None:
                item = {"item_index": index, "attempts": 0, "correct": 0}
                group["items"][index] = item
            item["attempts"] += 1
            item["correct"] += int(feedback["correct"])

    if summary["answered_items"]:
        summary["accuracy"] = summary["correct_items"] / summary["answered_items"]
    for key in sorted(groups):
        group = groups[key]
        group["accuracy"] = group["correct_items"] / group["answered_items"]
        items = []
        for index in sorted(group["items"]):
            item = group["items"][index]
            item["accuracy"] = item["correct"] / item["attempts"]
            items.append(item)
        group["items"] = items
        summary["by_material"].append(group)
    return summary
