"""Quarantine preserves attempts but excludes invalid sources from active study metrics."""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from test_study_api import auth, client, login, register


def test_quarantine_history_accuracy_and_eligibility(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.entities.documents import Chunk, Document
    from backend.src.Memorix.pipeline.service import StudyPipeline

    text = "Fonte problemática para revisão."
    document = Document(doc_sha256=sha256(text.encode()).hexdigest(), title="Apostila",
                        source_type="texto", uploaded_by="admin", extra={"fonte": "apostila.txt"})
    session.add(document)
    session.flush()
    chunk = Chunk(doc_id=document.doc_id, position=0, text=text, offset_start=0, offset_end=len(text))
    session.add(chunk)
    session.commit()

    def cited(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": "multiple_choice", "trace_id": trace_id,
                "items": [{"question": "Enunciado da fonte?", "options": ["sim", "não"],
                           "answer": "sim", "explanation": "A fonte diz.",
                           "evidence": [{"chunk_id": chunk.chunk_id, "quote": text}]}],
                "sources": [{"chunk_id": chunk.chunk_id, "doc_id": document.doc_id,
                             "doc_sha256": document.doc_sha256,
                             "offset_start": 0, "offset_end": len(text)}]}

    monkeypatch.setattr(StudyPipeline, "generate", cited)
    student = auth(register(http, "history-review@example.test"))
    administrator = login(http, "admin@example.test", "admin-secret-123")
    created = http.post("/study/generate", headers=student, json={"prompt": "fonte", "type": "multiple_choice"})
    assert created.status_code == 201, created.text
    content_id, item_id = created.json()["id"], created.json()["items"][0]["id"]
    attempt = http.post(f"/study/content/{content_id}/answer", headers=student,
                        json={"item_id": item_id, "answer": "não", "request_id": "before-review"})
    assert attempt.status_code == 201, attempt.text
    assert http.get("/study/accuracy", headers=student).json()["attempts"] == 1
    posted = http.post("/admin/review-spans", headers=administrator, json={
        "doc_sha256": document.doc_sha256, "offset_start": 2, "offset_end": 7,
        "reason": "Fonte aguardando curadoria"})
    assert posted.status_code == 201, posted.text
    new_content = http.post("/study/generate", headers=student,
                            json={"prompt": "fonte", "type": "multiple_choice"})
    assert new_content.status_code == 422 and "Enunciado da fonte?" not in new_content.text
    history = http.get("/study/history", headers=student)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["id"] == attempt.json()["id"]
    assert history.json()[0]["source_in_review"] is True
    assert "Enunciado da fonte?" not in history.text and "A fonte diz." not in history.text
    metrics = http.get("/study/accuracy", headers=student)
    assert metrics.status_code == 200
    assert metrics.json()["attempts"] == 0
    assert metrics.json()["excluded_attempts"] == 1
    assert http.delete(f"/admin/review-spans/{posted.json()['id']}", headers=administrator).status_code == 204
    restored = http.get("/study/accuracy", headers=student).json()
    assert restored["attempts"] == 1 and restored["excluded_attempts"] == 0
    assert http.get("/study/history", headers=student).json()[0]["source_in_review"] is False


def test_quarantine_rejects_invalid_sha_and_offsets_and_blocks_pdf_download(client):
    http, session = client
    from backend.src.Memorix.entities.documents import Chunk, Document

    path = Path("backend/uploads") / f"{uuid4()}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\nsynthetic archive content")
    try:
        document = Document(doc_sha256="c" * 64, title="PDF sintético", source_type="pdf",
                            uploaded_by="admin", extra={"fonte": path.as_posix()})
        session.add(document)
        session.flush()
        session.add(Chunk(doc_id=document.doc_id, position=0, text="exemplo", offset_start=0, offset_end=7))
        session.commit()
        student = auth(register(http, "pdf-review@example.test"))
        administrator = login(http, "admin@example.test", "admin-secret-123")
        url = f"/study/materials/{document.doc_id}/download"
        assert http.get(url, headers=student).status_code == 200
        body = {"doc_sha256": document.doc_sha256, "offset_start": 1, "offset_end": 3,
                "reason": "Fonte aguardando curadoria"}
        for bad in ({**body, "doc_sha256": "not-a-sha"},
                    {**body, "doc_sha256": "d" * 64},
                    {**body, "offset_start": -1},
                    {**body, "offset_end": 1000},
                    {**body, "reason": " "}):
            response = http.post("/admin/review-spans", headers=administrator, json=bad)
            assert response.status_code in (400, 404, 422), response.text
        posted = http.post("/admin/review-spans", headers=administrator, json=body)
        assert posted.status_code == 201, posted.text
        blocked = http.get(url, headers=student)
        assert blocked.status_code == 410 and "revisão" in blocked.text.lower()
        assert http.delete(f"/admin/review-spans/{posted.json()['id']}", headers=administrator).status_code == 204
        assert http.get(url, headers=student).status_code == 200
    finally:
        path.unlink(missing_ok=True)
