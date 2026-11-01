"""A correct sentence must not launder an unsupported second assertion."""

import hashlib

import pytest

from backend.src.Memorix.pipeline import service
from backend.src.Memorix.providers import generation


def test_lesson_rejects_unsupported_sentence_even_when_paragraph_starts_with_source(monkeypatch, trace_file):
    fact = "Íons de cargas opostas atraem-se e constituem uma rede cristalina."
    unsupported = "A corrente elétrica resulta de elétrons liberados pela eletrólise."
    source = {"chunk_id": "15:223", "doc_id": 15, "position": 223, "text": fact,
              "doc_sha256": hashlib.sha256(fact.encode()).hexdigest(),
              "offset_start": 0, "offset_end": len(fact)}
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: [source])
    monkeypatch.setattr(service.reranking, "score", lambda *args: [8.0])
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "lesson": [{"text": fact + " " + unsupported, "evidence": [{"chunk_id": "15:223"}]}]})

    def local_judge(claims, sources):
        # External model boundary: a paragraph-level verdict can miss an appended assertion.
        return [{"supported": claim.startswith("O item deve") or claim.startswith(fact),
                 "chunk_id": "15:223"} for claim in claims]

    monkeypatch.setattr(generation, "check_claims", local_judge)
    with pytest.raises(ValueError, match="suporte"):
        service.StudyPipeline().generate(
            {"prompt": "Explique a ligação iônica", "topic": "ligação iônica", "type": "lesson"},
            session=None)
