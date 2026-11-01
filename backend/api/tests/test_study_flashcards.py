"""Flashcard back is revealed before, not by, self-assessment."""

from test_study_api import auth, client, generate, register


def test_flashcard_reveal_precedes_rating_and_preserves_student_ownership(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.pipeline.service import StudyPipeline
    def flashcard(self, request, *, session, trace_id=None):
        return {"status": "ok", "type": request["type"],
                "items": [{"question": "Quanto é 2 + 2?",
                           **({"answer": "quatro"} if request["type"] == "flashcards" else
                              {"answer": "4", "options": ["1", "2", "3", "4"]}),
                           "explanation": "Dois pares dão quatro.",
                           "evidence": [{"chunk_id": "1:0", "quote": "2 + 2 = 4"}]}],
                "sources": [{"chunk_id": "1:0", "doc_id": 1, "doc_sha256": "a" * 64,
                             "offset_start": 0, "offset_end": 9}], "trace_id": trace_id}
    monkeypatch.setattr(StudyPipeline, "generate", flashcard)
    learner = auth(register(http, "cards@example.test"))
    other = auth(register(http, "cards-other@example.test"))
    content = generate(http, learner, "flashcards")
    cid, iid = content["id"], content["items"][0]["id"]
    url = f"/study/content/{cid}/items/{iid}/reveal"
    assert "quatro" not in str(content)
    rating_url = f"/study/content/{cid}/answer"
    payload = {"item_id": iid, "answer": "quatro", "self_assessment": True,
               "request_id": "rated-after-reveal"}
    rejected = http.post(rating_url, headers=learner, json=payload)
    assert rejected.status_code == 409, rejected.text
    assert http.get("/study/history", headers=learner).json() == []
    assert http.get(url, headers=learner).status_code == 405
    assert http.post(url, headers=other).status_code == 404
    assert http.post(rating_url, headers=learner, json=payload).status_code == 409
    revealed = http.post(url, headers=learner)
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["answer"] == "quatro" and revealed.json()["sources"]
    assert http.post(url, headers=learner).json() == revealed.json()
    sibling = generate(http, learner, "flashcards")
    sibling_payload = {**payload, "item_id": sibling["items"][0]["id"], "request_id": "not-revealed"}
    assert http.post(f"/study/content/{sibling['id']}/answer", headers=learner,
                     json=sibling_payload).status_code == 409
    assert http.get("/study/history", headers=learner).json() == []
    rating = http.post(rating_url, headers=learner, json=payload)
    assert rating.status_code == 201 and rating.json()["correct"] is True
    assert len(http.get("/study/history", headers=learner).json()) == 1
    replay = http.post(rating_url, headers=learner, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == rating.json()["id"]
    mc = generate(http, learner)
    assert http.post(f"/study/content/{mc['id']}/items/{mc['items'][0]['id']}/reveal",
                    headers=learner).status_code == 404
    # A pre-migration attempt remains replayable, but does not invent a reveal.
    from sqlalchemy import select
    from backend.src.Memorix.entities.study import StudyAnswer, User
    legacy = StudyAnswer(id="legacy-rating", student_id=session.scalar(
        select(User.id).where(User.email == "cards@example.test")),
        content_id=sibling["id"], item_id=sibling_payload["item_id"],
        request_id="legacy-rating", answer="quatro", self_assessment=True, correct=True, score=1.0)
    session.add(legacy)
    session.commit()
    legacy_payload = {**sibling_payload, "request_id": "legacy-rating"}
    legacy_replay = http.post(f"/study/content/{sibling['id']}/answer", headers=learner,
                              json=legacy_payload)
    assert legacy_replay.status_code == 200 and legacy_replay.json()["id"] == legacy.id
    assert http.post(f"/study/content/{sibling['id']}/answer", headers=learner,
                     json={**legacy_payload, "request_id": "fresh-without-reveal"}).status_code == 409
