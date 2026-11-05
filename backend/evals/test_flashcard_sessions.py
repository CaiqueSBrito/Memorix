"""Regressões de prática espaçada com acervo, aprovação e SQLite reais."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import multiprocessing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.flashcard_sessions import FlashcardStore
from backend.src.Memorix.storage.materials import MaterialStore
from backend.src.Memorix.study.flashcard_queue import flashcard_queue


def _rate_in_process(database, session_id, instant, ready, release, results):
    """Cada competidor usa seu próprio processo e sua própria conexão SQLite."""
    try:
        with FlashcardStore(database) as store:
            ready.put(session_id)
            if not release.wait(timeout=15):
                raise RuntimeError("A corrida de revisão não foi liberada.")
            try:
                record = store.rate(session_id, "good", expected_item=0, now=instant)
            except ValueError:
                results.put(("blocked", session_id))
            else:
                results.put(("rated", record))
    except Exception as error:
        results.put(("error", repr(error)))


class FlashcardStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.text = "O núcleo contém DNA. A membrana delimita a célula."
        self.now = datetime(2026, 5, 10, 12, tzinfo=timezone.utc)
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.corpus.ingest_text(self.text, source="biologia", title="Biologia")
        self.materials = MaterialStore(self.database)
        self.addCleanup(self.materials.close)
        self.sessions = FlashcardStore(self.database)
        self.addCleanup(self.sessions.close)

    def draft(self, *, count=2, title="Estudo da célula", kind="flashcards"):
        if kind == "flashcards":
            items = [
                {"front": "O que o núcleo contém?", "back": "DNA: verso do núcleo."},
                {"front": "O que delimita a célula?", "back": "Membrana: verso da célula."},
            ][:count]
        elif kind == "multipla_escolha":
            items = [{
                "question": "O que o núcleo contém?",
                "options": ["DNA", "Membrana", "Parede", "Cílio"],
                "answer_index": 0,
                "explanation": "O núcleo contém DNA.",
            }]
        else:
            items = [{"heading": "Núcleo", "content": "O núcleo contém DNA."}]
        hits = self.corpus.search("núcleo")
        for item in items:
            item["citations"] = [{"chunk_id": hits[0].chunk_id, "quote": self.text}]
        return validate_material(
            {"title": title, "items": items},
            GenerationRequest(kind, "Célula", count=len(items), difficulty="intermediaria"),
            hits,
        )

    def approve(self, **kwargs):
        created = self.materials.create(self.draft(**kwargs))
        return self.materials.review(
            created["material_id"], "approve", expected_version=created["version"]
        )

    def start(self, material, *, limit=20, now=None):
        return self.sessions.start(
            material["material_id"], expected_version=material["version"], limit=limit,
            now=self.now if now is None else now,
        )

    def queue(self, material, *, now=None):
        return flashcard_queue(
            self.database, material_id=material["material_id"],
            now=self.now if now is None else now,
        )["cards"]

    def finish_one(self, material, *, rating="good", now=None):
        instant = self.now if now is None else now
        started = self.start(material, limit=1, now=instant)
        item = started["card"]["item_index"]
        self.sessions.reveal(started["session_id"], expected_item=item)
        return self.sessions.rate(started["session_id"], rating, expected_item=item, now=instant)

    def summary(self, session_id):
        return next(row for row in self.sessions.list_sessions() if row["session_id"] == session_id)

    def assert_active_blocked(self, record):
        session_id = record["session_id"]
        item = record["card"]["item_index"]
        before = self.summary(session_id)
        with self.assertRaises(ValueError):
            self.sessions.get(session_id)
        with self.assertRaises(ValueError):
            self.sessions.reveal(session_id, expected_item=item)
        with self.assertRaises(ValueError):
            self.sessions.rate(session_id, "good", expected_item=item, now=self.now)
        self.assertEqual(self.summary(session_id), before)

    def test_start_requires_approval_current_version_flashcards_and_current_sources(self):
        draft = self.materials.create(self.draft())
        with self.assertRaises(ValueError):
            self.start(draft)
        approved = self.materials.review(
            draft["material_id"], "approve", expected_version=draft["version"]
        )
        with self.assertRaises(ValueError):
            self.start(draft)
        rejected = self.materials.create(self.draft())
        rejected = self.materials.review(
            rejected["material_id"], "reject", expected_version=rejected["version"]
        )
        with self.assertRaises(ValueError):
            self.start(rejected)
        for kind in ("multipla_escolha", "aula"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.start(self.approve(kind=kind))
        self.corpus.ingest_text(self.text + " Há outras organelas.", source="biologia", title="Biologia")
        with self.assertRaises(ValueError):
            self.start(approved)
        self.assertEqual(self.sessions.list_sessions(), [])

    def test_front_only_reveal_resume_advance_and_completion_do_not_leak_other_cards(self):
        approved = self.approve()
        started = self.start(approved)
        session_id = started["session_id"]
        self.assertEqual(started["card"], {
            "item_index": 0, "front": approved["items"][0]["front"], "revealed": False,
        })
        self.assertEqual(started["reviews"], [])
        self.assertEqual(started["total_cards"], 2)
        self.assertEqual(started["completed_cards"], 0)
        self.assertTrue(started["card_current"])
        self.assertEqual(self.sessions.get(session_id), started)
        before_reveal = deepcopy(started)
        with self.assertRaises(ValueError):
            self.sessions.rate(session_id, "good", expected_item=0, now=self.now)
        self.assertEqual(self.sessions.get(session_id), before_reveal)
        with FlashcardStore(self.database) as reopened:
            revealed = reopened.reveal(session_id, expected_item=0)
            self.assertEqual(revealed["card"], {
                "item_index": 0, "front": approved["items"][0]["front"], "revealed": True,
                "back": approved["items"][0]["back"],
                "citations": approved["items"][0]["citations"],
            })
            self.assertEqual(reopened.reveal(session_id, expected_item=0), revealed)
        with FlashcardStore(self.database) as reopened:
            self.assertEqual(reopened.get(session_id), revealed)
            advanced = reopened.rate(session_id, "good", expected_item=0, now=self.now)
        self.assertEqual(advanced["card"], {
            "item_index": 1, "front": approved["items"][1]["front"], "revealed": False,
        })
        self.assertEqual(advanced["completed_cards"], 1)
        self.assertEqual([review["rating"] for review in advanced["reviews"]], ["good"])
        for action in ("reveal", "rate"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                if action == "reveal":
                    self.sessions.reveal(session_id, expected_item=0)
                else:
                    self.sessions.rate(session_id, "easy", expected_item=0, now=self.now)
        with self.assertRaises(ValueError):
            self.sessions.rate(session_id, "easy", expected_item=1, now=self.now)
        self.assertEqual(self.sessions.get(session_id), advanced)
        self.sessions.reveal(session_id, expected_item=1)
        completed = self.sessions.rate(session_id, "easy", expected_item=1, now=self.now)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["completed_cards"], 2)
        self.assertIsNone(completed["card"])
        self.assertIsNone(completed["card_current"])
        self.assertEqual([review["item_index"] for review in completed["reviews"]], [0, 1])
        self.assertEqual([review["box"] for review in completed["reviews"]], [1, 2])
        self.assertEqual(self.sessions.get(session_id), completed)
        with self.assertRaises(ValueError):
            self.sessions.reveal(session_id, expected_item=1)
        with self.assertRaises(ValueError):
            self.sessions.rate(session_id, "again", expected_item=1, now=self.now)
        with FlashcardStore(self.database) as reopened:
            self.assertEqual(reopened.get(session_id), completed)
        self.assertEqual(self.queue(approved), [])
        for full in (started, revealed, advanced, completed):
            self.assertFalse({"snapshot_json", "selection_json", "items", "answers", "accuracy"} & set(full))
        summary = self.summary(session_id)
        self.assertEqual(summary, {k: v for k, v in completed.items() if k not in ("card", "reviews")})
        self.assertFalse({"card", "reviews", "snapshot", "selection", "back", "citations"} & set(summary))

    def test_scheduled_cards_are_absent_until_due_and_resume_the_same_box(self):
        approved = self.approve(count=1)
        completed = self.finish_one(approved, rating="again")
        due = self.now + timedelta(minutes=10)
        self.assertEqual(completed["reviews"][0]["due_at"], due.isoformat())
        self.assertEqual(self.queue(approved, now=due - timedelta(microseconds=1)), [])
        with self.assertRaises(ValueError):
            self.start(approved, now=due - timedelta(microseconds=1))
        due_cards = self.queue(approved, now=due)
        self.assertEqual(len(due_cards), 1)
        self.assertEqual(due_cards[0]["box"], 0)
        self.assertEqual(due_cards[0]["state_version"], 1)
        second = self.finish_one(approved, rating="easy", now=due)
        self.assertEqual(second["reviews"][0]["box"], 2)
        next_due = due + timedelta(days=3)
        self.assertEqual(second["reviews"][0]["due_at"], next_due.isoformat())
        third = self.finish_one(approved, rating="hard", now=next_due)
        self.assertEqual(third["reviews"][0]["box"], 1)
        self.assertEqual(self.queue(approved, now=next_due + timedelta(days=1))[0]["state_version"], 3)
        self.assertEqual(self.sessions.get(completed["session_id"]), completed)

    def test_two_sessions_freeze_the_same_token_but_only_one_can_review_it(self):
        approved = self.approve(count=1)
        first = self.start(approved)
        second = self.start(approved)
        for record in (first, second):
            self.sessions.reveal(record["session_id"], expected_item=0)
        completed = self.sessions.rate(first["session_id"], "good", expected_item=0, now=self.now)
        self.assert_active_blocked(second)
        self.assertFalse(self.summary(second["session_id"])["card_current"])
        cards = self.queue(approved, now=self.now + timedelta(days=1))
        self.assertEqual([(card["box"], card["state_version"]) for card in cards], [(1, 1)])
        self.assertEqual(self.sessions.get(first["session_id"]), completed)
        self.assertEqual(len(self.sessions.list_sessions(status="completed")), 1)

    def test_two_processes_cannot_overwrite_the_same_state_or_count_two_reviews(self):
        approved = self.approve(count=1)
        sessions = [self.start(approved), self.start(approved)]
        for record in sessions:
            self.sessions.reveal(record["session_id"], expected_item=0)
        context = multiprocessing.get_context("spawn")
        ready, results = context.Queue(), context.Queue()
        release = context.Event()
        processes = [context.Process(
            target=_rate_in_process,
            args=(str(self.database), record["session_id"], self.now, ready, release, results),
        ) for record in sessions]
        try:
            for process in processes:
                process.start()
            self.assertEqual({ready.get(timeout=20), ready.get(timeout=20)}, {
                record["session_id"] for record in sessions
            })
            release.set()
            returned = [results.get(timeout=20), results.get(timeout=20)]
            self.assertEqual(sorted(kind for kind, _ in returned), ["blocked", "rated"])
            completed = next(value for kind, value in returned if kind == "rated")
            self.assertEqual(len(completed["reviews"]), 1)
            self.assertEqual(self.sessions.get(completed["session_id"]), completed)
            self.assertEqual(len(self.sessions.list_sessions(status="completed")), 1)
            cards = self.queue(approved, now=self.now + timedelta(days=1))
            self.assertEqual([(card["box"], card["state_version"]) for card in cards], [(1, 1)])
        finally:
            release.set()
            for process in processes:
                if process.pid is not None:
                    process.join(timeout=20)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            ready.close()
            results.close()
        for process in processes:
            self.assertEqual(process.exitcode, 0)

    def test_rating_persists_when_the_next_frozen_card_has_become_stale(self):
        approved = self.approve()
        self.finish_one(approved)
        other_time = self.now + timedelta(hours=1)
        other = self.start(approved, now=other_time)
        self.assertEqual(other["card"]["item_index"], 1)
        due = self.now + timedelta(days=1)
        current = self.start(approved, now=due)
        self.assertEqual(current["card"]["item_index"], 0)
        self.sessions.reveal(other["session_id"], expected_item=1)
        self.sessions.rate(other["session_id"], "good", expected_item=1, now=due)
        self.sessions.reveal(current["session_id"], expected_item=0)
        advanced = self.sessions.rate(current["session_id"], "good", expected_item=0, now=due)
        self.assertEqual(advanced["status"], "in_progress")
        self.assertEqual(advanced["completed_cards"], 1)
        self.assertFalse(advanced["card_current"])
        self.assertIsNone(advanced["card"])
        self.assertEqual([review["item_index"] for review in advanced["reviews"]], [0])
        self.assertEqual(advanced["reviews"][0]["box"], 2)
        with self.assertRaises(ValueError):
            self.sessions.get(current["session_id"])
        with self.assertRaises(ValueError):
            self.sessions.reveal(current["session_id"], expected_item=1)
        with self.assertRaises(ValueError):
            self.sessions.rate(current["session_id"], "easy", expected_item=1, now=due)
        self.assertEqual(self.summary(current["session_id"])["completed_cards"], 1)
        cards = self.queue(approved, now=due + timedelta(days=3))
        by_item = {card["item_index"]: card for card in cards}
        self.assertEqual((by_item[0]["box"], by_item[0]["state_version"]), (2, 2))
        self.assertEqual((by_item[1]["box"], by_item[1]["state_version"]), (1, 1))

    def test_material_edits_block_active_sessions_and_new_versions_start_unscheduled(self):
        approved = self.approve()
        completed = self.finish_one(approved, rating="easy")
        active = self.start(approved)
        self.sessions.reveal(active["session_id"], expected_item=1)
        revised = self.draft(count=1, title="Material revisado")
        revised["items"][0]["front"] = "Qual substância há no núcleo?"
        revised["items"][0]["back"] = "Novo verso: DNA."
        edited = self.materials.update(
            approved["material_id"], revised, expected_version=approved["version"]
        )
        for material in (edited, None):
            if material is None:
                material = self.materials.review(
                    edited["material_id"], "approve", expected_version=edited["version"]
                )
            self.assert_active_blocked(active)
            self.assertFalse(self.summary(active["session_id"])["material_current"])
            historical = self.sessions.get(completed["session_id"])
            self.assertEqual(historical["title"], approved["title"])
            self.assertEqual(historical["reviews"], completed["reviews"])
            self.assertFalse(historical["material_current"])
        cards = self.queue(material)
        self.assertEqual([(card["box"], card["state_version"], card["due_at"]) for card in cards], [(0, 0, None)])
        fresh = self.start(material)
        self.assertEqual(fresh["card"]["front"], revised["items"][0]["front"])
        self.sessions.reveal(fresh["session_id"], expected_item=0)
        new_result = self.sessions.rate(fresh["session_id"], "good", expected_item=0, now=self.now)
        self.assertEqual(new_result["reviews"][0]["box"], 1)
        self.assertEqual(self.sessions.get(completed["session_id"])["reviews"], completed["reviews"])

    def test_source_text_and_metadata_changes_block_active_but_preserve_completed_history(self):
        for text, title in ((self.text, "Fonte renomeada"), (self.text + " Há organelas.", "Biologia")):
            with self.subTest(text=text, title=title):
                approved = self.approve()
                completed = self.finish_one(approved)
                active = self.start(approved)
                self.sessions.reveal(active["session_id"], expected_item=1)
                self.corpus.ingest_text(text, source="biologia", title=title)
                self.assert_active_blocked(active)
                summary = self.summary(active["session_id"])
                self.assertFalse(summary["sources_current"])
                self.assertTrue(summary["material_current"])
                with FlashcardStore(self.database) as reopened:
                    historical = reopened.get(completed["session_id"])
                    self.assertEqual(historical["reviews"], completed["reviews"])
                    self.assertEqual(historical["title"], approved["title"])
                    self.assertFalse(historical["sources_current"])
                self.assertEqual(self.queue(approved), [])
                with self.assertRaises(ValueError):
                    self.start(approved)

    def test_trigger_failures_roll_back_start_reveal_and_every_write_of_rating(self):
        approved = self.approve(count=1)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_start AFTER INSERT ON flashcard_sessions "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.start(approved)
        self.assertEqual(self.sessions.list_sessions(), [])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_start")
        started = self.start(approved)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_reveal AFTER UPDATE ON flashcard_sessions "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.sessions.reveal(started["session_id"], expected_item=0)
        self.assertEqual(self.sessions.get(started["session_id"]), started)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_reveal")
        revealed = self.sessions.reveal(started["session_id"], expected_item=0)
        original_queue = self.queue(approved)
        for name, target in (("reject_state", "flashcard_states"), ("reject_review", "flashcard_reviews")):
            with self.subTest(target=target):
                with closing(sqlite3.connect(self.database)) as connection:
                    connection.execute(
                        f"CREATE TRIGGER {name} AFTER INSERT ON {target} "
                        "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    self.sessions.rate(started["session_id"], "good", expected_item=0, now=self.now)
                self.assertEqual(self.sessions.get(started["session_id"]), revealed)
                self.assertEqual(self.queue(approved), original_queue)
                with closing(sqlite3.connect(self.database)) as connection:
                    connection.execute(f"DROP TRIGGER {name}")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_advance AFTER UPDATE ON flashcard_sessions "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.sessions.rate(started["session_id"], "good", expected_item=0, now=self.now)
        self.assertEqual(self.sessions.get(started["session_id"]), revealed)
        self.assertEqual(self.queue(approved), original_queue)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_advance")
        completed = self.sessions.rate(started["session_id"], "good", expected_item=0, now=self.now)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(completed["reviews"]), 1)

    def test_invalid_domains_do_not_create_sessions_or_change_the_current_card(self):
        approved = self.approve(count=1)
        for version in (True, False, 0, -1, 2.0, "2", None, []):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.sessions.start(approved["material_id"], expected_version=version, now=self.now)
        for limit in (True, False, 0, -1, 1.0, "1", None, []):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.start(approved, limit=limit)
                with self.assertRaises(ValueError):
                    self.sessions.list_sessions(limit=limit)
        for material_id in ("missing", "", " ", None, [], True):
            with self.subTest(material_id=material_id), self.assertRaises(ValueError):
                self.sessions.start(material_id, expected_version=approved["version"], now=self.now)
        for status in ("approved", "unknown", "", True, [], {}):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.sessions.list_sessions(status=status)
        self.assertEqual(self.sessions.list_sessions(), [])
        started = self.start(approved)
        session_id = started["session_id"]
        for item in (True, False, -1, 1, 0.0, "0", None, [], {}):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    self.sessions.reveal(session_id, expected_item=item)
                with self.assertRaises(ValueError):
                    self.sessions.rate(session_id, "good", expected_item=item, now=self.now)
                self.assertEqual(self.sessions.get(session_id), started)
        for invalid_id in ("missing", "", " ", None, [], True):
            with self.subTest(session_id=invalid_id):
                with self.assertRaises(ValueError):
                    self.sessions.get(invalid_id)
                with self.assertRaises(ValueError):
                    self.sessions.reveal(invalid_id, expected_item=0)
                with self.assertRaises(ValueError):
                    self.sessions.rate(invalid_id, "good", expected_item=0, now=self.now)
        revealed = self.sessions.reveal(session_id, expected_item=0)
        for rating in ("", "GOOD", "correct", True, False, 0, None, [], {}):
            with self.subTest(rating=rating), self.assertRaises(ValueError):
                self.sessions.rate(session_id, rating, expected_item=0, now=self.now)
            self.assertEqual(self.sessions.get(session_id), revealed)
        with FlashcardStore(self.database) as reopened:
            self.assertEqual(reopened.get(session_id), revealed)
        with self.assertRaises(sqlite3.ProgrammingError):
            reopened.list_sessions()

    def test_invalid_or_backdated_times_roll_back_and_aware_offsets_normalize_to_utc(self):
        approved = self.approve(count=1)
        invalid_times = (datetime(2026, 5, 10), "2026-05-10T12:00:00+00:00", True, 1, [])
        for instant in invalid_times:
            with self.subTest(instant=instant), self.assertRaises(ValueError):
                self.start(approved, now=instant)
        self.assertEqual(self.sessions.list_sessions(), [])
        offset = timezone(timedelta(hours=-3))
        started = self.start(approved, now=self.now.astimezone(offset))
        self.assertEqual(started["created_at"], self.now.isoformat())
        revealed = self.sessions.reveal(started["session_id"], expected_item=0)
        for instant in (*invalid_times, self.now - timedelta(microseconds=1), datetime.max.replace(tzinfo=timezone.utc)):
            with self.subTest(instant=instant), self.assertRaises(ValueError):
                self.sessions.rate(started["session_id"], "good", expected_item=0, now=instant)
            self.assertEqual(self.sessions.get(started["session_id"]), revealed)
        completed = self.sessions.rate(
            started["session_id"], "good", expected_item=0, now=self.now.astimezone(offset)
        )
        self.assertEqual(completed["completed_at"], self.now.isoformat())
        self.assertEqual(completed["reviews"][0]["reviewed_at"], self.now.isoformat())
        # Repeating a due card still requires a review time at or after the
        # current session, not merely an instant accepted by the previous one.
        due = self.now + timedelta(days=1)
        next_session = self.start(approved, now=due)
        self.sessions.reveal(next_session["session_id"], expected_item=0)
        next_review = self.sessions.rate(next_session["session_id"], "again", expected_item=0, now=due)
        earlier_session = self.start(approved, now=due + timedelta(minutes=10))
        before = self.sessions.reveal(earlier_session["session_id"], expected_item=0)
        with self.assertRaises(ValueError):
            self.sessions.rate(earlier_session["session_id"], "good", expected_item=0, now=due - timedelta(seconds=1))
        self.assertEqual(self.sessions.get(earlier_session["session_id"]), before)
        self.assertEqual(self.sessions.get(next_session["session_id"]), next_review)

    def test_listing_exposes_only_summaries_with_filter_limit_and_frozen_counts(self):
        approved = self.approve()
        pending = self.start(approved, now=self.now)
        completed = self.finish_one(approved, now=self.now + timedelta(seconds=1))
        listed = self.sessions.list_sessions()
        self.assertEqual([row["session_id"] for row in listed], [completed["session_id"], pending["session_id"]])
        self.assertEqual(self.sessions.list_sessions(limit=1), listed[:1])
        self.assertEqual([row["session_id"] for row in self.sessions.list_sessions(status="completed")], [completed["session_id"]])
        self.assertEqual([row["session_id"] for row in self.sessions.list_sessions(status="in_progress")], [pending["session_id"]])
        for summary in listed:
            self.assertFalse({"card", "reviews", "items", "snapshot_json", "selection_json", "back", "citations"} & set(summary))
        self.assertEqual(self.summary(pending["session_id"])["completed_cards"], 0)
        self.assertFalse(self.summary(pending["session_id"])["card_current"])


if __name__ == "__main__":
    unittest.main()
