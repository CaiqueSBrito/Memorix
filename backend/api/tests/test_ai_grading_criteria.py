"""Essay scores come from the rubric's bounded criteria, not an unsupported total."""

import pytest

from backend.src.Memorix.pipeline.service import StudyPipeline
from backend.src.Memorix.providers import generation


CONTENT = {
    "question": "Explique o mecanismo da ligação iônica e a estrutura resultante.",
    "rubric": [{"points": 0.5, "criterion": "Mecanismo", "expected_answer": "Íons de cargas opostas se atraem eletrostaticamente."}, {"points": 0.5, "criterion": "Estrutura", "expected_answer": "Os íons formam uma rede cristalina."}],
    "evidence": [{"chunk_id": "42:0", "quote": "Íons de cargas opostas atraem-se e formam uma rede cristalina."}],
}


def test_partial_essay_score_is_sum_of_bounded_rubric_criteria(monkeypatch, trace_file):
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "criteria": [
            {"index": 1, "points_awarded": 0.5, "evidence_quote": "Cargas opostas se atraem."},
            {"index": 2, "points_awarded": 0, "evidence_quote": ""},
        ],
        "uncertainty": "A descrição da estrutura não foi apresentada.",
    })
    grade = StudyPipeline().grade_answer(CONTENT, "Cargas opostas se atraem.")
    assert grade["score"] == 0.5
    assert [criterion["status"] for criterion in grade["criteria"]] == ["met", "not_met"]
    assert grade["sources"] == CONTENT["evidence"]
    assert grade["criteria"][1]["points_awarded"] == 0


@pytest.mark.parametrize("criteria", [
    [{"index": 1, "points_awarded": 0.6}, {"index": 2, "points_awarded": 0}],
    [{"index": 1, "points_awarded": 0.5}, {"index": 1, "points_awarded": 0.5}],
    [{"index": 1, "points_awarded": float("nan")}, {"index": 2, "points_awarded": 0}],
])
def test_essay_grading_rejects_unbounded_or_duplicate_criteria(monkeypatch, trace_file, criteria):
    criteria = [{**criterion, "evidence_quote": "Cargas opostas se atraem."} for criterion in criteria]
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "criteria": criteria, "uncertainty": "Avaliação inconsistente.",
    })
    with pytest.raises(ValueError, match="critério"):
        StudyPipeline().grade_answer(CONTENT, "Cargas opostas se atraem.")


def test_essay_cannot_award_points_without_student_evidence(monkeypatch, trace_file):
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "criteria": [
            {"index": 1, "points_awarded": 0.5, "evidence_quote": "Cargas opostas se atraem."},
            {"index": 2, "points_awarded": 0.2, "evidence_quote": ""},
        ],
        "uncertainty": "A estrutura não foi descrita.",
    })
    with pytest.raises(ValueError, match="critério"):
        StudyPipeline().grade_answer(CONTENT, "Cargas opostas se atraem.")


def test_partial_credit_and_total_preserve_criterion_status(monkeypatch, trace_file):
    answer = "Cargas opostas se atraem. Os íons formam uma rede cristalina."
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "criteria": [
            {"index": 1, "points_awarded": 0.25, "evidence_quote": "Cargas opostas se atraem."},
            {"index": 2, "points_awarded": 0.5, "evidence_quote": "Os íons formam uma rede cristalina."},
        ],
        "uncertainty": "O mecanismo da força não foi explicitado.",
    })
    grade = StudyPipeline().grade_answer(CONTENT, answer)
    assert grade["score"] == 0.75
    assert [criterion["status"] for criterion in grade["criteria"]] == ["partial", "met"]


def test_zero_credit_preserves_the_incorrect_passage_for_feedback(monkeypatch, trace_file):
    answer = "Átomos neutros compartilham elétrons para formar uma ligação iônica."
    monkeypatch.setattr(generation, "generate_json", lambda *args: {
        "criteria": [
            {"index": 1, "points_awarded": 0, "evidence_quote": answer},
            {"index": 2, "points_awarded": 0, "evidence_quote": ""},
        ],
        "uncertainty": "Nenhuma incerteza identificada.",
    })
    grade = StudyPipeline().grade_answer(CONTENT, answer)
    assert grade["score"] == 0
    assert grade["criteria"][0]["status"] == "not_met"
    assert answer in grade["feedback"]
    assert CONTENT["rubric"][0]["expected_answer"] in grade["feedback"]
