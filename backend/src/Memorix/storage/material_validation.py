"""Validação estrutural de rascunhos contra referências atuais do acervo local."""

import sqlite3

from ..contracts.generation import GenerationRequest
from ..generation_adapter.material import validate_material
from ..ingestion.corpus import SearchHit


_DRAFT_FIELDS = {"status", "kind", "topic", "difficulty", "title", "items"}
_CITATION_FIELDS = {"doc_id", "chunk_id", "quote", "title", "source", "page"}


def validate_draft(payload: object, connection: sqlite3.Connection) -> dict:
    """Revalida o envelope sem confiar nos metadados recebidos nem alterá-lo.

    A conexão deve usar sqlite3.Row e conter o esquema inicializado pelo Corpus.
    A validação literal das referências não avalia fidelidade semântica.
    """
    if not isinstance(payload, dict) or set(payload) != _DRAFT_FIELDS:
        raise ValueError("Material: envelope com campos obrigatórios e sem campos extras esperado.")
    if payload["status"] != "requires_review":
        raise ValueError("Material: status requires_review obrigatório.")
    items = payload["items"]
    if not isinstance(items, list):
        raise ValueError("Material: lista de itens esperada.")
    request = GenerationRequest(
        kind=payload["kind"],
        topic=payload["topic"],
        count=len(items),
        difficulty=payload["difficulty"],
    )
    hits_by_id = {}
    raw_items = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Material: objeto de item esperado.")
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise ValueError("Material: lista não vazia de citações esperada.")
        raw_citations = []
        for citation in citations:
            if not isinstance(citation, dict) or set(citation) != _CITATION_FIELDS:
                raise ValueError("Citação: campos obrigatórios e sem campos extras esperados.")
            for field in ("doc_id", "chunk_id", "quote", "title", "source"):
                if not isinstance(citation[field], str) or not citation[field].strip():
                    raise ValueError("Citação: metadados e citação devem ser textos não vazios.")
            page = citation["page"]
            if page is not None and (type(page) is not int or page < 1):
                raise ValueError("Citação: página deve ser nula ou inteiro positivo.")
            chunk_id = citation["chunk_id"]
            if chunk_id not in hits_by_id:
                row = connection.execute(
                    "SELECT c.doc_id, c.chunk_id, d.title, d.source, c.ordinal, c.text, c.page "
                    "FROM chunks AS c JOIN documents AS d ON d.doc_id = c.doc_id "
                    "WHERE c.chunk_id = ?",
                    (chunk_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("Citação: referência não existe no acervo atual.")
                hits_by_id[chunk_id] = SearchHit(**dict(row), score=0)
            hit = hits_by_id[chunk_id]
            if any(citation[field] != getattr(hit, field) for field in (
                "doc_id", "chunk_id", "title", "source", "page"
            )):
                raise ValueError("Citação: metadados não correspondem ao acervo atual.")
            raw_citations.append({"chunk_id": chunk_id, "quote": citation["quote"]})
        raw_items.append({**item, "citations": raw_citations})
    return validate_material(
        {"title": payload["title"], "items": raw_items}, request, list(hits_by_id.values())
    )


def references_current(payload: object, connection: sqlite3.Connection) -> bool:
    """Indica validade atual; falhas de armazenamento não são referências obsoletas."""
    try:
        validate_draft(payload, connection)
    except ValueError:
        return False
    return True
