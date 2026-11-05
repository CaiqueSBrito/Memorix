"""Prioridades e indicações do plano com materiais, fontes e tentativas reais."""

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
from backend.src.Memorix.study.planning import build_study_plan
from backend.src.Memorix.study.progress import progress_summary


class StudyPlanningTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.text = "O núcleo contém DNA. A mitocôndria produz energia."
        self.corpus.ingest_text(
            self.text, source="biologia", title="Biologia", chunk_size=4, overlap=0
        )
        self.hits = [self.corpus.search("núcleo")[0], self.corpus.search("mitocôndria")[0]]
        self.materials = MaterialStore(self.database)
        self.addCleanup(self.materials.close)
        self.sessions = StudyStore(self.database)
        self.addCleanup(self.sessions.close)

    def draft(self, kind="verdadeiro_falso", focus=(0,), title="Biologia"):
        items = []
        for index in focus:
            hit = self.hits[index]
            if kind == "verdadeiro_falso":
                item = {"question": hit.text, "answer": True, "explanation": hit.text}
            elif kind == "multipla_escolha":
                item = {
                    "question": "O que o núcleo contém?",
                    "options": ["DNA", "Amido", "Clorofila", "Celulose"],
                    "answer_index": 0,
                    "explanation": hit.text,
                }
            elif kind == "aula":
                item = {"heading": "Conceito", "content": hit.text}
            else:
                item = {"front": "Qual conceito é descrito?", "back": hit.text}
            item["citations"] = [{"chunk_id": hit.chunk_id, "quote": hit.text}]
            items.append(item)
        return validate_material(
            {"title": title, "items": items},
            GenerationRequest(kind, "biologia", count=len(items)),
            self.hits,
        )

    def material(self, kind="verdadeiro_falso", focus=(0,), title="Biologia", status="approved"):
        created = self.materials.create(self.draft(kind, focus, title))
        if status == "requires_review":
            return created
        return self.materials.review(
            created["material_id"], "approve" if status == "approved" else "reject",
            expected_version=created["version"],
        )

    def complete(self, material, answers):
        session = self.sessions.start(
            material["material_id"], expected_version=material["version"]
        )
        return self.sessions.submit(session["session_id"], answers)

    def test_weak_questions_outrank_diagnostics_and_consolidation_even_at_global_target(self):
        failed = self.material(title="Erros")
        self.complete(failed, [False])
        mixed = self.material(focus=(0, 1), title="Média na meta, uma questão fraca")
        for second in (False, False, True, True, True):
            self.complete(mixed, [True, second])
        unseen = self.material("multipla_escolha", title="Diagnóstico")
        mastered = self.material(title="Consolidação")
        self.complete(mastered, [True])
        tasks = build_study_plan(self.database)["tasks"]
        self.assertEqual(
            [task["material_id"] for task in tasks],
            [failed["material_id"], mixed["material_id"], unseen["material_id"], mastered["material_id"]],
        )
        self.assertEqual([task["action"] for task in tasks], ["review_errors", "review_errors", "diagnostic", "consolidate"])
        self.assertEqual(tasks[1]["accuracy"], 0.8)
        self.assertEqual(tasks[1]["weak_items"], [{"item_index": 1, "attempts": 5, "correct": 3, "accuracy": 0.6}])
        self.assertEqual([source["chunk_id"] for source in tasks[1]["sources"]], [self.hits[1].chunk_id])
        self.assertEqual([task["material_id"] for task in build_study_plan(self.database, limit=2)["tasks"]], [failed["material_id"], mixed["material_id"]])

    def test_exact_target_is_not_weak_and_a_higher_target_changes_the_action(self):
        material = self.material()
        self.complete(material, [True])
        self.complete(material, [False])
        at_target = build_study_plan(self.database, target_accuracy=0.5)["tasks"][0]
        below_target = build_study_plan(self.database, target_accuracy=0.5001)["tasks"][0]
        self.assertEqual(at_target["action"], "consolidate")
        self.assertEqual(at_target["weak_items"], [])
        self.assertEqual(below_target["action"], "review_errors")
        self.assertEqual(below_target["weak_items"][0]["accuracy"], 0.5)

    def test_equally_weak_materials_prioritize_fewer_completed_attempts(self):
        fewer = self.material(title="Uma tentativa")
        more = self.material(title="Duas tentativas")
        self.complete(fewer, [False])
        self.complete(more, [False])
        self.complete(more, [False])
        tasks = build_study_plan(self.database)["tasks"]
        self.assertEqual([task["material_id"] for task in tasks], [fewer["material_id"], more["material_id"]])
        self.assertEqual([task["completed_sessions"] for task in tasks], [1, 2])

    def test_recommendations_match_weak_chunk_not_just_document_or_topic(self):
        target = self.material(focus=(0, 1))
        self.complete(target, [True, False])
        matching_lesson = self.material("aula", focus=(1,), title="Energia")
        matching_cards = self.material("flashcards", focus=(1,), title="Recuperação")
        self.material("aula", focus=(0,), title="Mesmo documento, outro trecho")
        self.material("aula", focus=(1,), status="requires_review")
        self.material("aula", focus=(1,), status="rejected")
        plan = build_study_plan(self.database, material_id=target["material_id"])
        task = plan["tasks"][0]
        self.assertEqual([resource["material_id"] for resource in task["resources"]], [matching_lesson["material_id"], matching_cards["material_id"]])
        for resource in task["resources"]:
            self.assertEqual(resource["shared_chunk_ids"], [self.hits[1].chunk_id])
        self.assertEqual(task["sources"][0]["doc_id"], self.hits[1].doc_id)
        self.assertEqual(task["sources"][0]["source"], "biologia")
        self.assertIsNone(task["sources"][0]["page"])
        self.assertNotIn("items", task)
        self.assertNotIn("quote", task["sources"][0])

    def test_stale_materials_and_related_resources_are_never_recommended(self):
        current = self.material(focus=(0,))
        self.material(focus=(1,), title="Fonte que vai mudar")
        self.material("aula", focus=(1,))
        current_lesson = self.material("aula", focus=(0,))
        self.material(focus=(0,), status="requires_review")
        self.material(focus=(0,), status="rejected")
        self.corpus.ingest_text(
            "O núcleo contém DNA. A mitocôndria sintetiza ATP.",
            source="biologia", title="Biologia", chunk_size=4, overlap=0,
        )
        tasks = build_study_plan(self.database)["tasks"]
        self.assertEqual([task["material_id"] for task in tasks], [current["material_id"]])
        self.assertEqual([resource["material_id"] for resource in tasks[0]["resources"]], [current_lesson["material_id"]])
        self.corpus.ingest_text(
            "O núcleo contém DNA. A mitocôndria sintetiza ATP.",
            source="biologia", title="Fonte renomeada", chunk_size=4, overlap=0,
        )
        self.assertEqual(build_study_plan(self.database)["tasks"], [])

    def test_new_approved_version_starts_diagnostic_without_reusing_old_answers(self):
        old = self.material()
        self.complete(old, [False])
        edited = self.materials.update(
            old["material_id"], self.draft(title="Nova versão"), expected_version=old["version"]
        )
        self.assertEqual(build_study_plan(self.database)["tasks"], [])
        current = self.materials.review(edited["material_id"], "approve", expected_version=edited["version"])
        task = build_study_plan(self.database)["tasks"][0]
        self.assertEqual(task["material_version"], current["version"])
        self.assertEqual(task["action"], "diagnostic")
        self.assertIsNone(task["accuracy"])
        self.assertEqual(task["completed_sessions"], 0)
        self.complete(current, [True])
        task = build_study_plan(self.database)["tasks"][0]
        self.assertEqual(task["accuracy"], 1.0)
        self.assertEqual(task["action"], "consolidate")

    def test_diagnostic_plan_does_not_create_attempts_or_count_open_sessions(self):
        material = self.material()
        self.sessions.start(material["material_id"], expected_version=material["version"])
        before = progress_summary(self.database)
        plan = build_study_plan(self.database)
        self.assertEqual(plan["tasks"][0]["action"], "diagnostic")
        self.assertEqual(progress_summary(self.database), before)
        self.assertEqual(len(self.sessions.list_sessions()), 1)

    def test_filter_and_invalid_parameters_do_not_fall_back_to_other_materials(self):
        first = self.material()
        self.material("multipla_escolha")
        filtered = build_study_plan(self.database, material_id=first["material_id"])
        self.assertEqual([task["material_id"] for task in filtered["tasks"]], [first["material_id"]])
        for target in (0, -1, 1.01, True, None, "0.8", float("nan"), float("inf"), 10**1000):
            with self.subTest(target=target), self.assertRaises(ValueError):
                build_study_plan(self.database, target_accuracy=target)
        for limit in (0, -1, True, 1.0, None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                build_study_plan(self.database, limit=limit)
        for material_id in ("", "desconhecido", "' OR 1=1 --", True, []):
            with self.subTest(material_id=material_id), self.assertRaises(ValueError):
                build_study_plan(self.database, material_id=material_id)

    def test_empty_library_and_sql_errors_are_distinct(self):
        self.assertEqual(build_study_plan(self.database)["tasks"], [])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE study_sessions")
        with self.assertRaises(sqlite3.OperationalError):
            build_study_plan(self.database)


if __name__ == "__main__":
    unittest.main()
