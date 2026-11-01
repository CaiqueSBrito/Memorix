"""Candidate passages are auditable but not references of an unrelated generated item."""
import hashlib

from backend.src.Memorix.pipeline import service
from backend.src.Memorix.providers import generation
from backend.src.Memorix.providers.observabilitiy import read_trace


def test_response_sources_include_only_evidence_actually_used(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))

    def row(doc_id, passage):
        return {"chunk_id": f"{doc_id}:0", "doc_id": doc_id, "position": 0, "text": passage,
                "doc_sha256": hashlib.sha256(passage.encode()).hexdigest(),
                "offset_start": 0, "offset_end": len(passage)}

    used = row(1, "A mitose produz duas células-filhas geneticamente idênticas.")
    candidate = row(2, "A fotossíntese transforma energia luminosa em energia química.")
    monkeypatch.setattr(service, "retrieve", lambda session, query, trace_id: [used, candidate])
    monkeypatch.setattr(service.reranking, "score", lambda query, passages: [8.0, 7.0])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"items": [
        {"question": "Quantas células-filhas a mitose produz?", "answer": "Duas células-filhas.",
         "explanation": used["text"], "evidence": [{"chunk_id": used["chunk_id"]}]}]})
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": used["chunk_id"]} for _ in claims])

    output = service.StudyPipeline().generate(
        {"prompt": "Crie um flashcard sobre a mitose", "topic": "mitose", "type": "flashcards"},
        session=None, trace_id="source-selection")
    assert output["status"] == "ok"
    assert [reference["chunk_id"] for reference in output["sources"]] == [used["chunk_id"]]
    adapter = next(event for event in read_trace("source-selection") if event["etapa"] == "generation_adapter")
    assert set(adapter["chunk_ids"]) == {used["chunk_id"], candidate["chunk_id"]}
