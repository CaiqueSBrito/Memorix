"""Regressões da biblioteca e revisão humana com SQLite e acervo reais."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.materials import MaterialStore


class MaterialStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.corpus.ingest_text(
            "O núcleo contém DNA.", source="biologia", title="Biologia"
        )
        self.store = MaterialStore(self.database)
        self.addCleanup(self.store.close)

    def draft(self, title="Estudo da célula"):
        return validate_material(
            {
                "title": title,
                "items": [{
                    "front": "O que o núcleo contém?",
                    "back": "DNA.",
                    "citations": [{
                        "chunk_id": self.corpus.search("núcleo")[0].chunk_id,
                        "quote": "O núcleo contém DNA.",
                    }],
                }],
            },
            GenerationRequest("flashcards", "Célula", count=1, difficulty="intermediaria"),
            self.corpus.search("núcleo"),
        )

    def replace_source(self):
        self.corpus.ingest_text(
            "O núcleo contém DNA. A célula possui membrana.",
            source="biologia",
            title="Biologia",
        )

    def test_persistence_reopened_and_context_manager_closes_connection(self):
        draft = self.draft()
        created = self.store.create(draft)
        self.assertEqual(created["items"], draft["items"])
        self.assertEqual(created["title"], draft["title"])
        with MaterialStore(self.database) as reopened:
            self.assertEqual(reopened.get(created["material_id"]), created)
            summary = reopened.list_materials()[0]
            self.assertEqual(
                summary, {key: value for key, value in created.items() if key != "items"}
            )
        with self.assertRaises(sqlite3.ProgrammingError):
            reopened.list_materials()

    def test_create_can_be_approved_or_rejected_and_decisions_are_final_until_edit(self):
        for decision, status in (("approve", "approved"), ("reject", "rejected")):
            with self.subTest(decision=decision):
                created = self.store.create(self.draft())
                self.assertEqual(created["status"], "requires_review")
                self.assertEqual(created["version"], 1)
                self.assertIsNone(created["reviewed_at"])
                reviewed = self.store.review(
                    created["material_id"], decision, expected_version=created["version"]
                )
                self.assertEqual(reviewed["status"], status)
                self.assertEqual(reviewed["version"], 2)
                self.assertEqual(reviewed["items"], created["items"])
                self.assertEqual(reviewed["created_at"], created["created_at"])
                for field in ("created_at", "updated_at", "reviewed_at"):
                    self.assertEqual(
                        datetime.fromisoformat(reviewed[field]).utcoffset(), timedelta(0)
                    )
                for next_decision in ("approve", "reject"):
                    with self.assertRaises(ValueError):
                        self.store.review(
                            created["material_id"], next_decision,
                            expected_version=reviewed["version"],
                        )
                    self.assertEqual(self.store.get(created["material_id"]), reviewed)

    def test_editing_any_state_requires_a_new_review(self):
        for decision in (None, "approve", "reject"):
            with self.subTest(decision=decision):
                previous = self.store.create(self.draft())
                material_id = previous["material_id"]
                if decision is not None:
                    previous = self.store.review(
                        material_id, decision, expected_version=previous["version"]
                    )
                draft = self.draft("Material revisado")
                draft["items"][0]["front"] = "Qual substância está no núcleo?"
                edited = self.store.update(
                    material_id, draft, expected_version=previous["version"]
                )
                self.assertEqual(edited["status"], "requires_review")
                self.assertIsNone(edited["reviewed_at"])
                self.assertEqual(edited["version"], previous["version"] + 1)
                self.assertEqual(edited["created_at"], previous["created_at"])
                self.assertEqual(edited["title"], draft["title"])
                self.assertEqual(edited["items"], draft["items"])
                approved = self.store.review(
                    material_id, "approve", expected_version=edited["version"]
                )
                self.assertEqual(approved["status"], "approved")
                self.assertEqual(approved["version"], edited["version"] + 1)

    def test_stale_second_store_cannot_overwrite_or_approve_a_newer_version(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        with MaterialStore(self.database) as second:
            stale = second.get(material_id)
            edited = self.store.update(
                material_id, self.draft("Edição mais recente"),
                expected_version=created["version"],
            )
            with self.assertRaises(ValueError):
                second.update(
                    material_id, self.draft("Edição antiga"),
                    expected_version=stale["version"],
                )
            self.assertEqual(second.get(material_id), edited)
            with self.assertRaises(ValueError):
                second.review(material_id, "approve", expected_version=stale["version"])
            self.assertEqual(second.get(material_id), edited)
            approved = second.review(
                material_id, "approve", expected_version=edited["version"]
            )
        self.assertEqual(self.store.get(material_id), approved)

    def test_obsolete_sources_prevent_approval_but_not_rejection(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        self.replace_source()
        obsolete = self.store.get(material_id)
        self.assertFalse(obsolete["sources_current"])
        self.assertEqual(obsolete["status"], "requires_review")
        with self.assertRaises(ValueError):
            self.store.review(material_id, "approve", expected_version=created["version"])
        self.assertEqual(self.store.get(material_id), obsolete)
        rejected = self.store.review(
            material_id, "reject", expected_version=created["version"]
        )
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["version"], created["version"] + 1)
        self.assertFalse(rejected["sources_current"])
        self.assertIsNotNone(rejected["reviewed_at"])
        self.assertEqual(rejected["items"], created["items"])

    def test_approved_material_retains_history_after_source_replacement(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        approved = self.store.review(material_id, "approve", expected_version=1)
        self.assertTrue(approved["sources_current"])
        self.replace_source()
        expected = {**approved, "sources_current": False}
        self.assertEqual(self.store.get(material_id), expected)
        self.assertEqual(
            self.store.list_materials(status="approved"),
            [{key: value for key, value in expected.items() if key != "items"}],
        )
        with MaterialStore(self.database) as reopened:
            self.assertEqual(reopened.get(material_id), expected)

    def test_invalid_inputs_do_not_create_or_replace_material(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        previous = self.store.review(material_id, "approve", expected_version=1)
        empty_title = self.draft()
        empty_title["title"] = " "
        forged_approval = self.draft()
        forged_approval["status"] = "approved"
        extra_metadata = self.draft()
        extra_metadata["material_id"] = material_id
        unknown_reference = self.draft()
        unknown_reference["items"][0]["citations"][0]["chunk_id"] = "inexistente"
        for payload in (None, empty_title, forged_approval, extra_metadata, unknown_reference, previous):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.store.create(payload)
                with self.assertRaises(ValueError):
                    self.store.update(
                        material_id, payload, expected_version=previous["version"]
                    )
                self.assertEqual(self.store.get(material_id), previous)
                self.assertEqual(len(self.store.list_materials()), 1)

    def test_obsolete_draft_is_neither_created_nor_saved_over_existing_material(self):
        stale_draft = self.draft()
        created = self.store.create(stale_draft)
        material_id = created["material_id"]
        self.replace_source()
        previous = self.store.get(material_id)
        with self.assertRaises(ValueError):
            self.store.create(stale_draft)
        stale_edit = deepcopy(stale_draft)
        stale_edit["title"] = "Edição com fonte antiga"
        with self.assertRaises(ValueError):
            self.store.update(material_id, stale_edit, expected_version=created["version"])
        self.assertEqual(self.store.get(material_id), previous)
        self.assertEqual(len(self.store.list_materials()), 1)
        updated = self.store.update(
            material_id, self.draft("Fonte atual"), expected_version=created["version"]
        )
        self.assertTrue(updated["sources_current"])
        self.assertEqual(updated["version"], created["version"] + 1)

    def test_versions_must_be_positive_integers_and_invalid_decisions_do_not_mutate(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        for version in (True, False, 0, -1, 1.0, "1", None, []):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    self.store.update(material_id, self.draft("Outro título"), expected_version=version)
                with self.assertRaises(ValueError):
                    self.store.review(material_id, "approve", expected_version=version)
                self.assertEqual(self.store.get(material_id), created)
        for decision in ("approved", "rejected", "", None, True, []):
            with self.subTest(decision=decision):
                with self.assertRaises(ValueError):
                    self.store.review(material_id, decision, expected_version=1)
                self.assertEqual(self.store.get(material_id), created)

    def test_storage_failure_rolls_back_and_releases_the_transaction(self):
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_material_update AFTER UPDATE ON materials "
                "BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.update(material_id, self.draft("Edição recusada"), expected_version=1)
        self.assertEqual(self.store.get(material_id), created)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.review(material_id, "approve", expected_version=1)
        self.assertEqual(self.store.get(material_id), created)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TRIGGER reject_material_update")
        reviewed = self.store.review(material_id, "approve", expected_version=1)
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["version"], 2)

    def test_listing_filters_limits_and_orders_by_creation_then_identifier(self):
        first = self.store.create(self.draft("Primeiro"))
        second = self.store.create(self.draft("Segundo"))
        third = self.store.create(self.draft("Terceiro"))
        self.store.review(first["material_id"], "approve", expected_version=1)
        self.store.review(second["material_id"], "reject", expected_version=1)
        earlier = first["created_at"]
        later = (datetime.fromisoformat(earlier) + timedelta(seconds=1)).isoformat()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executemany(
                "UPDATE materials SET created_at = ? WHERE material_id = ?",
                [(earlier, first["material_id"]), (earlier, second["material_id"]),
                 (later, third["material_id"])],
            )
        expected_ids = [third["material_id"], *sorted([first["material_id"], second["material_id"]])]
        listed = self.store.list_materials()
        self.assertEqual([row["material_id"] for row in listed], expected_ids)
        self.assertEqual(self.store.list_materials(limit=2), listed[:2])
        for status, record in (("approved", first), ("rejected", second), ("requires_review", third)):
            with self.subTest(status=status):
                filtered = self.store.list_materials(status=status, limit=1)
                self.assertEqual([row["material_id"] for row in filtered], [record["material_id"]])
                self.assertNotIn("items", filtered[0])
                self.assertTrue(filtered[0]["sources_current"])
        self.assertEqual(self.store.list_materials(status="approved", limit=2)[0]["version"], 2)

    def test_invalid_listing_arguments_and_unknown_materials_raise_value_error(self):
        for status in ("unknown", "approve", "", True, []):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.store.list_materials(status=status)
        for limit in (0, -1, True, False, 1.0, "1", None, []):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.store.list_materials(limit=limit)
        for material_id in ("inexistente", "", None, []):
            with self.subTest(material_id=material_id):
                with self.assertRaises(ValueError):
                    self.store.get(material_id)
                with self.assertRaises(ValueError):
                    self.store.update(material_id, self.draft(), expected_version=1)
                with self.assertRaises(ValueError):
                    self.store.review(material_id, "approve", expected_version=1)
        self.assertEqual(self.store.list_materials(), [])

    def test_material_operations_preserve_corpus_documents_chunks_and_search(self):
        def corpus_rows():
            with closing(sqlite3.connect(self.database)) as connection:
                return (
                    connection.execute("SELECT * FROM documents ORDER BY doc_id").fetchall(),
                    connection.execute("SELECT * FROM chunks ORDER BY id").fetchall(),
                )

        before_rows = corpus_rows()
        before_search = self.corpus.search("núcleo")
        created = self.store.create(self.draft())
        material_id = created["material_id"]
        self.store.review(material_id, "approve", expected_version=1)
        self.store.update(material_id, self.draft("Novo título"), expected_version=2)
        self.store.review(material_id, "reject", expected_version=3)
        self.store.get(material_id)
        self.store.list_materials()
        self.assertEqual(corpus_rows(), before_rows)
        self.assertEqual(self.corpus.search("núcleo"), before_search)


if __name__ == "__main__":
    unittest.main()
