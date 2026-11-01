"""Consumer-facing AI contract: real database, local model boundaries substituted only here."""
import hashlib
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


def _document(conn):
    source = "A mitose produz duas células-filhas geneticamente idênticas. Na metáfase, os cromossomos alinham-se no plano equatorial. Na anáfase, as cromátides irmãs se separam."
    sha = hashlib.sha256(source.encode()).hexdigest()
    doc_id = conn.execute(text("insert into documents (doc_sha256,title,source_type,uploaded_by) values (:sha,'Biologia','texto','admin') returning doc_id"), {"sha": sha}).scalar_one()
    chunk_id = conn.execute(text("insert into chunks (doc_id,position,text,offset_start,offset_end) values (:id,0,:body,0,:end) returning chunk_id"), {"id": doc_id, "body": source, "end": len(source)}).scalar_one()
    return doc_id, chunk_id, source


@pytest.fixture
def local_models(monkeypatch):
    from backend.src.Memorix.providers import embedding, reranking, generation

    monkeypatch.setattr(embedding, "embed", lambda texts: [[1.0] + [0.0] * 1023 for _ in texts])
    monkeypatch.setattr(reranking, "score", lambda query, passages: [8.0 for _ in passages])
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [{"supported": True, "chunk_id": sources[0]["chunk_id"]} for _ in claims])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"items": [{"question": "O que ocorre na metáfase?", "options": ["Cromossomos alinham-se no plano equatorial", "Cromátides irmãs se separam", "DNA duplica", "Células morrem"], "answer": "Cromossomos alinham-se no plano equatorial", "explanation": "Cromossomos alinham-se no plano equatorial.", "evidence": [{"chunk_id": local_models.chunk_id, "quote": "Na metáfase, os cromossomos alinham-se no plano equatorial."}]}]})
    return local_models


def test_index_and_generate_with_provenance(conn, monkeypatch, tmp_path, local_models):
    from backend.src.Memorix.pipeline.service import StudyPipeline, index_documents
    from backend.src.Memorix.providers.observabilitiy import read_trace

    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    doc_id, chunk_id, source = _document(conn)
    local_models.chunk_id = chunk_id
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    indexed = index_documents(session, [doc_id], trace_id="test-ai-001")
    assert indexed["indexed"] == 1
    assert conn.execute(text("select embedding_model from chunks where chunk_id=:id"), {"id": chunk_id}).scalar_one().startswith("BAAI/bge-m3")
    assert conn.execute(text("select tsv @@ plainto_tsquery('public.pt_unaccent', 'metafase') from chunks where chunk_id=:id"), {"id": chunk_id}).scalar_one()
    output = StudyPipeline().generate({"prompt": "Faça uma questão de múltipla escolha sobre metáfase", "type": "multiple_choice", "count": 1}, session=session, trace_id="test-ai-001")
    assert output["status"] == "ok"
    assert output["items"][0]["answer"] == "Cromossomos alinham-se no plano equatorial"
    assert output["items"][0]["evidence"] == [{"chunk_id": chunk_id, "quote": "Na metáfase, os cromossomos alinham-se no plano equatorial."}]
    assert output["sources"][0]["doc_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert {"indexacao", "pedagogical_understand", "retrieval", "reranking", "gate", "generation_adapter", "geracao", "validacao", "resposta"} <= {event["etapa"] for event in read_trace("test-ai-001")}
    assert all("duracao_ms" in event and "status" in event for event in read_trace("test-ai-001"))


def test_no_source_refuses_without_generating(conn, monkeypatch, tmp_path, local_models):
    from backend.src.Memorix.pipeline.service import StudyPipeline
    from backend.src.Memorix.providers import generation
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    monkeypatch.setattr(generation, "generate_json", lambda *a, **kw: pytest.fail("generated without source"))
    response = StudyPipeline().generate({"prompt": "Questões sobre astrobiologia", "type": "true_false"}, session=Session(bind=conn), trace_id="test-ai-002")
    assert response["status"] == "not_found" and response["items"] == []
    assert "não encontrei" in response["message"].lower()


def test_rejects_unsubstantiated_claims_and_distractors(conn, monkeypatch, tmp_path, local_models):
    from backend.src.Memorix.pipeline.service import StudyPipeline
    from backend.src.Memorix.providers import generation
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    doc_id, chunk_id, _ = _document(conn)
    local_models.chunk_id = chunk_id
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [{"supported": False, "chunk_id": ""} for _ in claims])
    from backend.src.Memorix.pipeline.service import index_documents
    index_documents(session, [doc_id])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"items": [{"question": "O que ocorre na metáfase?", "options": ["A Lua é feita de queijo", "Na metáfase, os cromossomos alinham-se no plano equatorial", "DNA duplica", "Células morrem"], "answer": "A Lua é feita de queijo", "explanation": "A Lua é feita de queijo", "evidence": [{"chunk_id": chunk_id, "quote": "Na metáfase, os cromossomos alinham-se no plano equatorial."}]}]})
    with pytest.raises(ValueError, match="(fidelidade|suporte|evidência|validação)"):
        StudyPipeline().generate({"prompt": "Questão sobre metáfase", "type": "multiple_choice"}, session=session)


def test_essay_grading_requires_rubric_and_cited_source(tmp_path, monkeypatch):
    from backend.src.Memorix.pipeline.service import StudyPipeline
    from backend.src.Memorix.providers import generation
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    content = {"question": "O que ocorre na metáfase?", "rubric": [{"points": 0.5, "criterion": "Alinhamento", "expected_answer": "Os cromossomos se alinham durante a metáfase."}, {"points": 0.5, "criterion": "Local", "expected_answer": "O alinhamento ocorre no plano equatorial."}], "evidence": [{"chunk_id": "42:0", "quote": "Na metáfase, os cromossomos alinham-se no plano equatorial."}]}
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"criteria": [
        {"index": 1, "points_awarded": 0.5, "evidence_quote": "Os cromossomos se alinham."},
        {"index": 2, "points_awarded": 0, "evidence_quote": ""}],
        "uncertainty": "A resposta não permite verificar todos os detalhes."})
    grade = StudyPipeline().grade_answer(content, "Os cromossomos se alinham.", trace_id="test-grade")
    assert 0 <= grade["score"] <= 1 and grade["sources"] == content["evidence"]
    assert grade["uncertainty"] and grade["trace_id"] == "test-grade"
    with pytest.raises(ValueError):
        StudyPipeline().grade_answer({"question": "Sem fonte", "rubric": "qualquer"}, "resposta")
