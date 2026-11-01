"""Invalid choices must not become learning errors or consume retry IDs."""
import pytest
from sqlalchemy import select

from test_study_api import auth, client, generate, register
from backend.src.Memorix.entities.study import StudyAnswer, User


@pytest.mark.parametrize("invalid_choice", ["7", "  \t"])
def test_invalid_choice_has_no_study_effect_and_does_not_consume_retry_id(client, invalid_choice):
    http, session = client
    headers = auth(register(http, "choices@example.test"))
    content = generate(http, headers)
    paths = ("/study/history", "/study/accuracy", "/study/plan", "/study/recommendations")
    before = {path: http.get(path, headers=headers).json() for path in paths}
    url = f"/study/content/{content['id']}/answer"
    body = {"item_id": content["items"][0]["id"], "answer": invalid_choice, "request_id": "choice-retry"}
    rejected = http.post(url, headers=headers, json=body)
    assert rejected.status_code == 422, rejected.text
    assert {path: http.get(path, headers=headers).json() for path in paths} == before
    wrong = http.post(url, headers=headers, json={**body, "answer": "3"})
    assert wrong.status_code == 201 and wrong.json()["correct"] is False
    corrected = http.post(url, headers=headers, json={**body, "answer": " 4 ", "request_id": "choice-correct"})
    assert corrected.status_code == 201 and corrected.json()["correct"] is True
    accuracy = http.get("/study/accuracy", headers=headers).json()
    assert (accuracy["attempts"], accuracy["correct"], accuracy["first_attempts"], accuracy["review_attempts"]) == (2, 1, 1, 1)


def test_legacy_invalid_choice_replays_but_cannot_create_a_new_invalid_attempt(client):
    http, session = client
    headers = auth(register(http, "legacy-choices@example.test"))
    content = generate(http, headers)
    item_id = content["items"][0]["id"]
    student_id = session.scalar(select(User.id).where(User.email == "legacy-choices@example.test"))
    legacy = StudyAnswer(id="legacy-invalid-choice", student_id=student_id, content_id=content["id"],
                         item_id=item_id, request_id="legacy-choice", answer="7", correct=False, score=0.0)
    session.add(legacy)
    session.commit()
    url = f"/study/content/{content['id']}/answer"
    body = {"item_id": item_id, "answer": "7", "request_id": "legacy-choice"}
    replay = http.post(url, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["id"] == legacy.id
    assert http.post(url, headers=headers, json={**body, "answer": "3"}).status_code == 409
    assert http.post(url, headers=headers, json={**body, "request_id": "fresh-invalid"}).status_code == 422
    history = http.get("/study/history", headers=headers).json()
    assert [row["id"] for row in history] == [legacy.id]
    assert http.get("/study/accuracy", headers=headers).json()["attempts"] == 1
