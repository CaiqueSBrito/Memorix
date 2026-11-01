"""Pedagogical checks need a verdict; factual claims need a real cited chunk ID."""
import pytest

from backend.src.Memorix.pipeline.service import _validate
from backend.src.Memorix.providers import generation


_SOURCE = {"chunk_id": "15:223", "doc_id": 15, "position": 223,
           "text": "A ligação iônica é atração entre íons opostos e mantém os íons presos numa rede cristalina."}
_ESSAY = {"question": "Explique o mecanismo da ligação iônica e sua consequência estrutural.",
          "rubric": [{"points": 0.5, "criterion": "Mecanismo", "expected_answer": "Íons de cargas opostas se atraem eletrostaticamente."}, {"points": 0.5, "criterion": "Estrutura", "expected_answer": "Os íons formam uma rede cristalina."}],
          "evidence": [{"chunk_id": "15:223"}]}


def test_neutral_essay_checks_need_verdict_not_fabricated_chunk_id(monkeypatch):
    monkeypatch.setattr(generation, "check_item", lambda *args: True)
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "15:223"} for claim in claims])
    metadata = {}
    assert _validate("essay", {"items": [dict(_ESSAY)]}, [_SOURCE], 1, metadata)[0]["question"] == _ESSAY["question"]


def test_invalid_id_never_supports_a_factual_claim(monkeypatch):
    item = {"question": "A ligação iônica mantém íons numa rede cristalina.", "answer": True,
            "explanation": _SOURCE["text"], "evidence": [{"chunk_id": "15:223"}]}
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "37"} for _ in claims])
    with pytest.raises(ValueError, match="suporte"):
        _validate("true_false", {"items": [item]}, [_SOURCE], 1, {})
