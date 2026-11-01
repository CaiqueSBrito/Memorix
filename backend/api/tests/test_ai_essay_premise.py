"""A sourced rubric cannot launder a false premise in the essay prompt."""
import pytest

from backend.src.Memorix.pipeline.service import _validate
from backend.src.Memorix.providers import generation


def test_false_essay_question_premise_rejected(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A mitose produz duas células-filhas geneticamente idênticas."}
    item = {"question": "Explique por que a mitose produz quatro células-filhas.",
            "rubric": [{"points": 0.5, "criterion": "Quantidade", "expected_answer": "A mitose produz duas células-filhas."}, {"points": 0.5, "criterion": "Identidade genética", "expected_answer": "As células-filhas são geneticamente idênticas."}],
            "evidence": [{"chunk_id": "42:0", "quote": source["text"]}]}

    def judge(claims, sources):
        return [{"supported": True, "chunk_id": "42:0"} for claim in claims]

    monkeypatch.setattr(generation, "check_claims", judge)
    monkeypatch.setattr(generation, "check_item", lambda *args: False)
    with pytest.raises(ValueError, match="suporte"):
        _validate("essay", {"items": [item]}, [source], 1, {})


def test_true_false_item_disallows_hidden_options(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A mitose produz duas células-filhas geneticamente idênticas."}
    item = {"question": "A mitose produz duas células-filhas geneticamente idênticas.",
            "answer": True, "explanation": source["text"],
            "evidence": [{"chunk_id": "42:0", "quote": source["text"]}],
            "options": ["gabarito escondido"]}
    monkeypatch.setattr(generation, "check_claims", lambda *args: pytest.fail("extra field reached judge"))
    with pytest.raises(ValueError, match="campo extra"):
        _validate("true_false", {"items": [item]}, [source], 1, {})


def test_evidence_quote_comes_from_canonical_chunk_not_model_copy(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A mitose produz duas células-filhas geneticamente idênticas."}
    item = {"question": "Quantas células-filhas resultam da mitose?", "answer": "Duas.",
            "explanation": source["text"], "evidence": [{"chunk_id": "42:0"}]}
    monkeypatch.setattr(generation, "check_claims", lambda claims, sources: [
        {"supported": True, "chunk_id": "42:0"} for _ in claims])
    result = _validate("flashcards", {"items": [item]}, [source], 1, {})
    assert result[0]["evidence"] == [{"chunk_id": "42:0", "quote": source["text"]}]


def test_laya_exercises_without_subtype_asks_before_generation(monkeypatch, tmp_path):
    from backend.src.Memorix.pipeline import service

    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))
    monkeypatch.setattr(service, "pin_local_checkpoint", lambda: None)
    monkeypatch.setattr(service.router, "unload", lambda: None)
    monkeypatch.setattr(service.router, "predict", lambda prompt, questions: {
        "answers": {"o que devemos gerar": {"choice": "exercicios",
                                           "probabilities": {"exercicios": 0.992, "aula": 0.004,
                                                             "flashcards": 0.003, "outro": 0.001}}}})
    monkeypatch.setattr(generation, "generate_json", lambda *args: pytest.fail("não escolheu subtipo"))
    response = service.StudyPipeline().generate({"prompt": "Três perguntas sobre mitose"},
                                                session=None)
    assert response["status"] == "clarification" and response["items"] == []
    assert "verdadeiro/falso" in response["message"]


def test_essay_rubric_cannot_be_a_topic_label(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A ligação iônica ocorre pela atração eletrostática entre íons de cargas opostas."}
    item = {"question": "Explique como os íons se atraem numa ligação iônica.",
            "rubric": "Ligações iônicas",
            "evidence": [{"chunk_id": "42:0"}]}
    monkeypatch.setattr(generation, "check_claims", lambda *args: pytest.fail("rubrica vaga chegou ao juiz"))
    with pytest.raises(ValueError, match="rubrica"):
        _validate("essay", {"items": [item]}, [source], 1, {})


def test_essay_question_cannot_reveal_the_answer(monkeypatch):
    source = {"chunk_id": "42:0", "doc_id": 42, "position": 0,
              "text": "A ligação iônica ocorre pela atração eletrostática entre íons de cargas opostas."}
    item = {"question": ("A ligação iônica ocorre pela atração eletrostática entre íons de cargas opostas "
                          "e mantém a rede cristalina dos compostos iônicos. Qual é o papel da força "
                          "eletrostática na ligação iônica?"),
            "rubric": [{"points": 0.5, "criterion": "Força", "expected_answer": "A atração entre os íons é eletrostática."}, {"points": 0.5, "criterion": "Cargas", "expected_answer": "Os íons possuem cargas opostas."}],
            "evidence": [{"chunk_id": "42:0"}]}
    monkeypatch.setattr(generation, "check_item", lambda *args: False)
    with pytest.raises(ValueError, match="suporte"):
        _validate("essay", {"items": [item]}, [source], 1, {})
