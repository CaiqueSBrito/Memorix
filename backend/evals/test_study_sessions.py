"""Regressões de estudo objetivo com aprovação, acervo e SQLite reais."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.materials import MaterialStore
from backend.src.Memorix.storage.study_sessions import StudyStore


class StudyStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.corpus.ingest_text(
            "O núcleo contém DNA. A membrana delimita a célula.",
            source="biologia", title="Biologia",
        )
        self.materials = MaterialStore(self.database)
        self.addCleanup(self.materials.close)
        self.sessions = StudyStore(self.database)
        self.addCleanup(self.sessions.close)

    def draft(self, kind="multipla_escolha", title="Estudo da célula"):
        if kind == "multipla_escolha":
            items = [
                {
                    "question": "O que o núcleo contém?",
                    "options": ["DNA", "Membrana", "Parede", "Cílio"],
                    "answer_index": 0,
                    "explanation": "O núcleo contém DNA, conforme o trecho.",
                },
                {
                    "question": "O que delimita a célula?",
                    "options": ["DNA", "Membrana", "Núcleo", "Cílio"],
                    "answer_index": 1,
                    "explanation": "A membrana delimita a célula, conforme o trecho.",
                },
            ]
        elif kind == "verdadeiro_falso":
            items = [
                {
                    "question": "O núcleo contém DNA.",
                    "answer": True,
                    "explanation": "O trecho afirma que o núcleo contém DNA.",
                },
                {
                    "question": "A membrana não delimita a célula.",
                    "answer": False,
                    "explanation": "O trecho afirma que a membrana delimita a célula.",
                },
            ]
        elif kind == "flashcards":
            items = [{"front": "O que o núcleo contém?", "back": "DNA."}]
        else:
            items = [{"heading": "Núcleo", "content": "O núcleo contém DNA."}]
        hits = self.corpus.search("núcleo")
        for item in items:
            item["citations"] = [{
                "chunk_id": hits[0].chunk_id,
                "quote": "O núcleo contém DNA. A membrana delimita a célula.",
            }]
        return validate_material(
            {"title": title, "items": items},
            GenerationRequest(kind, "Célula", count=len(items), difficulty="intermediaria"),
            hits,
        )

    def approve(self, kind="multipla_escolha"):
        created = self.materials.create(self.draft(kind))
        return self.materials.review(
            created["material_id"], "approve", expected_version=created["version"]
        )

    def start(self, material):
        return self.sessions.start(
            material["material_id"], expected_version=material["version"]
        )

    def replace_source(self, *, title="Biologia"):
        self.corpus.ingest_text(
            "O núcleo contém DNA. A membrana delimita a célula. Há outras organelas.",
            source="biologia", title=title,
        )

    def test_start_requires_human_approval_and_the_current_version(self):
        created = self.materials.create(self.draft())
        with self.assertRaises(ValueError):
            self.start(created)
        self.assertEqual(self.sessions.list_sessions(), [])
        approved = self.materials.review(
            created["material_id"], "approve", expected_version=created["version"]
        )
        with self.assertRaises(ValueError):
            self.start(created)
        self.assertEqual(self.sessions.list_sessions(), [])
        started = self.start(approved)
        self.assertEqual(started["material_version"], approved["version"])
        rejected = self.materials.create(self.draft())
        rejected = self.materials.review(
            rejected["material_id"], "reject", expected_version=rejected["version"]
        )
        with self.assertRaises(ValueError):
            self.start(rejected)
        self.assertEqual(len(self.sessions.list_sessions()), 1)

    def test_approved_flashcards_and_lessons_cannot_be_scored(self):
        for kind in ("flashcards", "aula"):
            with self.subTest(kind=kind):
                approved = self.approve(kind)
                with self.assertRaises(ValueError):
                    self.start(approved)
        self.assertEqual(self.sessions.list_sessions(), [])

    def test_obsolete_sources_prevent_starting_an_approved_material(self):
        approved = self.approve()
        self.replace_source()
        self.assertFalse(self.materials.get(approved["material_id"])["sources_current"])
        with self.assertRaises(ValueError):
            self.start(approved)
        self.assertEqual(self.sessions.list_sessions(), [])

    def test_pending_questions_and_all_summaries_hide_answers_and_references(self):
        for kind in ("multipla_escolha", "verdadeiro_falso"):
            with self.subTest(kind=kind):
                approved = self.approve(kind)
                started = self.start(approved)
                self.assertEqual(started["status"], "in_progress")
                self.assertIsNone(started["completed_at"])
                self.assertTrue(started["material_current"])
                self.assertTrue(started["sources_current"])
                self.assertNotIn("result", started)
                for index, question in enumerate(started["questions"]):
                    expected = {
                        "item_index": index,
                        "question": approved["items"][index]["question"],
                    }
                    if kind == "multipla_escolha":
                        expected["options"] = approved["items"][index]["options"]
                    self.assertEqual(question, expected)
                self.assertEqual(self.sessions.get(started["session_id"]), started)
                answers = [0, 1] if kind == "multipla_escolha" else [True, False]
                completed = self.sessions.submit(started["session_id"], answers)
                for record in (started, completed):
                    listed = self.sessions.list_sessions(status=record["status"])
                    if record["status"] == "in_progress":
                        self.assertEqual(listed, [])
                    else:
                        summary = next(
                            row for row in listed if row["session_id"] == record["session_id"]
                        )
                        self.assertEqual(
                            summary, {key: value for key, value in record.items() if key != "result"}
                        )
                for record in (started, completed):
                    self.assertFalse({"items", "answers", "answers_json", "snapshot_json"} & set(record))

    def test_pending_list_contains_only_public_session_metadata(self):
        approved = self.approve()
        started = self.start(approved)
        self.assertEqual(
            self.sessions.list_sessions(status="in_progress"),
            [{key: value for key, value in started.items() if key != "questions"}],
        )

    def test_multiple_choice_and_true_false_grade_correct_and_wrong_answers(self):
        cases = [
            ("multipla_escolha", [0, 3], [0, 1]),
            ("verdadeiro_falso", [True, True], [True, False]),
        ]
        for kind, answers, expected_answers in cases:
            with self.subTest(kind=kind):
                approved = self.approve(kind)
                started = self.start(approved)
                completed = self.sessions.submit(started["session_id"], answers)
                self.assertEqual(completed["status"], "completed")
                self.assertNotIn("questions", completed)
                result = completed["result"]
                self.assertEqual(result["total_count"], 2)
                self.assertEqual(result["correct_count"], 1)
                self.assertEqual(result["accuracy"], 0.5)
                self.assertEqual([item["correct"] for item in result["items"]], [True, False])
                self.assertEqual([item["answer"] for item in result["items"]], answers)
                self.assertEqual(
                    [item["expected_answer"] for item in result["items"]], expected_answers
                )
                for index, feedback in enumerate(result["items"]):
                    self.assertEqual(feedback["item_index"], index)
                    self.assertEqual(feedback["explanation"], approved["items"][index]["explanation"])
                    self.assertEqual(feedback["citations"], approved["items"][index]["citations"])
                self.assertEqual(self.sessions.get(started["session_id"]), completed)
                for timestamp in (completed["created_at"], completed["completed_at"]):
                    self.assertEqual(datetime.fromisoformat(timestamp).utcoffset(), timedelta(0))

    def test_invalid_or_incomplete_answers_never_partially_complete_a_session(self):
        common_invalid = (None, {}, "resposta privada", [], [0], [0, 1, 2], (0, 1))
        cases = [
            ("multipla_escolha", [0, 1],
             (*common_invalid, [0, True], [0, False], [0, -1], [0, 4], [0, 1.0],
              [0, "resposta privada"], [0, None], [0, []])),
            ("verdadeiro_falso", [True, False],
             (*common_invalid, [True, 0], [True, 1], [True, "false"], [True, None],
              [True, []])),
        ]
        for kind, valid, invalid_answers in cases:
            with self.subTest(kind=kind):
                started = self.start(self.approve(kind))
                for answers in invalid_answers:
                    with self.subTest(answers=answers):
                        with self.assertRaises(ValueError) as error:
                            self.sessions.submit(started["session_id"], answers)
                        self.assertNotIn("resposta privada", str(error.exception))
                        self.assertEqual(self.sessions.get(started["session_id"]), started)
                        self.assertFalse(any(
                            row["session_id"] == started["session_id"]
                            for row in self.sessions.list_sessions(status="completed")
                        ))
                completed = self.sessions.submit(started["session_id"], valid)
                self.assertEqual(completed["result"]["correct_count"], 2)

    def test_submission_is_final_across_connections_and_survives_reopening(self):
        started = self.start(self.approve())
        with StudyStore(self.database) as reopened:
            self.assertEqual(reopened.get(started["session_id"]), started)
            completed = reopened.submit(started["session_id"], [0, 1])
        with self.assertRaises(ValueError):
            self.sessions.submit(started["session_id"], [3, 2])
        self.assertEqual(self.sessions.get(started["session_id"]), completed)
        with StudyStore(self.database) as reopened:
            self.assertEqual(reopened.get(started["session_id"]), completed)
            self.assertEqual(len(reopened.list_sessions(status="completed")), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            reopened.list_sessions()

    def test_concurrent_submissions_have_exactly_one_winner(self):
        started = self.start(self.approve())
        ready = Barrier(2)

        def submit(answers):
            with StudyStore(self.database) as store:
                ready.wait(timeout=10)
                try:
                    return store.submit(started["session_id"], answers)
                except ValueError:
                    return None

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(submit, ([0, 1], [3, 2])))
        completed = [result for result in results if result is not None]
        self.assertEqual(len(completed), 1)
        self.assertEqual(self.sessions.get(started["session_id"]), completed[0])
        self.assertEqual(len(self.sessions.list_sessions(status="completed")), 1)

    def test_material_edits_block_pending_sessions_even_after_reapproval(self):
        approved = self.approve()
        started = self.start(approved)
        edited = self.materials.update(
            approved["material_id"], self.draft(title="Questionário revisado"),
            expected_version=approved["version"],
        )
        for material in (edited, None):
            if material is None:
                material = self.materials.review(
                    edited["material_id"], "approve", expected_version=edited["version"]
                )
            with self.subTest(status=material["status"]):
                listed = self.sessions.list_sessions(status="in_progress")
                self.assertEqual(len(listed), 1)
                self.assertFalse(listed[0]["material_current"])
                self.assertTrue(listed[0]["sources_current"])
                self.assertEqual(listed[0]["title"], approved["title"])
                with self.assertRaises(ValueError):
                    self.sessions.get(started["session_id"])
                with self.assertRaises(ValueError):
                    self.sessions.submit(started["session_id"], [0, 1])
                self.assertEqual(self.sessions.list_sessions(status="in_progress"), listed)
                self.assertEqual(self.sessions.list_sessions(status="completed"), [])
        self.assertEqual(self.start(material)["material_version"], material["version"])

    def test_source_text_or_metadata_edits_block_pending_sessions_but_not_listing(self):
        for title in ("Biologia", "Fonte renomeada"):
            with self.subTest(title=title):
                started = self.start(self.approve())
                self.replace_source(title=title)
                summary = next(
                    row for row in self.sessions.list_sessions()
                    if row["session_id"] == started["session_id"]
                )
                self.assertTrue(summary["material_current"])
                self.assertFalse(summary["sources_current"])
                self.assertNotIn("questions", summary)
                self.assertNotIn("result", summary)
                with self.assertRaises(ValueError):
                    self.sessions.get(started["session_id"])
                with self.assertRaises(ValueError):
                    self.sessions.submit(started["session_id"], [0, 1])
                self.assertEqual(self.sessions.list_sessions(status="completed"), [])

    def test_completed_feedback_uses_the_frozen_material_after_answers_and_sources_change(self):
        approved = self.approve()
        started = self.start(approved)
        completed = self.sessions.submit(started["session_id"], [0, 1])
        original_result = deepcopy(completed["result"])
        revised = self.draft(title="Versão com outro gabarito")
        revised["items"][0]["question"] = "Qual alternativa foi revisada?"
        revised["items"][0]["answer_index"] = 2
        revised["items"][0]["explanation"] = "Explicação revisada após a primeira tentativa."
        edited = self.materials.update(
            approved["material_id"], revised, expected_version=approved["version"]
        )
        reapproved = self.materials.review(
            edited["material_id"], "approve", expected_version=edited["version"]
        )
        historical = self.sessions.get(started["session_id"])
        self.assertFalse(historical["material_current"])
        self.assertTrue(historical["sources_current"])
        self.assertEqual(historical["title"], approved["title"])
        self.assertEqual(historical["result"], original_result)
        new_session = self.start(reapproved)
        new_result = self.sessions.submit(new_session["session_id"], [0, 1])["result"]
        self.assertEqual(new_result["correct_count"], 1)
        self.assertEqual(new_result["items"][0]["expected_answer"], 2)
        self.replace_source()
        with StudyStore(self.database) as reopened:
            historical = reopened.get(started["session_id"])
            self.assertFalse(historical["material_current"])
            self.assertFalse(historical["sources_current"])
            self.assertEqual(historical["result"], original_result)
            summary = next(
                row for row in reopened.list_sessions(status="completed")
                if row["session_id"] == started["session_id"]
            )
            self.assertNotIn("result", summary)
            self.assertFalse(summary["sources_current"])

    def test_storage_failures_roll_back_start_and_submit_and_release_transactions(self):
        approved = self.approve()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_session_insert AFTER INSERT ON study_sessions "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.start(approved)
        self.assertEqual(self.sessions.list_sessions(), [])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_session_insert")
        started = self.start(approved)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_session_update AFTER UPDATE ON study_sessions "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.sessions.submit(started["session_id"], [0, 1])
        self.assertEqual(self.sessions.get(started["session_id"]), started)
        self.assertEqual(self.sessions.list_sessions(status="completed"), [])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_session_update")
        self.assertEqual(self.sessions.submit(started["session_id"], [0, 1])["status"], "completed")

    def test_listing_filters_limits_and_preserves_completed_and_pending_sessions(self):
        approved = self.approve()
        pending = self.start(approved)
        completed = self.start(approved)
        completed = self.sessions.submit(completed["session_id"], [0, 1])
        listed = self.sessions.list_sessions()
        self.assertEqual(
            [row["session_id"] for row in listed],
            [completed["session_id"], pending["session_id"]],
        )
        self.assertEqual(self.sessions.list_sessions(limit=1), listed[:1])
        for status, record in (("in_progress", pending), ("completed", completed)):
            with self.subTest(status=status):
                self.assertEqual(
                    [row["session_id"] for row in self.sessions.list_sessions(status=status)],
                    [record["session_id"]],
                )

    def test_invalid_versions_identifiers_and_listing_domains_do_not_create_sessions(self):
        approved = self.approve()
        for version in (True, False, 0, -1, 2.0, "2", None, []):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.sessions.start(approved["material_id"], expected_version=version)
        for material_id in ("inexistente", "", " ", None, []):
            with self.subTest(material_id=material_id), self.assertRaises(ValueError):
                self.sessions.start(material_id, expected_version=approved["version"])
        for session_id in ("inexistente", "", " ", None, []):
            with self.subTest(session_id=session_id):
                with self.assertRaises(ValueError):
                    self.sessions.get(session_id)
                with self.assertRaises(ValueError):
                    self.sessions.submit(session_id, [0, 1])
        for status in ("approved", "unknown", "", True, []):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.sessions.list_sessions(status=status)
        for limit in (0, -1, True, False, 1.0, "1", None, []):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.sessions.list_sessions(limit=limit)
        self.assertEqual(self.sessions.list_sessions(), [])


if __name__ == "__main__":
    unittest.main()
