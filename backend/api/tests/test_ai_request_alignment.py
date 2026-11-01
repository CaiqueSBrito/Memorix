"""Source-backed facts alone cannot replace the student's requested learning objective."""
import hashlib

import pytest

from backend.src.Memorix.pipeline import service
from backend.src.Memorix.providers import generation


def test_off_topic_mc_even_if_factually_sourced_requires_request_alignment(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    source_text = "O Egito antigo foi uma sociedade teocrática. A escravidão ocorreu nas minas e pedreiras estatais."
    source = {"chunk_id": "11:0", "doc_id": 11, "position": 0, "doc_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
              "offset_start": 0, "offset_end": len(source_text), "text": source_text}
    item = {"question": "Qual sociedade se desenvolveu no Egito antigo?", "answer": "Teocrática",
            "options": ["Teocrática", "Feudal", "Capitalista", "Socialista"],
            "explanation": "O Egito antigo foi uma sociedade teocrática.",
            "evidence": [{"chunk_id": "11:0"}]}
    monkeypatch.setattr(service, "retrieve", lambda session, query, trace_id: [source])
    monkeypatch.setattr(service.reranking, "score", lambda query, passages: [8.0])
    monkeypatch.setattr(generation, "generate_json", lambda prompt, schema: {"items": [item]})
    monkeypatch.setattr(generation, "check_item", lambda *args: False)

    with pytest.raises(ValueError, match="suporte"):
        service.StudyPipeline().generate(
            {"prompt": "Crie uma questão sobre as atividades econômicas escravistas no Egito antigo",
             "topic": "escravidão no Egito antigo", "type": "multiple_choice"}, session=None)
