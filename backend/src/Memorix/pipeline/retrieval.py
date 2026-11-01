"""Exact dense search plus Portuguese FTS, fused by reciprocal rank (k=60)."""
from time import monotonic

from sqlalchemy import text
from ..config.config import ConfigIngestao

from ..providers import embedding
from ..providers.observabilitiy import query_digest, record_trace

_SQL = text("""
WITH eligible AS NOT MATERIALIZED (
 SELECT c.chunk_id, c.embedding, c.embedding_model, c.tsv
 FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
 WHERE NOT EXISTS (
   SELECT 1 FROM rag_excluded_spans excluded
   WHERE excluded.doc_sha256 = d.doc_sha256
     AND c.offset_start < excluded.offset_end AND c.offset_end > excluded.offset_start
 )
), dense AS (
 SELECT chunk_id, 1 - (embedding OPERATOR(extensions.<=>) CAST(:vector AS extensions.vector(1024))) AS cosine,
        row_number() OVER (ORDER BY embedding OPERATOR(extensions.<=>) CAST(:vector AS extensions.vector(1024)), chunk_id) AS rank
 FROM eligible WHERE embedding_model = :model
 ORDER BY embedding OPERATOR(extensions.<=>) CAST(:vector AS extensions.vector(1024)), chunk_id LIMIT :k
), lexical AS (
 SELECT chunk_id, ts_rank_cd(tsv, q.term) AS lexical_score,
        row_number() OVER (ORDER BY ts_rank_cd(tsv, q.term) DESC, chunk_id) AS rank
 FROM eligible, (SELECT to_tsquery('public.pt_unaccent',
   replace(trim(regexp_replace(:query, '[^A-Za-zÀ-ÿ0-9]+', ' ', 'g')), ' ', ' | ')) AS term) q
 WHERE :hybrid AND tsv @@ q.term
 ORDER BY lexical_score DESC, chunk_id LIMIT :k
), fused AS (
 SELECT COALESCE(d.chunk_id, l.chunk_id) AS chunk_id, d.cosine, l.lexical_score,
       COALESCE(1.0 / (60 + d.rank), 0) + COALESCE(1.0 / (60 + l.rank), 0) AS rrf
 FROM dense d FULL OUTER JOIN lexical l ON d.chunk_id = l.chunk_id
)
SELECT c.chunk_id, c.doc_id, c.position, c.text, c.offset_start, c.offset_end,
       d.doc_sha256, d.title, fused.cosine, fused.lexical_score, fused.rrf
FROM fused JOIN chunks c ON c.chunk_id = fused.chunk_id JOIN documents d ON d.doc_id = c.doc_id
ORDER BY fused.rrf DESC, c.chunk_id LIMIT :k
""")


def retrieve(session, query: str, *, mode="hybrid", k=30, trace_id: str):
    started = monotonic()
    try:
        vector = embedding.embed([query])[0]
        record_trace(trace_id, "embedding", status="ok", duracao_ms=(monotonic() - started) * 1000,
                     modelo=embedding.MODEL, revisao=embedding.REVISION,
                     chunking=ConfigIngestao.strategy, fts="pt_unaccent@v1", quantidade_vetores=1)
    except Exception as error:
        record_trace(trace_id, "embedding", status="erro", erro=type(error).__name__,
                     duracao_ms=(monotonic() - started) * 1000, modelo=embedding.MODEL)
        raise
    started = monotonic()
    try:
        rows = [dict(row) for row in session.execute(_SQL, {
            "vector": "[" + ",".join(str(x) for x in vector) + "]", "model": embedding.MODEL_ID,
            "query": query, "hybrid": mode == "hybrid", "k": k,
        }).mappings()]
        record_trace(trace_id, "retrieval", status="ok", duracao_ms=(monotonic() - started) * 1000,
                     consulta_hash=query_digest(query), k=k, filtros={"embedding_model": embedding.MODEL_ID, "excluded_spans": "sha_offset_overlap"},
                     metodo=mode, resultados=[{"chunk_id": r["chunk_id"], "posicao": index + 1,
                                                "rrf": float(r["rrf"]), "cosine": float(r["cosine"]) if r["cosine"] is not None else None,
                                                "lexical": float(r["lexical_score"]) if r["lexical_score"] is not None else None}
                                               for index, r in enumerate(rows)])
        return rows
    except Exception as error:
        record_trace(trace_id, "retrieval", status="erro", erro=type(error).__name__,
                     duracao_ms=(monotonic() - started) * 1000, consulta_hash=query_digest(query), k=k)
        raise
