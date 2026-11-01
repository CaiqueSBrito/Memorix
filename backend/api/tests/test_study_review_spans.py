"""Admin source quarantine prevents new study and retires already generated citations."""

from sqlalchemy import select

from test_study_api import auth, client, login, register


def test_admin_excludes_spans_and_prior_student_content_becomes_unavailable(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.entities.documents import Chunk, Document
    from backend.src.Memorix.pipeline.service import StudyPipeline
    source = Document(doc_sha256="b" * 64, title="Texto para revisão",
                      source_type="texto", uploaded_by="admin", extra={"fonte": "review.txt"})
    session.add(source)
    session.flush()
    chunk = Chunk(doc_id=source.doc_id, position=0, text="Hipótese incorreta do acervo.",
                  offset_start=10, offset_end=39)
    session.add(chunk)
    session.commit()
    def cited(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": request["type"], "trace_id": trace_id,
                "items": [{"question": "Hipótese?",
                           "answer": "sim", "explanation": "Acervo.",
                           **({"options": ["não", "sim"]} if request["type"] == "multiple_choice" else {}),
                           "evidence": [{"chunk_id": chunk.chunk_id, "quote": "Hipótese incorreta"}]}],
                "sources": [{"chunk_id": chunk.chunk_id, "doc_id": source.doc_id,
                             "doc_sha256": source.doc_sha256, "offset_start": 10, "offset_end": 39}]}
    monkeypatch.setattr(StudyPipeline, "generate", cited)
    student = auth(register(http, "review-student@example.test"))
    admin = login(http, "admin@example.test", "admin-secret-123")
    created = http.post("/study/generate", headers=student,
                        json={"prompt": "tema", "type": "multiple_choice"})
    assert created.status_code == 201, created.text
    cid, iid = created.json()["id"], created.json()["items"][0]["id"]
    card = http.post("/study/generate", headers=student,
                     json={"prompt": "tema", "type": "flashcards"})
    assert card.status_code == 201, card.text
    card_id, card_item = card.json()["id"], card.json()["items"][0]["id"]
    reveal_url = f"/study/content/{card_id}/items/{card_item}/reveal"
    assert http.post(reveal_url, headers=student).status_code == 200
    wrong = http.post(f"/study/content/{cid}/answer", headers=student,
                      json={"item_id": iid, "answer": "não", "request_id": "old-answer"})
    assert wrong.status_code == 201
    assert http.get("/study/plan", headers=student).json()
    assert http.get("/study/recommendations", headers=student).json()
    body = {"doc_sha256": source.doc_sha256, "offset_start": 15, "offset_end": 20,
            "reason": "Em revisão pedagógica"}
    assert http.post("/admin/review-spans", headers=student, json=body).status_code == 403
    invalid = http.post("/admin/review-spans", headers=admin, json={**body, "offset_end": 15})
    assert invalid.status_code in (400, 422)
    span = http.post("/admin/review-spans", headers=admin, json=body)
    assert span.status_code == 201, span.text
    span_id = span.json()["id"]
    assert any(row["id"] == span_id for row in http.get("/admin/review-spans", headers=admin).json())
    assert http.get("/admin/review-spans", headers=student).status_code == 403
    material = http.get(f"/study/materials/{source.doc_id}?chunk_id={chunk.chunk_id}", headers=student)
    assert material.status_code == 410 and "revisão" in material.text.lower()
    assert http.get(f"/study/content/{cid}", headers=student).status_code == 410
    assert http.post(f"/study/content/{cid}/answer", headers=student,
                     json={"item_id": iid, "answer": "sim", "request_id": "new-answer"}).status_code == 410
    assert http.post(reveal_url, headers=student).status_code == 410
    assert http.get("/study/plan", headers=student).json() == []
    assert http.get("/study/recommendations", headers=student).json() == []
    assert http.delete(f"/admin/review-spans/{span_id}", headers=student).status_code == 403
    assert http.delete(f"/admin/review-spans/{span_id}", headers=admin).status_code == 204
    assert http.get(f"/study/content/{cid}", headers=student).status_code == 200
    assert http.get("/study/recommendations", headers=student).json()
