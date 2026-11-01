"""Human-approved minor invitation and separate study assessment contracts."""

from sqlalchemy import select

from test_study_api import auth, client, generate, login, register


def test_admin_verified_guardian_invitation_is_single_use_and_minimal(client):
    http, session = client
    admin = login(http, "admin@example.test", "admin-secret-123")
    student = auth(register(http, "adult@example.test"))
    request = {"guardian_verified": True, "minor_email": "minor@example.test"}
    assert http.post("/admin/minor-invitations", headers=student, json=request).status_code == 403
    assert http.post("/admin/minor-invitations", headers=admin,
                     json={**request, "guardian_verified": False}).status_code in (400, 403, 422)
    invite = http.post("/admin/minor-invitations", headers=admin, json=request)
    assert invite.status_code == 201, invite.text
    invitation_token = invite.json()["invitation_token"]
    minor = {"email": "minor@example.test", "password": "minor-secret-123", "adult_confirmed": False}
    assert http.post("/auth/register", json=minor).status_code in (400, 403, 422)
    assert http.post("/auth/register", json={**minor, "email": "other@example.test",
                                              "invitation_token": invitation_token}).status_code in (400, 403, 409, 422)
    created = http.post("/auth/register", json={**minor, "invitation_token": invitation_token})
    assert created.status_code == 201, created.text
    assert created.json()["token"]
    assert http.post("/auth/register", json={**minor, "email": "minor2@example.test",
                                              "invitation_token": invitation_token}).status_code in (400, 403, 409, 422)
    from backend.src.Memorix.entities.study import MinorInvitation, User
    assert session.scalar(select(User).where(User.email == "minor2@example.test")) is None
    user = session.scalar(select(User).where(User.email == "minor@example.test"))
    invitation = session.scalar(select(MinorInvitation).where(MinorInvitation.claimed_by_id == user.id))
    assert user.role == "student" and invitation.verified_by_id and invitation.verified_at
    assert invitation.claimed_at and invitation.token_hash != invitation_token
    assert invitation.minor_email == "minor@example.test"
    assert not hasattr(invitation, "guardian_name") and not hasattr(invitation, "guardian_document")
    assert http.get("/study/history", headers=auth(created.json()["token"])).status_code == 200


def test_flashcard_self_assessment_and_essay_grading_do_not_inflate_objective_accuracy(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.pipeline.service import StudyPipeline
    def generate_kind(self, request, *, session, trace_id=None):
        kind = request["type"]
        item = {"question": "Explique dois mais dois", "evidence": [{"chunk_id": "1:0", "quote": "2 + 2 = 4"}]}
        item["answer" if kind == "flashcards" else "rubric"] = "quatro" if kind == "flashcards" else "soma correta"
        return {"status": "ok", "type": kind, "items": [item],
                "sources": [{"chunk_id": "1:0", "doc_id": 1, "doc_sha256": "a" * 64,
                             "offset_start": 0, "offset_end": 9}], "trace_id": trace_id}
    monkeypatch.setattr(StudyPipeline, "generate", generate_kind)
    headers = auth(register(http, "reflect@example.test"))
    card = generate(http, headers, "flashcards")
    essay = generate(http, headers, "essay")
    assert "answer" not in card["items"][0] and "rubric" not in essay["items"][0]
    card_id, card_item = card["id"], card["items"][0]["id"]
    assert http.post(f"/study/content/{card_id}/items/{card_item}/reveal", headers=headers).status_code == 200
    assert http.post(f"/study/content/{card_id}/answer", headers=headers,
                     json={"item_id": card_item, "answer": "quatro", "request_id": "card-no-rating"}).status_code == 422
    review = http.post(f"/study/content/{card_id}/answer", headers=headers,
                       json={"item_id": card_item, "answer": "quatro", "self_assessment": False,
                             "request_id": "card-rated"})
    assert review.status_code == 201, review.text
    assert review.json()["correct"] is False  # aluno marcou erro, apesar do texto coincidir
    essay_id, essay_item = essay["id"], essay["items"][0]["id"]
    graded = http.post(f"/study/content/{essay_id}/answer", headers=headers,
                       json={"item_id": essay_item, "answer": "quatro", "request_id": "essay-rated"})
    assert graded.status_code == 201 and graded.json()["score"] == 0.8
    accuracy = http.get("/study/accuracy", headers=headers).json()
    assert accuracy["attempts"] == 0 and accuracy["correct"] == 0
    history = http.get("/study/history", headers=headers).json()
    assert len(history) == 2 and {h["type"] for h in history} == {"flashcards", "essay"}
    assert http.get("/study/plan", headers=headers).json()[0]["answer_ids"] == [review.json()["id"]]


def test_first_attempt_and_review_are_distinct_in_history_and_accuracy(client):
    http, session = client
    headers = auth(register(http, "reviews@example.test"))
    generated = generate(http, headers)
    content_id, item_id = generated["id"], generated["items"][0]["id"]
    for value, request_id in (("3", "first-attempt"), ("4", "revised-attempt")):
        response = http.post(f"/study/content/{content_id}/answer", headers=headers,
                             json={"item_id": item_id, "answer": value, "request_id": request_id})
        assert response.status_code == 201, response.text
    history = http.get("/study/history", headers=headers).json()
    assert [entry["is_review"] for entry in history] == [False, True]
    accuracy = http.get("/study/accuracy", headers=headers).json()
    assert accuracy["attempts"] == 2 and accuracy["correct"] == 1
    assert accuracy["first_attempts"] == 1 and accuracy["review_attempts"] == 1
