"""Progresso anônimo com acervo, materiais e sessões persistentes reais."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.materials import MaterialStore
from backend.src.Memorix.storage.study_sessions import StudyStore
from backend.src.Memorix.study.progress import progress_summary


class StudyProgressTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.text = (
            "O núcleo contém DNA. A membrana delimita a célula. "
            "As mitocôndrias produzem energia."
        )
        self.corpus.ingest_text(self.text, source="biologia", title="Biologia")
        self.materials = MaterialStore(self.database)
        self.addCleanup(self.materials.close)
        self.sessions = StudyStore(self.database)
        self.addCleanup(self.sessions.close)

    def draft(self, kind="multipla_escolha", *, count=1, title="Estudo da célula"):
        if kind == "multipla_escolha":
            items = [
                {
                    "question": "O que o núcleo contém?",
                    "options": ["DNA", "Amido", "Celulose", "Glicogênio"],
                    "answer_index": 0,
                    "explanation": "O núcleo contém DNA.",
                },
                {
                    "question": "O que delimita a célula?",
                    "options": ["Núcleo", "Membrana", "DNA", "Ribossomo"],
                    "answer_index": 1,
                    "explanation": "A membrana delimita a célula.",
                },
                {
                    "question": "O que produz energia?",
                    "options": ["Núcleo", "Membrana", "Mitocôndrias", "DNA"],
                    "answer_index": 2,
                    "explanation": "As mitocôndrias produzem energia.",
                },
            ]
        else:
            items = [
                {
                    "question": "O núcleo contém DNA.",
                    "answer": True,
                    "explanation": "O núcleo contém DNA.",
                },
                {
                    "question": "A membrana não delimita a célula.",
                    "answer": False,
                    "explanation": "A membrana delimita a célula.",
                },
                {
                    "question": "As mitocôndrias produzem energia.",
                    "answer": True,
                    "explanation": "As mitocôndrias produzem energia.",
                },
            ]
        hits = self.corpus.search("núcleo")
        for item in items:
            item["citations"] = [{"chunk_id": hits[0].chunk_id, "quote": self.text}]
        return validate_material(
            {"title": title, "items": items[:count]},
            GenerationRequest(kind, "Célula", count=count),
            hits,
        )

    def approve(self, kind="multipla_escolha", *, count=1, title="Estudo da célula"):
        created = self.materials.create(self.draft(kind, count=count, title=title))
        return self.materials.review(
            created["material_id"], "approve", expected_version=created["version"]
        )

    def start(self, material):
        return self.sessions.start(
            material["material_id"], expected_version=material["version"]
        )

    def complete(self, material, answers):
        session = self.start(material)
        return self.sessions.submit(session["session_id"], answers)

    def test_no_completed_attempts_have_no_accuracy_or_material_groups(self):
        expected = {
            "completed_sessions": 0,
            "answered_items": 0,
            "correct_items": 0,
            "accuracy": None,
            "by_material": [],
        }
        self.assertEqual(progress_summary(self.database), expected)
        for kind in ("multipla_escolha", "verdadeiro_falso"):
            material = self.approve(kind, count=3)
            self.start(material)
            self.assertEqual(
                progress_summary(self.database, material_id=material["material_id"]),
                expected,
            )
        self.assertEqual(progress_summary(self.database), expected)

    def test_both_question_types_use_answer_weighted_accuracy_and_no_raw_answers(self):
        multiple_choice = self.approve(title="Uma questão de múltipla escolha")
        true_false = self.approve(
            "verdadeiro_falso", count=3, title="Três questões de verdadeiro ou falso"
        )
        self.complete(multiple_choice, [0])
        self.complete(true_false, [True, True, False])
        self.start(true_false)
        summary = progress_summary(self.database)
        groups = [
            {
                "material_id": multiple_choice["material_id"],
                "material_version": multiple_choice["version"],
                "kind": "multipla_escolha",
                "topic": "Célula",
                "title": multiple_choice["title"],
                "completed_sessions": 1,
                "answered_items": 1,
                "correct_items": 1,
                "accuracy": 1.0,
                "items": [
                    {"item_index": 0, "attempts": 1, "correct": 1, "accuracy": 1.0}
                ],
            },
            {
                "material_id": true_false["material_id"],
                "material_version": true_false["version"],
                "kind": "verdadeiro_falso",
                "topic": "Célula",
                "title": true_false["title"],
                "completed_sessions": 1,
                "answered_items": 3,
                "correct_items": 1,
                "accuracy": 1 / 3,
                "items": [
                    {"item_index": 0, "attempts": 1, "correct": 1, "accuracy": 1.0},
                    {"item_index": 1, "attempts": 1, "correct": 0, "accuracy": 0.0},
                    {"item_index": 2, "attempts": 1, "correct": 0, "accuracy": 0.0},
                ],
            },
        ]
        self.assertEqual(summary, {
            "completed_sessions": 2,
            "answered_items": 4,
            "correct_items": 2,
            "accuracy": 0.5,
            "by_material": sorted(groups, key=lambda group: group["material_id"]),
        })

    def test_distinct_attempts_accumulate_per_question_in_index_order(self):
        material = self.approve(count=3)
        first = self.complete(material, [0, 1, 0])
        second = self.complete(material, [3, 1, 2])
        self.assertNotEqual(first["session_id"], second["session_id"])
        summary = progress_summary(self.database)
        self.assertEqual(summary["completed_sessions"], 2)
        self.assertEqual(summary["answered_items"], 6)
        self.assertEqual(summary["correct_items"], 4)
        self.assertEqual(summary["accuracy"], 2 / 3)
        group = summary["by_material"][0]
        self.assertEqual(group["completed_sessions"], 2)
        self.assertEqual(group["answered_items"], 6)
        self.assertEqual(group["correct_items"], 4)
        self.assertEqual(group["accuracy"], 2 / 3)
        self.assertEqual(group["items"], [
            {"item_index": 0, "attempts": 2, "correct": 1, "accuracy": 0.5},
            {"item_index": 1, "attempts": 2, "correct": 2, "accuracy": 1.0},
            {"item_index": 2, "attempts": 2, "correct": 1, "accuracy": 0.5},
        ])

    def test_edited_reapproved_versions_keep_separate_keys_and_grading(self):
        original = self.approve(title="Primeira versão")
        historical = self.complete(original, [0])
        revised = self.draft(title="Versão revista")
        revised["items"][0]["options"] = ["Amido", "DNA", "Celulose", "Glicogênio"]
        revised["items"][0]["answer_index"] = 1
        edited = self.materials.update(
            original["material_id"], revised, expected_version=original["version"]
        )
        current = self.materials.review(
            edited["material_id"], "approve", expected_version=edited["version"]
        )
        self.complete(current, [0])
        summary = progress_summary(self.database, material_id=original["material_id"])
        self.assertEqual(summary["completed_sessions"], 2)
        self.assertEqual(summary["answered_items"], 2)
        self.assertEqual(summary["correct_items"], 1)
        self.assertEqual(summary["accuracy"], 0.5)
        groups = summary["by_material"]
        self.assertEqual(
            [(group["material_id"], group["material_version"]) for group in groups],
            [(original["material_id"], original["version"]),
             (current["material_id"], current["version"])],
        )
        self.assertEqual([group["title"] for group in groups],
                         ["Primeira versão", "Versão revista"])
        self.assertEqual([group["completed_sessions"] for group in groups], [1, 1])
        self.assertEqual([group["accuracy"] for group in groups], [1.0, 0.0])
        self.assertEqual(groups[0]["items"], [
            {"item_index": 0, "attempts": 1, "correct": 1, "accuracy": 1.0}
        ])
        self.assertEqual(groups[1]["items"], [
            {"item_index": 0, "attempts": 1, "correct": 0, "accuracy": 0.0}
        ])
        self.assertEqual(
            self.sessions.get(historical["session_id"])["result"]["correct_count"], 1
        )

    def test_completed_history_survives_replaced_sources_and_reopened_connections(self):
        material = self.approve("verdadeiro_falso", count=3)
        completed = self.complete(material, [True, False, False])
        before = progress_summary(self.database)
        self.corpus.ingest_text(
            "O núcleo contém DNA. O citoplasma contém organelas.",
            source="biologia",
            title="Biologia atualizada",
        )
        self.assertFalse(self.materials.get(material["material_id"])["sources_current"])
        with StudyStore(self.database) as reopened:
            historical = reopened.get(completed["session_id"])
            self.assertFalse(historical["sources_current"])
            self.assertEqual(historical["result"]["correct_count"], 2)
        self.assertEqual(progress_summary(self.database), before)
        self.assertEqual(
            progress_summary(self.database, material_id=material["material_id"]), before
        )

    def test_material_filter_excludes_other_materials_with_the_same_topic(self):
        selected = self.approve(count=3)
        other = self.approve(count=3)
        self.complete(selected, [0, 1, 0])
        self.complete(other, [3, 0, 2])
        self.complete(other, [3, 0, 0])
        all_progress = progress_summary(self.database)
        filtered = progress_summary(self.database, material_id=selected["material_id"])
        self.assertEqual(filtered["completed_sessions"], 1)
        self.assertEqual(filtered["answered_items"], 3)
        self.assertEqual(filtered["correct_items"], 2)
        self.assertEqual(filtered["accuracy"], 2 / 3)
        self.assertEqual(filtered["by_material"], [
            group for group in all_progress["by_material"]
            if group["material_id"] == selected["material_id"]
        ])
        self.assertEqual(all_progress["completed_sessions"], 3)
        self.assertEqual(all_progress["answered_items"], 9)
        self.assertEqual(all_progress["correct_items"], 3)

    def test_invalid_unknown_or_sql_shaped_material_filter_is_rejected(self):
        material = self.approve()
        self.complete(material, [0])
        before = progress_summary(self.database)
        for material_id in ("", " ", 0, True, [], {}, "desconhecido", "' OR 1=1 --"):
            with self.subTest(material_id=material_id):
                with self.assertRaises(ValueError):
                    progress_summary(self.database, material_id=material_id)
        self.assertEqual(progress_summary(self.database), before)

    def test_second_submission_cannot_inflate_or_replace_progress(self):
        material = self.approve("verdadeiro_falso", count=3)
        completed = self.complete(material, [True, False, False])
        before = progress_summary(self.database)
        for answers in ([True, False, True], [True, False, False]):
            with self.subTest(answers=answers):
                with self.assertRaises(ValueError):
                    self.sessions.submit(completed["session_id"], answers)
                self.assertEqual(progress_summary(self.database), before)

    def test_storage_failure_is_not_reported_as_empty_progress(self):
        material = self.approve()
        self.complete(material, [0])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE study_sessions")
        with self.assertRaises(sqlite3.OperationalError):
            progress_summary(self.database)


if __name__ == "__main__":
    unittest.main()
