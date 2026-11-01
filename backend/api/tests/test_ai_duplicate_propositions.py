"""A shared answer is not a proposition; paraphrases can repeat the same fact."""
import pytest

from backend.src.Memorix.pipeline.service import _validate
from backend.src.Memorix.providers import generation


SOURCE = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
          "text": "O coração bombeia o sangue e se localiza entre os pulmões."}


def card(question, answer):
    return {"question": question, "answer": answer, "explanation": SOURCE["text"],
            "evidence": [{"chunk_id": SOURCE["chunk_id"]}]}


def supported_claims(claims, sources):
    return [{"supported": True, "chunk_id": SOURCE["chunk_id"]} for _ in claims]


def test_distinct_facts_with_the_same_answer_remain_available(monkeypatch):
    monkeypatch.setattr(generation, "check_claims", supported_claims)
    monkeypatch.setattr(generation, "generate_json", lambda *args: {"duplicate": False})
    items = [card("Qual órgão bombeia o sangue?", "Coração"),
             card("Qual órgão se localiza entre os pulmões?", "Coração")]
    result = _validate("flashcards", {"items": items}, [SOURCE], 2, {})
    assert {item["question"] for item in result} == {
        "Qual órgão bombeia o sangue?", "Qual órgão se localiza entre os pulmões?"}


@pytest.mark.parametrize("verdict", [True, "false"])
def test_repeated_fact_or_invalid_semantic_verdict_is_not_delivered(monkeypatch, verdict):
    monkeypatch.setattr(generation, "check_claims", supported_claims)
    monkeypatch.setattr(generation, "generate_json", lambda *args: {"duplicate": verdict})
    items = [card("Qual é a função do coração?", "Bombear o sangue."),
             card("O que o coração faz com o sangue?", "Impulsiona o sangue pelo corpo.")]
    with pytest.raises(ValueError, match="validação"):
        _validate("flashcards", {"items": items}, [SOURCE], 2, {})
