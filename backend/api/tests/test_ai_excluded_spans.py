"""A curated canonical span must never enter either retrieval channel."""
import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.src.Memorix.pipeline.retrieval import retrieve
from backend.src.Memorix.providers import embedding


@pytest.mark.banco
def test_excluded_span_filters_dense_and_lexical_after_reindex(conn, monkeypatch):
    from backend.src.Memorix.entities.documents import ExcludedSpan
    from backend.src.Memorix.pipeline.service import index_documents

    monkeypatch.setattr(embedding, "embed", lambda texts: [[1.0] + [0.0] * 1023 for _ in texts])
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    text_with_error = "A fonte diz cianobactérias por quimiossíntese."
    safe_text = "A fotossíntese transforma energia luminosa em energia química."
    bad_sha = hashlib.sha256(text_with_error.encode()).hexdigest()
    good_sha = hashlib.sha256(safe_text.encode()).hexdigest()
    bad_doc = conn.execute(text("INSERT INTO documents(doc_sha256,title,source_type,uploaded_by) VALUES (:sha,'Fonte','texto','admin') RETURNING doc_id"), {"sha": bad_sha}).scalar_one()
    good_doc = conn.execute(text("INSERT INTO documents(doc_sha256,title,source_type,uploaded_by) VALUES (:sha,'Outra','texto','admin') RETURNING doc_id"), {"sha": good_sha}).scalar_one()
    for doc_id, body in ((bad_doc, text_with_error), (good_doc, safe_text)):
        conn.execute(text("INSERT INTO chunks(doc_id,position,text,offset_start,offset_end) VALUES (:doc,0,:body,0,:end)"), {"doc": doc_id, "body": body, "end": len(body)})
    index_documents(session, [bad_doc, good_doc])
    for mode in ("dense", "hybrid"):
        assert any(row["doc_id"] == bad_doc for row in retrieve(session, "cianobactérias quimiossíntese", mode=mode, trace_id="before-curation"))
    span = ExcludedSpan(doc_sha256=bad_sha, offset_start=text_with_error.index("quimiossíntese"),
                        offset_end=text_with_error.index("quimiossíntese") + len("quimiossíntese"), reason="erro factual da fonte")
    session.add(span)
    session.flush()
    assert span.id is not None
    for mode in ("dense", "hybrid"):
        found = retrieve(session, "cianobactérias quimiossíntese", mode=mode, trace_id="after-curation")
        assert not any(row["doc_id"] == bad_doc for row in found)
        assert any(row["doc_id"] == good_doc for row in found)
    conn.execute(text("UPDATE chunks SET embedding=NULL, embedding_model=NULL WHERE doc_id=:doc"), {"doc": bad_doc})
    index_documents(session, [bad_doc])
    assert not any(row["doc_id"] == bad_doc for row in retrieve(session, "quimiossíntese", mode="hybrid", trace_id="after-reindex"))
    assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='rag_excluded_spans'::regclass")).scalar_one()
    with pytest.raises(Exception):
        with conn.begin_nested():
            conn.execute(text("INSERT INTO rag_excluded_spans(doc_sha256,offset_start,offset_end,reason) VALUES (:sha,3,3,'inválido')"), {"sha": bad_sha})
