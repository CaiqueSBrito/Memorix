"""Acervo textual local com recuperação lexical e referências estáveis."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    source: str
    chunk_count: int


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    chunk_id: str
    title: str
    source: str
    ordinal: int
    text: str
    score: float
    page: int | None


def chunk_text(text: str, *, chunk_size: int = 180, overlap: int = 30) -> list[str]:
    """Divide por palavras, sem truncá-las; tamanho e sobreposição em palavras."""
    if chunk_size < 1 or not 0 <= overlap < chunk_size:
        raise ValueError("Use chunk_size > 0 e 0 <= overlap < chunk_size.")
    words = text.split()
    if not words:
        raise ValueError("O documento não contém texto.")
    chunks = []
    for start in range(0, len(words), chunk_size - overlap):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break
    return chunks


class Corpus:
    """Uma conexão por instância; use como context manager para fechá-la."""

    def __init__(self, database: str | Path):
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY,
                    chunk_id TEXT NOT NULL UNIQUE,
                    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    page INTEGER CHECK(page IS NULL OR page > 0),
                    UNIQUE(doc_id, ordinal)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text, content='chunks', content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                );
                CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text)
                    VALUES ('delete', old.id, old.text);
                END;
                """
            )
            # Bancos anteriores ao suporte a PDF não têm metadados de página.
            columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(chunks)")}
            if "page" not in columns:
                self._connection.execute(
                    "ALTER TABLE chunks ADD COLUMN page INTEGER CHECK(page IS NULL OR page > 0)"
                )
        except Exception:
            self._connection.close()
            raise

    def __enter__(self) -> "Corpus":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def ingest_text(
        self,
        text: str,
        *,
        source: str,
        title: str,
        chunk_size: int = 180,
        overlap: int = 30,
    ) -> Document:
        """Substitui atomicamente a mesma fonte; IDs de trechos mudam com o texto."""
        chunks = [(chunk, None) for chunk in chunk_text(text, chunk_size=chunk_size, overlap=overlap)]
        return self._replace_document(chunks, source=source, title=title)

    def _replace_document(
        self, chunks: list[tuple[str, int | None]], *, source: str, title: str
    ) -> Document:
        if not source.strip() or not title.strip():
            raise ValueError("Fonte e título são obrigatórios.")
        doc_id = sha256(source.encode("utf-8")).hexdigest()
        rows = []
        for ordinal, (chunk, page) in enumerate(chunks):
            identity = (
                f"{doc_id}:{ordinal}:{chunk}"
                if page is None
                else f"{doc_id}:{ordinal}:{page}:{chunk}"
            )
            chunk_id = sha256(identity.encode("utf-8")).hexdigest()
            rows.append((chunk_id, doc_id, ordinal, chunk, page))
        with self._connection:
            self._connection.execute(
                "INSERT INTO documents(doc_id, title, source) VALUES (?, ?, ?) "
                "ON CONFLICT(doc_id) DO UPDATE SET title = excluded.title",
                (doc_id, title, source),
            )
            self._connection.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self._connection.executemany(
                "INSERT INTO chunks(chunk_id, doc_id, ordinal, text, page) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return Document(doc_id, title, source, len(chunks))

    def ingest_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
        chunk_size: int = 180,
        overlap: int = 30,
    ) -> Document:
        """Ingere texto UTF-8 ou PDF com texto; caminho absoluto identifica a fonte."""
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() == ".pdf":
            return self._ingest_pdf(path, title=title, chunk_size=chunk_size, overlap=overlap)
        text = path.read_text(encoding="utf-8-sig")
        if "\x00" in text:
            raise ValueError("O arquivo deve conter texto UTF-8, não dados binários.")
        return self.ingest_text(
            text,
            source=str(path),
            title=path.stem if title is None else title,
            chunk_size=chunk_size,
            overlap=overlap,
        )

    def _ingest_pdf(
        self, path: Path, *, title: str | None, chunk_size: int, overlap: int
    ) -> Document:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PyPdfError
        except ModuleNotFoundError as error:
            if error.name != "pypdf":
                raise
            raise ValueError(
                "Para importar PDF, instale pypdf: python3 -m pip install pypdf==6.21.4"
            ) from error

        chunks = []
        try:
            with path.open("rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise ValueError(
                        "PDF protegido por senha não é suportado; forneça uma cópia sem proteção."
                    )
                for number, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        chunks.extend(
                            (chunk, number)
                            for chunk in chunk_text(text, chunk_size=chunk_size, overlap=overlap)
                        )
        except PyPdfError as error:
            raise ValueError("Não foi possível ler o PDF; verifique se o arquivo é válido.") from error
        if not chunks:
            raise ValueError(
                "O PDF não contém texto extraível. "
                "PDFs digitalizados exigem OCR, ainda não suportado."
            )
        return self._replace_document(
            chunks, source=str(path), title=path.stem if title is None else title
        )

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        """Busca qualquer termo literal, ordenando por BM25 (score maior é melhor)."""
        if limit < 1:
            raise ValueError("O limite deve ser maior que zero.")
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return []
        # Não interpretar operadores FTS ou SQL enviados na consulta.
        expression = " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))
        rows = self._connection.execute(
            """
            SELECT d.doc_id, c.chunk_id, d.title, d.source, c.ordinal, c.text, c.page,
                   -bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.doc_id = c.doc_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts), d.doc_id, c.ordinal
            LIMIT ?
            """,
            (expression, limit),
        ).fetchall()
        return [SearchHit(**dict(row)) for row in rows]
