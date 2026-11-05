"""Regressões de rascunhos persistíveis contra Corpus e SQLite reais."""

from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.contracts.generation import CONTENT_TYPES, GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.storage.material_validation import references_current, validate_draft


class DraftValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.corpus.ingest_text(
            "A célula contém um núcleo. O núcleo contém DNA. Ação e memória: 日本語.",
            source="/acervo/biologia-ação.txt",
            title="Biologia — célula e memória 日本語",
        )
        self.hit = self.corpus.search("núcleo")[0]
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)

    def draft(self, kind="flashcards"):
        if kind == "flashcards":
            item = {"front": "O que o núcleo contém?", "back": "DNA."}
        elif kind == "multipla_escolha":
            item = {
                "question": "O que o núcleo contém?",
                "options": ["DNA", "Clorofila", "Parede celular", "Amido"],
                "answer_index": 0,
                "explanation": "O núcleo contém DNA.",
            }
        elif kind == "verdadeiro_falso":
            item = {
                "question": "O núcleo contém DNA.",
                "answer": True,
                "explanation": "O trecho registra DNA no núcleo.",
            }
        else:
            item = {"heading": "Núcleo", "content": "O núcleo contém DNA."}
        item["citations"] = [{"chunk_id": self.hit.chunk_id, "quote": "O núcleo contém DNA."}]
        return validate_material(
            {"title": "Revisão da célula 日本語", "items": [item]},
            GenerationRequest(kind, "Célula e ação 日本語", count=1, difficulty="intermediaria"),
            [self.hit],
        )

    def assert_invalid(self, payload):
        before = deepcopy(payload)
        with self.assertRaises(ValueError):
            validate_draft(payload, self.connection)
        self.assertFalse(references_current(payload, self.connection))
        self.assertEqual(payload, before)

    def test_generated_envelopes_of_every_kind_remain_valid_without_mutation(self):
        for kind in CONTENT_TYPES:
            with self.subTest(kind=kind):
                payload = self.draft(kind)
                before = deepcopy(payload)
                validate_draft(payload, self.connection)
                self.assertEqual(payload, before)
                self.assertTrue(references_current(payload, self.connection))

    def test_unicode_and_quote_whitespace_are_preserved_or_normalized_only_as_allowed(self):
        payload = self.draft()
        payload["items"][0]["citations"][0]["quote"] = " \n Ação\t e  memória: 日本語. \n"
        before = deepcopy(payload)
        result = validate_draft(payload, self.connection)
        self.assertEqual(result["items"][0]["citations"][0]["quote"], "Ação e memória: 日本語.")
        self.assertEqual(payload, before)

    def test_reingestion_removes_old_reference(self):
        payload = self.draft()
        self.corpus.ingest_text(
            "A mitocôndria participa da produção de energia.",
            source=self.hit.source,
            title=self.hit.title,
        )
        self.assert_invalid(payload)

    def test_title_change_invalidates_metadata_even_with_same_chunk(self):
        payload = self.draft()
        self.corpus.ingest_text(self.hit.text, source=self.hit.source, title="Título atualizado")
        self.assertEqual(self.corpus.search("núcleo")[0].chunk_id, self.hit.chunk_id)
        self.assert_invalid(payload)

    def test_missing_document_does_not_validate_orphan_chunk(self):
        payload = self.draft()
        with self.connection:
            self.connection.execute("DELETE FROM documents WHERE doc_id = ?", (self.hit.doc_id,))
        self.assert_invalid(payload)

    def test_forged_metadata_and_false_quotes_are_rejected(self):
        changes = [
            ("doc_id", "documento-forjado"),
            ("chunk_id", "trecho-forjado"),
            ("chunk_id", "' OR 1=1 --"),
            ("title", "Título forjado"),
            ("source", "/acervo/fonte-forjada.txt"),
            ("page", 3),
            ("quote", "O núcleo contém clorofila."),
            ("quote", "O nucleo contem DNA."),
            ("quote", "o núcleo contém DNA."),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                payload = self.draft()
                payload["items"][0]["citations"][0][field] = value
                self.assert_invalid(payload)

    def test_multiple_documents_require_their_own_source_metadata(self):
        self.corpus.ingest_text(
            "A mitocôndria participa da produção de energia.",
            source="/acervo/energia.txt",
            title="Energia",
        )
        energy_hit = self.corpus.search("mitocôndria")[0]
        payload = self.draft()
        energy = validate_material(
            {
                "title": "Energia",
                "items": [{
                    "front": "Quem participa da produção de energia?",
                    "back": "A mitocôndria.",
                    "citations": [{"chunk_id": energy_hit.chunk_id, "quote": energy_hit.text}],
                }],
            },
            GenerationRequest("flashcards", "Energia", count=1),
            [energy_hit],
        )
        payload["items"].extend(energy["items"])
        payload["items"][1]["citations"][0]["source"] = self.hit.source
        self.assert_invalid(payload)

    def test_real_page_is_accepted_but_boolean_or_other_forged_pages_are_not(self):
        with self.connection:
            self.connection.execute("UPDATE chunks SET page = 1 WHERE chunk_id = ?", (self.hit.chunk_id,))
        payload = self.draft()
        payload["items"][0]["citations"][0]["page"] = 1
        self.assertEqual(validate_draft(payload, self.connection), payload)
        for page in (True, False, None, 0, -1, 1.0, "1", [], {}, 2):
            with self.subTest(page=page):
                forged = deepcopy(payload)
                forged["items"][0]["citations"][0]["page"] = page
                self.assert_invalid(forged)

    def test_citation_requires_exact_fields_and_nonempty_strings(self):
        for field in ("doc_id", "chunk_id", "quote", "title", "source", "page"):
            with self.subTest(missing=field):
                payload = self.draft()
                del payload["items"][0]["citations"][0][field]
                self.assert_invalid(payload)
        for field in ("doc_id", "chunk_id", "quote", "title", "source"):
            for value in (None, "", " \n\t", 1, True, [], {}):
                with self.subTest(field=field, value=value):
                    payload = self.draft()
                    payload["items"][0]["citations"][0][field] = value
                    self.assert_invalid(payload)
        payload = self.draft()
        payload["items"][0]["citations"][0]["approved"] = True
        self.assert_invalid(payload)
        for citations in (None, [], {}, "referência", [None], [[]], ["referência"]):
            with self.subTest(citations=citations):
                payload = self.draft()
                payload["items"][0]["citations"] = citations
                self.assert_invalid(payload)

    def test_envelope_requires_exact_fields_and_review_status(self):
        for field in self.draft():
            with self.subTest(missing=field):
                payload = self.draft()
                del payload[field]
                self.assert_invalid(payload)
        for field, value in (("version", 1), ("approved", True), ("material_id", "id")):
            payload = self.draft()
            payload[field] = value
            self.assert_invalid(payload)
        for status in ("approved", "rejected", None, True, [], {}):
            with self.subTest(status=status):
                payload = self.draft()
                payload["status"] = status
                self.assert_invalid(payload)
        for payload in (None, [], "material", 42, True):
            self.assert_invalid(payload)

    def test_invalid_request_fields_and_item_counts_are_rejected(self):
        cases = {
            "kind": [None, [], {}, True, "desconhecido"],
            "topic": [None, [], {}, True, "", " \n"],
            "difficulty": [None, [], {}, True, "difícil"],
            "title": [None, [], {}, True, "", " \n"],
            "items": [None, {}, "itens", (), [], [None]],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = self.draft()
                    payload[field] = value
                    self.assert_invalid(payload)
        payload = self.draft()
        payload["items"] *= 20
        self.assertEqual(len(validate_draft(payload, self.connection)["items"]), 20)
        payload["items"].append(deepcopy(payload["items"][0]))
        self.assert_invalid(payload)

    def test_item_content_is_validated_instead_of_only_checking_references(self):
        changes = {
            "flashcards": [("front", ""), ("back", 1), ("extra", "não permitido")],
            "multipla_escolha": [
                ("options", ["A", "A", "B", "C"]),
                ("options", ["A", "B"]),
                ("answer_index", True),
                ("answer_index", 4),
                ("explanation", None),
            ],
            "verdadeiro_falso": [("answer", 1), ("question", []), ("explanation", " ")],
            "aula": [("heading", None), ("content", {})],
        }
        for kind, fields in changes.items():
            for field, value in fields:
                with self.subTest(kind=kind, field=field):
                    payload = self.draft(kind)
                    payload["items"][0][field] = value
                    self.assert_invalid(payload)
        payload = self.draft()
        del payload["items"][0]["back"]
        self.assert_invalid(payload)

    def test_validation_errors_do_not_echo_student_content(self):
        payload = self.draft()
        sensitive = "RESPOSTA PRIVADA DO ALUNO"
        payload["items"][0]["citations"][0]["quote"] = sensitive
        with self.assertRaises(ValueError) as raised:
            validate_draft(payload, self.connection)
        self.assertNotIn(sensitive, str(raised.exception))

    def test_storage_errors_propagate_instead_of_reporting_stale_references(self):
        payload = self.draft()
        with closing(sqlite3.connect(":memory:")) as missing_schema:
            missing_schema.row_factory = sqlite3.Row
            with self.assertRaises(sqlite3.OperationalError):
                validate_draft(payload, missing_schema)
            with self.assertRaises(sqlite3.OperationalError):
                references_current(payload, missing_schema)


if __name__ == "__main__":
    unittest.main()
