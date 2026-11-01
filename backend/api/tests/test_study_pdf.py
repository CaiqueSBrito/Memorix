"""Further HTTP contracts: admin PDF upload and insufficient material refusal."""

import pytest

from test_study_api import auth, client, login, register


@pytest.fixture
def http(client):
    return client[0]


def test_only_admin_can_upload_pdf_and_file_stays_local(http, monkeypatch):
    from backend.src.Memorix.ingestion import pdf
    from pathlib import Path
    from types import SimpleNamespace

    student = auth(register(http, "pdf-student@example.test"))
    admin = login(http, "admin@example.test", "admin-secret-123")
    document = b"%PDF-1.4\nsynthetic upload"
    seen = []
    def fake_pdf(path, *, title, uploaded_by, session, trace_id=None):
        path = Path(path)
        seen.append(path)
        assert path.is_file() and path.read_bytes() == document
        return SimpleNamespace(doc_id=99, status="created", doc_sha256="a" * 64)
    monkeypatch.setattr(pdf, "ingest_pdf", fake_pdf)
    request = {"file": ("fixture.pdf", document, "application/pdf")}
    assert http.post("/admin/ingest/pdf", headers=student, files=request,
                     data={"title": "Teste"}).status_code == 403
    try:
        response = http.post("/admin/ingest/pdf", headers=admin, files=request,
                             data={"title": "Teste"})
        assert response.status_code == 201, response.text
        assert response.json()["doc_id"] == 99 and len(seen) == 1 and seen[0].is_file()
    finally:
        for path in seen:
            path.unlink(missing_ok=True)


def test_refusal_or_clarification_never_persists_content(http, monkeypatch):
    from backend.src.Memorix.pipeline.service import StudyPipeline
    headers = auth(register(http, "refusal@example.test"))
    monkeypatch.setattr(StudyPipeline, "generate", lambda self, request, *, session, trace_id=None: {
        "status": "not_found", "type": request.get("type"), "message": "Não está no acervo.",
        "trace_id": trace_id,
    })
    response = http.post("/study/generate", headers=headers, json={"prompt": "conteúdo ausente", "type": "lesson"})
    assert response.status_code in (200, 404, 422)
    assert "Não está no acervo" in response.text
    assert "id" not in response.json()
    monkeypatch.setattr(StudyPipeline, "generate", lambda self, request, *, session, trace_id=None: {
        "status": "clarification", "type": None, "message": "Qual tipo de conteúdo?", "trace_id": trace_id,
    })
    response = http.post("/study/generate", headers=headers, json={"prompt": "estudar"})
    assert response.status_code in (200, 422)
    assert "Qual tipo de conteúdo" in response.text and "id" not in response.json()
    assert http.get("/study/history", headers=headers).json() == []
