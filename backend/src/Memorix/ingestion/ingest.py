"""Persistência atômica de texto canônico e seus trechos."""

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config.config import ConfigIngestao as Config
from ..entities.documents import Chunk, Document
from ..providers.rastro import registrar
from .canonical import canonicalizar, doc_sha256
from .chunking import chunkar


@dataclass(frozen=True)
class Resultado:
    doc_id: int
    doc_sha256: str
    resultado: str


def ingerir(
    texto: str,
    *,
    title: str,
    source_type: str,
    uploaded_by: str,
    fonte: str | Path,
    doc_id: int | None = None,
    session: Session | None = None,
    trace_id: str | None = None,
    extrator: str | None = None,
) -> Resultado:
    trace_id = trace_id or str(uuid4())
    inicio = monotonic()
    caminho = Path(fonte)
    sessao_propria = session is None
    try:
        if caminho.is_absolute() or ".." in caminho.parts:
            raise ValueError("fonte deve ser um caminho relativo dentro do acervo")
        canonico = canonicalizar(texto)
        sha = doc_sha256(canonico)
        inicio_chunking = monotonic()
        trechos = chunkar(canonico)
        duracao_chunking_ms = (monotonic() - inicio_chunking) * 1000
        if sessao_propria:
            from ..providers.database import SessionLocal

            session = SessionLocal()
        assert session is not None
        with session.begin():
            documento = session.scalar(select(Document).where(Document.doc_id == doc_id).with_for_update()) if doc_id is not None else None
            if doc_id is not None and documento is None:
                raise ValueError("documento não encontrado")
            if documento is None:
                documento = Document(
                    doc_sha256=sha, title=title, source_type=source_type,
                    uploaded_by=uploaded_by, extra={"fonte": caminho.as_posix()},
                )
                session.add(documento)
                session.flush()
                resultado = "criado"
            elif documento.doc_sha256 == sha:
                resultado = "sem_mudanca"
            else:
                documento.doc_sha256 = sha
                documento.title = title
                documento.source_type = source_type
                documento.uploaded_by = uploaded_by
                documento.extra = {"fonte": caminho.as_posix()}
                session.execute(delete(Chunk).where(Chunk.doc_id == documento.doc_id))
                resultado = "reingerido"
            if resultado != "sem_mudanca":
                session.add_all(
                    Chunk(doc_id=documento.doc_id, position=t.position, text=t.text,
                          offset_start=t.offset_start, offset_end=t.offset_end)
                    for t in trechos
                )
                session.flush()
            resultado_final = Resultado(documento.doc_id, sha, resultado)
    except Exception as erro:
        registrar(trace_id, "ingestao", status="erro", erro=type(erro).__name__, duracao_ms=(monotonic() - inicio) * 1000)
        raise
    finally:
        if sessao_propria and session is not None:
            session.close()

    registrar(
        trace_id, "ingestao", status="ok", erro=None, duracao_ms=(monotonic() - inicio) * 1000,
        doc_id=resultado_final.doc_id, doc_sha256=sha,
        origem={"tipo": source_type, "arquivo": caminho.name}, tamanho=len(canonico),
        extrator=extrator or Config.extrator, resultado=resultado,
    )
    registrar(
        trace_id, "chunking", status="ok", erro=None, duracao_ms=duracao_chunking_ms,
        doc_id=resultado_final.doc_id, doc_sha256=sha, estrategia=Config.estrategia,
        parametros={"tokenizer": Config.tokenizer, "revision": Config.revision,
                    "max_tokens": Config.max_tokens, "min_tokens": Config.min_tokens, "overlap": Config.overlap},
        chunks=[{"chunk_id": f"{resultado_final.doc_id}:{t.position}", "offset_start": t.offset_start,
                 "offset_end": t.offset_end, "n_tokens": t.n_tokens} for t in trechos],
    )
    return resultado_final
