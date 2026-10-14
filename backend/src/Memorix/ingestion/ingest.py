"""Persistência atômica de texto canônico e seus trechos."""

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config.config import ConfigIngestao as Config
from ..entities.documents import Chunk, Document
from ..providers.observabilitiy import record_trace
from .canonical import canonicalize, doc_sha256
from .chunking import chunking


@dataclass(frozen=True)
class Resultado:
    doc_id: int
    doc_sha256: str
    status: str


def ingest_document(
    content: str,
    *,
    title: str,
    source_type: str,
    uploaded_by: str,
    source: str | Path,
    doc_id: int | None = None,
    session: Session | None = None,
    trace_id: str | None = None,
    extractor: str | None = None,
) -> Resultado:
    trace_id = trace_id or str(uuid4())
    start = monotonic()
    path = Path(source)
    owns_session = session is None
    try:
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("fonte deve ser um caminho relativo dentro do acervo")
        canonical_text = canonicalize(content)
        sha = doc_sha256(canonical_text)
        chunking_start = monotonic()
        try:
            chunks = chunking(canonical_text)
        except Exception as error:
            record_trace(trace_id, "chunking", status="erro", erro=type(error).__name__,
                         duracao_ms=(monotonic() - chunking_start) * 1000)
            raise
        chunking_duration_ms = (monotonic() - chunking_start) * 1000
        if owns_session:
            from ..providers.database import SessionLocal

            session = SessionLocal()
        assert session is not None
        with session.begin():
            document = session.scalar(select(Document).where(Document.doc_id == doc_id).with_for_update()) if doc_id is not None else None
            if doc_id is not None and document is None:
                raise ValueError("documento não encontrado")
            if document is None:
                document = Document(
                    doc_sha256=sha, title=title, source_type=source_type,
                    uploaded_by=uploaded_by, extra={"fonte": path.as_posix()},
                )
                session.add(document)
                session.flush()
                result = "created"
            elif document.doc_sha256 == sha:
                result = "no_changes"
            else:
                document.doc_sha256 = sha
                document.title = title
                document.source_type = source_type
                document.uploaded_by = uploaded_by
                document.extra = {"fonte": path.as_posix()}
                session.execute(delete(Chunk).where(Chunk.doc_id == document.doc_id))
                result = "replaced"
            if result != "no_changes":
                session.add_all(
                    Chunk(doc_id=document.doc_id, position=t.position, text=t.text,
                          offset_start=t.offset_start, offset_end=t.offset_end)
                    for t in chunks
                )
                session.flush()
            final_result = Resultado(document.doc_id, sha, result)
    except Exception as error:
        record_trace(trace_id, "ingestao", status="erro", erro=type(error).__name__, duracao_ms=(monotonic() - start) * 1000)
        raise
    finally:
        if owns_session and session is not None:
            session.close()

    record_trace(
        trace_id, "ingestao", status="ok", erro=None, duracao_ms=(monotonic() - start) * 1000,
        doc_id=final_result.doc_id, doc_sha256=sha,
        origem={"tipo": source_type, "arquivo": path.name}, tamanho=len(canonical_text),
        extrator=extractor or Config.extractor, resultado=result,
    )
    record_trace(
        trace_id, "chunking", status="ok", erro=None, duracao_ms=chunking_duration_ms,
        doc_id=final_result.doc_id, doc_sha256=sha, estrategia=Config.strategy,
        parametros={"tokenizer": Config.tokenizer, "revision": Config.revision,
                    "max_tokens": Config.max_tokens, "min_tokens": Config.min_tokens, "overlap": Config.overlap},
        chunks=[{"chunk_id": f"{final_result.doc_id}:{t.position}", "offset_start": t.offset_start,
                 "offset_end": t.offset_end, "n_tokens": t.n_tokens} for t in chunks],
    )
    return final_result
