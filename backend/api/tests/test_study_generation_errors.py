"""Input and rejected AI output are not a successful study session or a leaked error."""

import pytest
from sqlalchemy import func, select

from test_study_api import auth, client, register


@pytest.mark.parametrize("body", [
    {"prompt": "   ", "type": "flashcards"},
    {"prompt": "membrana plasmática", "topic": "\t\n", "type": "flashcards"},
])
def test_blank_learning_request_is_rejected_at_http_boundary(client, body):
    http, _ = client
    headers = auth(register(http, "input-boundary@example.test"))
    assert http.post("/study/generate", headers=headers, json=body).status_code == 422


def test_rejected_generation_is_explicit_and_never_persisted(client, monkeypatch):
    http, session = client
    from backend.src.Memorix.entities.study import GeneratedContent
    from backend.src.Memorix.pipeline.service import StudyPipeline

    def rejected(self, request, *, session, trace_id=None):
        raise ValueError("unsafe-private-provider-detail")

    monkeypatch.setattr(StudyPipeline, "generate", rejected)
    headers = auth(register(http, "rejected-output@example.test"))
    response = http.post("/study/generate", headers=headers,
                         json={"prompt": "membrana plasmática", "type": "flashcards"})
    assert response.status_code == 422
    assert "unsafe-private-provider-detail" not in response.text
    assert session.scalar(select(func.count()).select_from(GeneratedContent)) == 0
