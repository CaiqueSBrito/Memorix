"""Regressões do acervo; executáveis sem dependências de modelos ou GPU."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.src.Memorix.ingestion.corpus import Corpus, chunk_text


class ChunkTextTests(unittest.TestCase):
    def test_overlap_preserves_words_and_stops_at_document_end(self):
        self.assertEqual(
            chunk_text("ação célula núcleo DNA RNA", chunk_size=3, overlap=1),
            ["ação célula núcleo", "núcleo DNA RNA"],
        )
        self.assertEqual(chunk_text("um dois três", chunk_size=3, overlap=2), ["um dois três"])

    def test_invalid_chunk_boundaries_and_empty_document(self):
        for size, overlap in [(0, 0), (3, -1), (3, 3), (3, 4)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                chunk_text("texto", chunk_size=size, overlap=overlap)
        with self.assertRaises(ValueError):
            chunk_text(" \n\t")


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)

    def test_file_persistence_accent_search_and_citation(self):
        path = Path(self.directory.name) / "biologia.txt"
        path.write_text("\ufeffA célula contém um núcleo.", encoding="utf-8")
        document = self.corpus.ingest_file(path, title="Biologia")
        with Corpus(self.database) as reopened:
            hits = reopened.search("celula")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.doc_id, document.doc_id)
        self.assertEqual(hit.title, "Biologia")
        self.assertEqual(hit.source, str(path.resolve()))
        self.assertEqual(hit.text, "A célula contém um núcleo.")
        self.assertEqual(hit.ordinal, 0)
        self.assertEqual(self.corpus.search("núcleo")[0].chunk_id, hit.chunk_id)

    def test_reingestion_is_stable_and_replaces_stale_index_entries(self):
        first = self.corpus.ingest_text("mitocôndria energia", source="bio", title="Original")
        chunk_id = self.corpus.search("energia")[0].chunk_id
        self.corpus.ingest_text("mitocôndria energia", source="bio", title="Original")
        self.assertEqual([h.chunk_id for h in self.corpus.search("energia")], [chunk_id])
        updated = self.corpus.ingest_text("clorofila luz", source="bio", title="Atualizado")
        self.assertEqual(updated.doc_id, first.doc_id)
        self.assertEqual(self.corpus.search("energia"), [])
        hit = self.corpus.search("clorofila")[0]
        self.assertEqual(hit.title, "Atualizado")
        self.assertNotEqual(hit.chunk_id, chunk_id)

    def test_failed_replacement_rolls_back_document_chunks_and_index(self):
        self.corpus.ingest_text("conteúdo original", source="bio", title="Original")
        before = self.corpus.search("original")
        # Simula uma falha de armazenamento durante a inserção do segundo trecho.
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_chunk BEFORE INSERT ON chunks "
                "WHEN new.ordinal = 1 BEGIN SELECT RAISE(ABORT, 'storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.corpus.ingest_text(
                "novo conteúdo rejeitado", source="bio", title="Novo", chunk_size=2, overlap=0
            )
        self.assertEqual(self.corpus.search("original"), before)
        self.assertEqual(self.corpus.search("novo"), [])

    def test_query_is_literal_and_unmatched_queries_return_no_evidence(self):
        self.corpus.ingest_text("célula núcleo", source="bio", title="Biologia")
        for query in ["", "?!()", "astronomia", '" OR 1=1; --', "NOT"]:
            with self.subTest(query=query):
                self.assertEqual(self.corpus.search(query), [])
        self.assertEqual(self.corpus.search('"célula"*')[0].text, "célula núcleo")

    def test_limit_and_document_isolation(self):
        first = self.corpus.ingest_text("célula vegetal", source="vegetal", title="Vegetal")
        second = self.corpus.ingest_text("célula animal", source="animal", title="Animal")
        hits = self.corpus.search("célula")
        self.assertEqual({h.doc_id for h in hits}, {first.doc_id, second.doc_id})
        self.assertEqual(self.corpus.search("célula", limit=1), hits[:1])
        with self.assertRaises(ValueError):
            self.corpus.search("célula", limit=0)

    def test_invalid_replacement_preserves_existing_content(self):
        self.corpus.ingest_text("conteúdo original", source="bio", title="Biologia")
        for text, source, title in [(" ", "bio", "Novo"), ("novo", "", "Novo"), ("novo", "bio", " ")]:
            with self.subTest(text=text, source=source, title=title), self.assertRaises(ValueError):
                self.corpus.ingest_text(text, source=source, title=title)
        self.assertEqual(self.corpus.search("original")[0].title, "Biologia")


if __name__ == "__main__":
    unittest.main()
