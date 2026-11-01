"""Consumer-visible HTTP contracts on a synthetic, rollback-only PostgreSQL database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def client(conn, monkeypatch):
    from backend.api.main import app, get_session
    from backend.src.Memorix.entities.study import User
    from backend.src.Memorix.services.auth import hash_password
    from backend.src.Memorix.pipeline import service as ai_service

    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    admin = User(email="admin@example.test", password_hash=hash_password("admin-secret-123"), role="admin")
    session.add(admin)
    session.commit()

    def session_override():
        yield session

    app.dependency_overrides[get_session] = session_override
    monkeypatch.setattr(ai_service.StudyPipeline, "generate", lambda self, request, *, session, trace_id=None: {
        "status": "ok", "type": request.get("type", "multiple_choice"),
        "items": [{"question": "Quanto é 2 + 2?", "options": ["3", "4"], "answer": "4",
                   "explanation": "A soma é quatro.", "evidence": [{"chunk_id": "1:0", "quote": "2 + 2 = 4"}]}],
        "sources": [{"chunk_id": "1:0", "doc_id": 1, "doc_sha256": "a" * 64,
                     "offset_start": 0, "offset_end": 9}], "trace_id": trace_id,
    })
    monkeypatch.setattr(ai_service.StudyPipeline, "grade_answer", lambda self, content, answer, *, trace_id=None: {
        "score": 0.8, "feedback": "Boa resposta", "sources": content["evidence"],
        "uncertainty": "", "trace_id": trace_id,
    })
    monkeypatch.setattr(ai_service, "index_documents", lambda session, doc_ids=None, trace_id=None: {
        "indexed": 1, "documents": 1, "trace_id": trace_id,
    })
    with TestClient(app) as test_client:
        yield test_client, session
    app.dependency_overrides.clear()
    session.close()


def register(client, email):
    response = client.post("/auth/register", json={
        "email": email, "password": "unique-secret-123", "adult_confirmed": True,
    })
    assert response.status_code == 201, response.text
    return response.json()["token"]


def login(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def generate(client, headers, kind="multiple_choice"):
    response = client.post("/study/generate", headers=headers, json={"prompt": "adição", "type": kind})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_registration_roles_and_session_revocation(client):
    http, session = client
    assert http.get("/health").status_code == 200
    denied = http.post("/auth/register", json={
        "email": "kid@example.test", "password": "unique-secret-123", "adult_confirmed": False,
        "role": "admin",
    })
    assert denied.status_code in (400, 403, 422)
    from backend.src.Memorix.entities.study import User
    assert session.scalar(select(User).where(User.email == "kid@example.test")) is None
    token = register(http, "one@example.test")
    user = session.scalar(select(User).where(User.email == "one@example.test"))
    assert user.role == "student" and "unique-secret-123" not in user.password_hash
    assert http.post("/auth/login", json={"email": "one@example.test", "password": "bad"}).status_code == 401
    assert http.get("/study/history", headers=auth(token)).status_code == 200
    assert http.post("/auth/logout", headers=auth(token)).status_code == 204
    assert http.get("/study/history", headers=auth(token)).status_code == 401


def test_admin_only_ingest_and_index(client, monkeypatch):
    http, session = client
    student = auth(register(http, "student@example.test"))
    admin = login(http, "admin@example.test", "admin-secret-123")
    assert http.post("/admin/ingest/text", headers=student,
                     json={"title": "Aritmética", "text": "Dois mais dois resulta em quatro.", "source": "aritmetica.txt"}).status_code == 403
    assert http.post("/admin/index", headers=student).status_code == 403
    assert http.get("/admin/metrics", headers=student).status_code == 403
    from backend.src.Memorix.entities.documents import Chunk, Document
    from backend.src.Memorix.entities.study import User
    admin_id = session.scalar(select(User.id).where(User.email == "admin@example.test"))
    saved = http.post("/admin/ingest/text", headers=admin,
                      json={"title": "Aritmética", "text": "Dois mais dois resulta em quatro.",
                            "source": "aritmetica.txt"})
    assert saved.status_code == 201, saved.text
    document = session.get(Document, saved.json()["doc_id"])
    assert document.title == "Aritmética" and document.uploaded_by == str(admin_id)
    assert session.scalars(select(Chunk).where(Chunk.doc_id == document.doc_id)).all()
    assert http.post("/admin/index", headers=admin, json={"doc_ids": [document.doc_id]}).json()["indexed"] == 1


def test_generation_hides_private_keys_and_isolates_every_student_route(client):
    http, session = client
    first = auth(register(http, "first@example.test"))
    second = auth(register(http, "second@example.test"))
    result = generate(http, first)
    assert result["items"][0]["question"] == "Quanto é 2 + 2?"
    assert "answer" not in result["items"][0]
    assert "rubric" not in str(result)
    content_id, item_id = result["id"], result["items"][0]["id"]
    assert http.get(f"/study/content/{content_id}", headers=second).status_code == 404
    assert http.post(f"/study/content/{content_id}/answer", headers=second,
                     json={"item_id": item_id, "answer": "4", "request_id": "attempt-other"}).status_code == 404
    assert http.get(f"/study/content/{content_id}", headers=first).status_code == 200
    for path in ("/study/history", "/study/accuracy", "/study/plan", "/study/recommendations"):
        response = http.get(path, headers=second)
        assert response.status_code == 200, response.text
        assert "Quanto é 2 + 2?" not in response.text


def test_answer_idempotency_accuracy_plan_recommendation_and_history(client):
    http, session = client
    first = auth(register(http, "study@example.test"))
    result = generate(http, first)
    content_id, item_id = result["id"], result["items"][0]["id"]
    body = {"item_id": item_id, "answer": "3", "request_id": "retry-one"}
    wrong = http.post(f"/study/content/{content_id}/answer", headers=first, json=body)
    assert wrong.status_code == 201, wrong.text
    assert wrong.json()["correct"] is False
    replay = http.post(f"/study/content/{content_id}/answer", headers=first, json=body)
    assert replay.status_code == 200 and replay.json()["id"] == wrong.json()["id"]
    conflict = http.post(f"/study/content/{content_id}/answer", headers=first,
                         json={**body, "answer": "4"})
    assert conflict.status_code == 409
    accuracy = http.get("/study/accuracy", headers=first).json()
    assert accuracy["attempts"] == 1 and accuracy["correct"] == 0
    history = http.get("/study/history", headers=first).json()
    assert len(history) == 1 and history[0]["item_id"] == item_id
    plan = http.get("/study/plan", headers=first).json()
    assert plan and plan[0]["answer_ids"] == [wrong.json()["id"]]
    assert plan[0]["due_at"] and plan[0]["reason"]
    recommendations = http.get("/study/recommendations", headers=first).json()
    assert recommendations and recommendations[0]["answer_ids"] == [wrong.json()["id"]]
    assert recommendations[0]["doc_id"] == 1 and recommendations[0]["reason"]
    assert recommendations[0]["sources"]
    correct = http.post(f"/study/content/{content_id}/answer", headers=first,
                        json={"item_id": item_id, "answer": "4", "request_id": "retry-two"})
    assert correct.status_code == 201 and correct.json()["correct"] is True
    assert http.get("/study/accuracy", headers=first).json()["attempts"] == 2


def test_essay_rubric_hidden_grade_called_and_invalid_ids_rejected(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.pipeline.service import StudyPipeline
    called = []
    def generate_essay(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": "essay", "items": [{"question": "Explique a soma", "rubric": "conceito de soma",
                "evidence": [{"chunk_id": "1:0", "quote": "2 + 2 = 4"}]}], "sources": [{"chunk_id": "1:0",
                "doc_id": 1, "doc_sha256": "a" * 64, "offset_start": 0, "offset_end": 9}], "trace_id": trace_id}
    def grade(self, content, answer, *, trace_id=None):
        called.append((content["rubric"], answer))
        return {"score": 0.8, "feedback": "Boa resposta", "sources": content["evidence"],
                "uncertainty": "", "trace_id": trace_id}
    monkeypatch.setattr(StudyPipeline, "generate", generate_essay)
    monkeypatch.setattr(StudyPipeline, "grade_answer", grade)
    headers = auth(register(http, "essay@example.test"))
    result = generate(http, headers, "essay")
    assert "rubric" not in str(result)
    cid, iid = result["id"], result["items"][0]["id"]
    assert http.post(f"/study/content/{cid}/answer", headers=headers,
                     json={"item_id": "invalid", "answer": "Soma", "request_id": "invalid-id"}).status_code == 404
    response = http.post(f"/study/content/{cid}/answer", headers=headers,
                         json={"item_id": iid, "answer": "Dois + dois são quatro", "request_id": "essay-answer"})
    assert response.status_code == 201 and response.json()["score"] == 0.8
    assert called == [("conceito de soma", "Dois + dois são quatro")]
    assert "conceito de soma" not in response.text


def test_no_input_or_secrets_leaked_on_errors(client, monkeypatch):
    http, session = client
    headers = auth(register(http, "errors@example.test"))
    from backend.src.Memorix.pipeline.service import StudyPipeline
    def failure(self, request, *, session, trace_id=None):
        raise RuntimeError(f"model crashed on {request['prompt']}")
    monkeypatch.setattr(StudyPipeline, "generate", failure)
    with TestClient(http.app, raise_server_exceptions=False) as safe:
        error = safe.post("/study/generate", headers=headers,
                          json={"prompt": "PRIVATE_STUDENT_INPUT", "type": "lesson"})
    assert error.status_code == 500 and "PRIVATE_STUDENT_INPUT" not in error.text
    validation = http.post("/auth/login", json={"email": "broken", "password": "PRIVATE_PASSWORD"})
    assert validation.status_code in (401, 422)
    assert "PRIVATE_PASSWORD" not in validation.text
