"""Exercita PDFs reais, sem substituir o extrator por mocks."""

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.src.Memorix.ingestion.corpus import Corpus


def write_pdf(path: Path, pages: list[str | None], *, password: str | None = None) -> None:
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        if text is None:
            continue
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 770 Td ({escaped}) Tj ET".encode("cp1252"))
        page.replace_contents(stream)
    if password is not None:
        writer.encrypt(password)
    writer.write(path)


class PdfIngestionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / "acervo.sqlite3"
        self.corpus = Corpus(self.database)
        self.addCleanup(self.corpus.close)
        self.pdf = self.root / "biologia.PDF"

    def test_chunks_keep_physical_page_numbers_and_never_cross_pages(self):
        write_pdf(self.pdf, ["célula núcleo DNA RNA", None, "fotossíntese clorofila luz"])
        document = self.corpus.ingest_file(self.pdf, title="Biologia", chunk_size=3, overlap=1)
        self.assertEqual(document.chunk_count, 3)
        with Corpus(self.database) as reopened:
            first = reopened.search("célula")[0]
            overlap = reopened.search("RNA")[0]
            last = reopened.search("fotossintese")[0]
        self.assertEqual((first.page, first.ordinal, first.text), (1, 0, "célula núcleo DNA"))
        self.assertEqual((overlap.page, overlap.ordinal, overlap.text), (1, 1, "DNA RNA"))
        self.assertEqual((last.page, last.ordinal, last.text), (3, 2, "fotossíntese clorofila luz"))
        self.assertEqual({first.doc_id, overlap.doc_id, last.doc_id}, {document.doc_id})
        self.assertEqual(last.source, str(self.pdf.resolve()))
        self.assertEqual(last.title, "Biologia")

    def test_reimport_keeps_ids_but_moving_content_changes_page_reference(self):
        write_pdf(self.pdf, ["mitose divisão celular"])
        document = self.corpus.ingest_file(self.pdf)
        original = self.corpus.search("mitose")[0]
        self.corpus.ingest_file(self.pdf)
        self.assertEqual(self.corpus.search("mitose")[0], original)
        write_pdf(self.pdf, [None, "mitose divisão celular"])
        moved = self.corpus.ingest_file(self.pdf)
        hit = self.corpus.search("mitose")[0]
        self.assertEqual(moved.doc_id, document.doc_id)
        self.assertEqual(hit.page, 2)
        self.assertNotEqual(hit.chunk_id, original.chunk_id)
        write_pdf(self.pdf, ["clorofila luz"])
        self.corpus.ingest_file(self.pdf)
        self.assertEqual(self.corpus.search("mitose"), [])
        self.assertEqual(self.corpus.search("clorofila")[0].page, 1)

    def test_invalid_empty_and_encrypted_pdf_preserve_existing_document(self):
        write_pdf(self.pdf, ["conteúdo original"])
        self.corpus.ingest_file(self.pdf, title="Original")
        before = self.corpus.search("original")
        for kind in ("empty", "encrypted", "malformed"):
            with self.subTest(kind=kind):
                if kind == "empty":
                    write_pdf(self.pdf, [None])
                elif kind == "encrypted":
                    write_pdf(self.pdf, ["segredo"], password="senha")
                else:
                    self.pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
                with self.assertRaises(ValueError):
                    self.corpus.ingest_file(self.pdf, title="Não deve substituir")
                self.assertEqual(self.corpus.search("original"), before)
                self.assertEqual(self.corpus.search("segredo"), [])

    def test_invalid_chunk_settings_do_not_replace_existing_pdf(self):
        write_pdf(self.pdf, ["conteúdo original"])
        self.corpus.ingest_file(self.pdf)
        before = self.corpus.search("original")
        with self.assertRaises(ValueError):
            self.corpus.ingest_file(self.pdf, chunk_size=3, overlap=3)
        self.assertEqual(self.corpus.search("original"), before)

    def test_legacy_database_preserves_text_ids_and_accepts_pdf_after_migration(self):
        legacy = self.root / "legacy.sqlite3"
        doc_id = sha256(b"original.txt").hexdigest()
        chunk_id = sha256(f"{doc_id}:0:célula núcleo".encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(legacy)) as connection:
            connection.executescript(
                """
                CREATE TABLE documents (
                    doc_id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL UNIQUE
                );
                CREATE TABLE chunks (
                    id INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE,
                    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(doc_id, ordinal)
                );
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    text, content='chunks', content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            with connection:
                connection.execute(
                    "INSERT INTO documents VALUES (?, 'Original', 'original.txt')", (doc_id,)
                )
                connection.execute(
                    "INSERT INTO chunks VALUES (1, ?, ?, 0, 'célula núcleo')", (chunk_id, doc_id)
                )
                connection.execute(
                    "INSERT INTO chunks_fts(rowid, text) VALUES (1, 'célula núcleo')"
                )
        write_pdf(self.pdf, [None, "clorofila luz"])
        with Corpus(legacy) as migrated:
            original = migrated.search("celula")[0]
            self.assertEqual(original.doc_id, doc_id)
            self.assertEqual(original.chunk_id, chunk_id)
            self.assertIsNone(original.page)
            migrated.ingest_file(self.pdf)
            self.assertEqual(migrated.search("clorofila")[0].page, 2)
            migrated.ingest_text("mitose", source="original.txt", title="Atualizado")
            self.assertEqual(migrated.search("celula"), [])
        with Corpus(legacy) as reopened:
            self.assertEqual(reopened.search("clorofila")[0].page, 2)
            self.assertIsNone(reopened.search("mitose")[0].page)


if __name__ == "__main__":
    unittest.main()
