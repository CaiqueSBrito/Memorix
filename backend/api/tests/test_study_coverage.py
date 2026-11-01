"""Partial grounded generation must tell the student it is partial, without padding."""

from test_study_api import auth, client, register


def test_partial_generation_message_survives_post_and_get(client, monkeypatch):
    http, _ = client
    from backend.src.Memorix.pipeline.service import StudyPipeline
    def one_item(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": "multiple_choice", "trace_id": trace_id,
                "message": "Encontrei material para 1 de 5 itens; não completei sem fonte.",
                "items": [{"question": "2+2?", "options": ["1", "2", "3", "4"], "answer": "4",
                           "explanation": "Soma", "evidence": [{"chunk_id": "1:0", "quote": "2+2=4"}]}],
                "sources": [{"chunk_id": "1:0", "doc_id": 1, "doc_sha256": "a" * 64,
                             "offset_start": 0, "offset_end": 5}]}
    monkeypatch.setattr(StudyPipeline, "generate", one_item)
    headers = auth(register(http, "partial@example.test"))
    response = http.post("/study/generate", headers=headers,
                         json={"prompt": "adição", "type": "multiple_choice", "count": 5})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert len(payload["items"]) == 1 and "1 de 5" in payload["message"]
    later = http.get(f"/study/content/{payload['id']}", headers=headers)
    assert later.status_code == 200 and later.json()["message"] == payload["message"]
