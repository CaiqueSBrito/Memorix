"""Public login must bound guessing without permanently disabling an account."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from test_study_api import client


def test_login_throttles_failed_attempts_then_expires(client):
    http, session = client
    credentials = {"email": "admin@example.test", "password": "wrong-password"}
    for _ in range(5):
        response = http.post("/auth/login", json=credentials)
        assert response.status_code == 401, response.text
    assert http.post("/auth/login", json=credentials).status_code == 429
    assert http.post("/auth/login", json={**credentials, "password": "admin-secret-123"}).status_code == 429
    from backend.src.Memorix.entities.study import LoginLimit
    limit = session.scalar(select(LoginLimit))
    assert limit is not None and "admin@example.test" not in limit.key_hash
    limit.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    success = http.post("/auth/login", json={**credentials, "password": "admin-secret-123"})
    assert success.status_code == 200 and success.json()["token"]
