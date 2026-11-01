"""A sourced summary is not a lesson about how a process works."""
import hashlib

import pytest

from backend.src.Memorix.pipeline import service
from backend.src.Memorix.providers import generation


def test_sourced_conclusion_does_not_satisfy_how_lesson(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    passage = ("Elétrons de valência participam da ligação. Pela família e período é possível prever o tipo e "
               "a quantidade de ligações que um átomo pode formar.")
    row = {"chunk_id": "15:0", "doc_id": 15, "position": 0, "text": passage,
           "doc_sha256": hashlib.sha256(passage.encode()).hexdigest(), "offset_start": 0, "offset_end": len(passage)}
    monkeypatch.setattr(service, "retrieve", lambda session, query, trace_id: [row])
    monkeypatch.setattr(service.reranking, "score", lambda query, passages: [8.0])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"lesson": [
        {"text": "Conhecendo a família e o período é possível prever o tipo e a quantidade de ligações.",
         "evidence": [{"chunk_id": "15:0"}]}]})
    monkeypatch.setattr(generation, "check_item", lambda *args: False)

    with pytest.raises(ValueError, match="suporte"):
        service.StudyPipeline().generate(
            {"prompt": "Dê uma aula curta sobre como posição na tabela prevê ligações",
             "topic": "tabela periódica e ligações", "type": "lesson"}, session=None)
