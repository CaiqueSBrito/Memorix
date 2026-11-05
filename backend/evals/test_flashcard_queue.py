"""Fila de revisão com acervo, aprovação, sessões e agendamento SQLite reais."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.flashcard_sessions import FlashcardStore
from backend.src.Memorix.storage.materials import MaterialStore
from backend.src.Memorix.study.flashcard_queue import cards_from_connection, flashcard_queue


class FlashcardQueueTests(unittest.TestCase):
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
        self.sessions = FlashcardStore(self.database)
        self.addCleanup(self.sessions.close)
        self.now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

    def draft(self, *, focus=(0,), kind="flashcards", title="Revisão da célula"):
        items = []
        for index in focus:
            hit = self.hits[index]
            if kind == "flashcards":
                item = {"front": f"Qual é o conceito {index}?", "back": hit.text}
            elif kind == "verdadeiro_falso":
                item = {"question": hit.text, "answer": True, "explanation": hit.text}
            else:
                item = {"heading": "Conceito", "content": hit.text}
            item["citations"] = [{"chunk_id": hit.chunk_id, "quote": hit.text}]
            items.append(item)
        return validate_material(
            {"title": title, "items": items},
            GenerationRequest(kind, "Célula", count=len(items), difficulty="intermediaria"),
            self.hits,
        )

    def material(self, *, status="approved", **kwargs):
        created = self.materials.create(self.draft(**kwargs))
        if status == "requires_review":
            return created
        return self.materials.review(
            created["material_id"], "approve" if status == "approved" else "reject",
            expected_version=created["version"],
        )

    def queue(self, **kwargs):
        kwargs.setdefault("now", self.now)
        return flashcard_queue(self.database, **kwargs)

    def review(self, material, *, rating="good", now=None):
        instant = self.now if now is None else now
        session = self.sessions.start(
            material["material_id"], expected_version=material["version"], limit=1, now=instant
        )
        item = session["card"]["item_index"]
        self.sessions.reveal(session["session_id"], expected_item=item)
        return self.sessions.rate(
            session["session_id"], rating, expected_item=item, now=instant
        )

    def test_new_cards_have_only_front_and_public_metadata(self):
        material = self.material(focus=(0, 1))
        result = self.queue()
        self.assertEqual(
            [(card["material_id"], card["material_version"], card["item_index"]) for card in result["cards"]],
            [(material["material_id"], material["version"], 0), (material["material_id"], material["version"], 1)],
        )
        for card in result["cards"]:
            self.assertEqual(set(card), {
                "material_id", "material_version", "item_index", "title", "topic",
                "difficulty", "front", "box", "due_at", "state_version",
            })
            self.assertEqual((card["box"], card["due_at"], card["state_version"]), (0, None, 0))

    def test_scheduled_review_reappears_exactly_at_due_in_any_timezone(self):
        material = self.material()
        completed = self.review(material)
        review = completed["reviews"][0]
        due = datetime.fromisoformat(review["due_at"])
        self.assertGreater(due, self.now)
        self.assertEqual(self.queue()["cards"], [])
        self.assertEqual(self.queue(now=due - timedelta(microseconds=1))["cards"], [])
        offset_due = due.astimezone(timezone(timedelta(hours=-3)))
        result = self.queue(now=offset_due)
        self.assertEqual(result["as_of"], due.isoformat())
        self.assertEqual(len(result["cards"]), 1)
        card = result["cards"][0]
        self.assertEqual(card["due_at"], review["due_at"])
        self.assertEqual(card["box"], review["box"])
        self.assertEqual(card["state_version"], 1)

    def test_due_cards_precede_new_cards_and_sort_by_instant_then_identity(self):
        later = self.material()
        earlier = self.material()
        tied = self.material()
        self.review(later, now=self.now + timedelta(hours=1))
        self.review(earlier)
        self.review(tied)
        new = self.material(focus=(0, 1))
        due = self.now + timedelta(days=2)
        cards = self.queue(now=due)["cards"]
        tied_ids = sorted([earlier["material_id"], tied["material_id"]])
        self.assertEqual(
            [card["material_id"] for card in cards],
            tied_ids + [later["material_id"], new["material_id"], new["material_id"]],
        )
        self.assertEqual([card["item_index"] for card in cards[-2:]], [0, 1])
        self.assertEqual(self.queue(limit=2, now=due)["cards"], cards[:2])

    def test_only_approved_flashcards_with_current_sources_consume_limit(self):
        self.material(status="requires_review")
        self.material(status="rejected")
        self.material(kind="verdadeiro_falso")
        self.material(kind="aula")
        stale = self.material(focus=(1,))
        mixed = self.material(focus=(0, 1))
        self.corpus.ingest_text(
            "O núcleo contém DNA. A mitocôndria sintetiza ATP.",
            source="biologia", title="Biologia", chunk_size=4, overlap=0,
        )
        valid = self.material(focus=(0,))
        cards = self.queue(limit=1)["cards"]
        self.assertEqual([card["material_id"] for card in cards], [valid["material_id"]])
        for material in (stale, mixed):
            self.assertEqual(self.queue(material_id=material["material_id"])["cards"], [])

    def test_source_text_or_title_changes_remove_previously_approved_deck(self):
        for change in ("text", "title"):
            with self.subTest(change=change):
                self.corpus.ingest_text(
                    self.text, source="biologia", title="Biologia", chunk_size=4, overlap=0
                )
                material = self.material()
                self.assertEqual(
                    [card["material_id"] for card in self.queue(material_id=material["material_id"])["cards"]],
                    [material["material_id"]],
                )
                self.corpus.ingest_text(
                    self.text.replace("DNA", "RNA") if change == "text" else self.text,
                    source="biologia", title="Renomeado" if change == "title" else "Biologia",
                    chunk_size=4, overlap=0,
                )
                self.assertEqual(self.queue(material_id=material["material_id"])["cards"], [])

    def test_material_filter_never_falls_back_and_known_ineligible_is_empty(self):
        first = self.material(focus=(0, 1))
        self.material()
        cards = self.queue(material_id=first["material_id"], limit=1)["cards"]
        self.assertEqual([(card["material_id"], card["item_index"]) for card in cards], [(first["material_id"], 0)])
        for kwargs in ({"status": "requires_review"}, {"status": "rejected"}, {"kind": "aula"}):
            material = self.material(**kwargs)
            self.assertEqual(self.queue(material_id=material["material_id"])["cards"], [])
        for invalid in ("", " ", 1, True, "unknown"):
            with self.subTest(material_id=invalid), self.assertRaises(ValueError):
                self.queue(material_id=invalid)
        for invalid in (0, -1, True, 1.5, "2", None):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                self.queue(limit=invalid)
        with self.assertRaises(ValueError):
            self.queue(now=self.now.replace(tzinfo=None))

    def test_reapproved_new_version_is_new_without_destroying_history(self):
        material = self.material()
        completed = self.review(material)
        edited = self.materials.update(
            material["material_id"], self.draft(title="Versão editada"),
            expected_version=material["version"],
        )
        self.assertEqual(self.queue(material_id=material["material_id"])["cards"], [])
        approved = self.materials.review(
            edited["material_id"], "approve", expected_version=edited["version"]
        )
        card = self.queue(material_id=material["material_id"])["cards"][0]
        self.assertEqual(card["material_version"], approved["version"])
        self.assertEqual((card["box"], card["state_version"], card["due_at"]), (0, 0, None))
        history = self.sessions.get(completed["session_id"])
        self.assertEqual(history["reviews"], completed["reviews"])
        self.assertEqual(history["material_version"], material["version"])
        with closing(sqlite3.connect(self.database)) as connection:
            states = connection.execute(
                "SELECT material_version, state_version FROM flashcard_states WHERE material_id = ?",
                (material["material_id"],),
            ).fetchall()
        self.assertEqual(states, [(material["version"], 1)])

    def test_helper_keeps_caller_transaction_and_all_reads_are_without_mutations(self):
        material = self.material()
        self.review(material)
        self.material()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            before = list(connection.iterdump())
            connection.execute("BEGIN")
            cards_from_connection(connection, now=self.now)
            self.assertTrue(connection.in_transaction)
            self.assertEqual(connection.total_changes, 0)
            connection.rollback()
            self.assertEqual(list(connection.iterdump()), before)

    def test_sql_errors_are_not_treated_as_an_empty_or_stale_queue(self):
        self.material()
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute("DROP TABLE chunks")
        with self.assertRaises(sqlite3.OperationalError):
            self.queue()

    def test_missing_state_schema_is_not_silently_initialized(self):
        self.material()
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute("DROP TABLE flashcard_states")
        with self.assertRaises(sqlite3.OperationalError):
            self.queue()


if __name__ == "__main__":
    unittest.main()
