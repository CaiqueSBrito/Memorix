"""Unexpected model fields never carry a private key through public DTOs."""

from test_study_api import auth, client, register


def test_non_mc_options_cannot_expose_private_answer(client, monkeypatch):
    http, _ = client
    from backend.src.Memorix.pipeline.service import StudyPipeline
    def injected_extra(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": "true_false", "trace_id": trace_id,
                "items": [{"question": "Dois mais dois é quatro?", "answer": True,
                           "options": ["SEGREDO", "GABARITO"], "explanation": "soma",
                           "evidence": [{"chunk_id": "1:0", "quote": "2+2=4"}]}],
                "sources": [{"chunk_id": "1:0", "doc_id": 1, "doc_sha256": "a" * 64,
                             "offset_start": 0, "offset_end": 5}]}
    monkeypatch.setattr(StudyPipeline, "generate", injected_extra)
    headers = auth(register(http, "private-fields@example.test"))
    result = http.post("/study/generate", headers=headers,
                       json={"prompt": "adição", "type": "true_false"})
    assert result.status_code == 201, result.text
    assert "SEGREDO" not in result.text and "options" not in result.json()["items"][0]
    again = http.get(f"/study/content/{result.json()['id']}", headers=headers)
    assert again.status_code == 200 and "SEGREDO" not in again.text
