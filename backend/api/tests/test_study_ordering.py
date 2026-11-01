"""Persisted answer order must survive transaction-start timestamp inversion."""

from datetime import datetime, timedelta, timezone


from test_study_api import auth, client, generate, register


def test_latest_answer_is_insert_order_not_transaction_start_clock(client):
    http, session = client
    from backend.src.Memorix.entities.study import StudyAnswer
    headers = auth(register(http, "order@example.test"))
    content = generate(http, headers)
    content_id, item_id = content["id"], content["items"][0]["id"]
    ids = []
    for request_id, answer in (("first", "3"), ("second", "4")):
        saved = http.post(f"/study/content/{content_id}/answer", headers=headers,
                          json={"item_id": item_id, "answer": answer, "request_id": request_id})
        assert saved.status_code == 201, saved.text
        ids.append(saved.json()["id"])
    first, second = (session.get(StudyAnswer, answer_id) for answer_id in ids)
    first.created_at = datetime.now(timezone.utc) + timedelta(days=1)
    second.created_at = datetime.now(timezone.utc)
    session.commit()
    history = http.get("/study/history", headers=headers).json()
    assert [entry["id"] for entry in history] == ids
    assert [entry["is_review"] for entry in history] == [False, True]
    plan = http.get("/study/plan", headers=headers).json()
    assert plan[0]["answer_ids"] == ids and "acerto" in plan[0]["reason"]
