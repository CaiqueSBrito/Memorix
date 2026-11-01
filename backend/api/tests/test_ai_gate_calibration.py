"""Consumer contract for fail-closed calibration using only training labels."""
import json
from math import inf, nan
from pathlib import Path

import pytest


def test_separated_scores_use_both_classes_and_maximum_margin():
    from backend.src.Memorix.pipeline.gate import calibrate_gate

    assert calibrate_gate([2.0, 4.0], [-4.0, -2.0]) == 0.0
    assert calibrate_gate([6.0, 8.0], [-4.0, -2.0]) == 2.0


def test_overlap_prioritizes_false_accepts_over_false_refusals():
    from backend.src.Memorix.pipeline.gate import calibrate_gate

    threshold = calibrate_gate([-1.0, 2.0, 8.0], [0.0, 3.0])
    assert threshold == 5.5
    assert sum(score >= threshold for score in [0.0, 3.0]) == 0
    assert sum(score < threshold for score in [-1.0, 2.0, 8.0]) == 2
    assert calibrate_gate([8.0, -1.0, 2.0], [3.0, 0.0]) == threshold


def test_equal_scores_and_all_refused_are_fail_closed():
    from backend.src.Memorix.pipeline.gate import calibrate_gate

    assert calibrate_gate([1.0, 3.0], [1.0]) == 2.0
    assert calibrate_gate([1.0], [1.0]) > 1.0
    assert calibrate_gate([-2.0], [1.0]) > 1.0


@pytest.mark.parametrize("positive,negative", [([], [0.0]), ([0.0], []), ([nan], [0.0]), ([0.0], [inf]), ([0.0], [-inf])])
def test_unidentifiable_or_nonfinite_training_data_cannot_open_gate(positive, negative):
    from backend.src.Memorix.pipeline.gate import calibrate_gate

    with pytest.raises(ValueError):
        calibrate_gate(positive, negative)


def test_recorded_twenty_cases_leave_one_out_without_exclusions():
    from backend.src.Memorix.pipeline.gate import calibrate_gate

    source = Path(__file__).resolve().parents[2] / "evals" / "results" / "retrieval.json"
    rows = json.loads(source.read_text(encoding="utf-8"))["variants"]["hybrid_rerank"]["cases"]
    assert len(rows) == 20
    assert sum(not row["out_of_corpus"] for row in rows) == 12
    assert next(row for row in rows if row["case_id"] == "ret-02")["out_of_corpus"] is False
    predictions = []
    for index, held_out in enumerate(rows):
        training = rows[:index] + rows[index + 1:]
        assert len(training) == 19
        threshold = calibrate_gate(
            [row["score"] for row in training if not row["out_of_corpus"]],
            [row["score"] for row in training if row["out_of_corpus"]],
        )
        predictions.append((held_out, held_out["score"] >= threshold))
    assert sum(admitted for row, admitted in predictions if row["out_of_corpus"]) == 0
    assert sum(not admitted for row, admitted in predictions if not row["out_of_corpus"]) == 0
    assert calibrate_gate(
        [row["score"] for row in rows if not row["out_of_corpus"]],
        [row["score"] for row in rows if row["out_of_corpus"]],
    ) == -1.067626953125
