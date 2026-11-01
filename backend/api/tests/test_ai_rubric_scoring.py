"""A supported essay rubric still needs transparent, scoreable criteria."""
import pytest

from backend.src.Memorix.pipeline.service import _validate
from backend.src.Memorix.providers import generation


def test_supported_but_unscoreable_rubric_not_delivered(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A ligação iônica envolve atração eletrostática entre íons de cargas opostas e sustenta uma rede cristalina."}
    item = {"question": "O que caracteriza a ligação iônica?",
            "rubric": "O aluno explica a atração eletrostática entre íons de cargas opostas e menciona a rede cristalina.",
            "evidence": [{"chunk_id": "42:0"}]}
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "42:0"} for _ in claims])
    with pytest.raises(ValueError, match="rubrica.*pontuação"):
        _validate("essay", {"items": [item]}, [source], 1, {})


def test_rubric_with_scored_criteria_is_accepted(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A ligação iônica envolve atração eletrostática entre íons de cargas opostas e sustenta uma rede cristalina."}
    item = {"question": "O que caracteriza a ligação iônica?",
            "rubric": [{"points": 0.5, "criterion": "Mecanismo", "expected_answer": "A ligação iônica envolve atração entre cargas opostas."}, {"points": 0.5, "criterion": "Estrutura", "expected_answer": "Os íons se organizam numa rede cristalina."}],
            "evidence": [{"chunk_id": "42:0"}]}
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "42:0"} for _ in claims])
    assert _validate("essay", {"items": [item]}, [source], 1, {})[0]["rubric"] == item["rubric"]
