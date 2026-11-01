"""Natural quantity, explicit exercise subtype and learning objective survive understanding."""
import hashlib

import pytest

from backend.src.Memorix.pipeline import service
from backend.src.Memorix.providers import generation
from backend.src.Memorix.providers.observabilitiy import read_trace


@pytest.fixture
def boundaries(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    passage = "A mitose produz duas células-filhas geneticamente idênticas."
    row = {"chunk_id": "7:0", "doc_id": 7, "position": 0, "text": passage,
           "doc_sha256": hashlib.sha256(passage.encode()).hexdigest(),
           "offset_start": 0, "offset_end": len(passage)}
    topics = []
    monkeypatch.setattr(service, "retrieve", lambda session, query, trace_id: topics.append(query) or [row])
    monkeypatch.setattr(service.reranking, "score", lambda query, passages: [8.0 for _ in passages])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"items": [
        {"question": "A mitose produz duas células-filhas geneticamente idênticas.", "answer": True,
         "explanation": passage, "evidence": [{"chunk_id": "7:0"}]}]})
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "7:0"} for _ in claims])
    monkeypatch.setattr(service, "pin_local_checkpoint", lambda: None)
    monkeypatch.setattr(service.router, "unload", lambda: None)
    monkeypatch.setattr(service.router, "predict", lambda prompt, questions: {
        "answers": {"o que devemos gerar": {"choice": "exercicios", "probabilities": {"exercicios": 0.99}}}})
    return topics


def test_explicit_natural_vf_and_three_items_with_topic_rewrite(boundaries):
    result = service.StudyPipeline().generate(
        {"prompt": "Crie três perguntas de verdadeiro ou falso sobre mitose"},
        session=None, trace_id="intent-natural")
    assert result["status"] == "ok" and result["type"] == "true_false"
    assert result["message"] and "1 de 3" in result["message"]
    assert boundaries == ["mitose"]
    understanding = next(event for event in read_trace("intent-natural") if event["etapa"] == "pedagogical_understand")
    assert understanding["quantidade"] == 3 and understanding["tipo"] == "true_false"
    assert "mitose" not in str(understanding)  # rastro has digest, not the student's text


def test_explicit_count_conflicting_with_natural_three_is_rejected(boundaries):
    with pytest.raises(ValueError, match="quantidade"):
        service.StudyPipeline().generate(
            {"prompt": "Crie três perguntas de verdadeiro ou falso sobre mitose", "type": "true_false", "count": 1},
            session=None)
    assert not boundaries


def test_explicit_difficulty_and_cognitive_level_recorded_without_student_text(boundaries):
    result = service.StudyPipeline().generate(
        {"prompt": "V/F sobre mitose", "topic": "mitose", "type": "true_false",
         "difficulty": "advanced", "cognitive_level": "apply"}, session=None, trace_id="intent-level")
    assert result["status"] == "ok"
    understanding = next(event for event in read_trace("intent-level") if event["etapa"] == "pedagogical_understand")
    assert understanding["dificuldade"] == "advanced" and understanding["nivel_cognitivo"] == "apply"


@pytest.mark.parametrize(("kind", "prompt"), [
    ("multiple_choice", "V/F sobre mitose"),
    ("true_false", "Múltipla escolha sobre mitose"),
])
def test_explicit_type_cannot_silently_override_conflicting_natural_type(boundaries, kind, prompt):
    with pytest.raises(ValueError, match="tipo"):
        service.StudyPipeline().generate({"prompt": prompt, "type": kind}, session=None)
    assert not boundaries


@pytest.mark.parametrize("prompt", [
    "Crie seis perguntas de verdadeiro ou falso sobre mitose",
    "Crie 0 perguntas de verdadeiro ou falso sobre mitose",
])
def test_natural_quantity_outside_supported_limit_is_not_silently_one(boundaries, prompt):
    with pytest.raises(ValueError, match="1 e 5"):
        service.StudyPipeline().generate({"prompt": prompt}, session=None)
    assert not boundaries


def test_two_natural_exercise_subtypes_need_clarification_without_retrieval(boundaries):
    result = service.StudyPipeline().generate(
        {"prompt": "V/F e múltipla escolha sobre mitose"}, session=None)
    assert result["status"] == "clarification" and result["items"] == []
    assert not boundaries


@pytest.mark.parametrize(("choice", "probability", "kind"), [
    ("flashcards", 0.99, "flashcards"), ("aula", 0.99, "lesson"),
    ("flashcards", 0.5, None), ("exercicios", 0.99, None),
])
def test_laya_still_routes_only_supported_confident_types(boundaries, monkeypatch, choice, probability, kind):
    monkeypatch.setattr(service.router, "predict", lambda prompt, questions: {
        "answers": {"o que devemos gerar": {"choice": choice, "probabilities": {choice: probability}}}})
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: [])
    result = service.StudyPipeline().generate({"prompt": "Quero estudar mitose"}, session=None)
    assert result["status"] == ("not_found" if kind else "clarification")
    assert result["type"] == kind
