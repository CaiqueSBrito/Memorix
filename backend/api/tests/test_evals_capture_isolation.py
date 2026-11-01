"""A completed or failed public benchmark must not capture subsequent student output."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from sqlalchemy.orm import Session

from backend.evals import run
from backend.src.Memorix.providers import generation


@pytest.mark.parametrize("phase", ["after_success", "after_error", "other_thread"])
def test_public_eval_does_not_capture_private_generation(conn, tmp_path, monkeypatch, trace_file, phase):
    cases_dir = tmp_path / "retrieval"
    cases_dir.mkdir()
    case = {"case_id": "public_case", "type": "flashcards", "query": "Um tema ausente",
            "topic": "tema ausente", "out_of_corpus": True, "expected": [], "acceptable": "recusa"}
    (cases_dir / "cases.jsonl").write_text(json.dumps(case), encoding="utf-8")
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run, "SessionLocal", lambda: Session(bind=conn, join_transaction_mode="create_savepoint"))

    def generate(self, request, **kwargs):
        if request["type"] == "essay":
            raise ValueError("Dissertativa fora desta prova de privacidade")
        if phase == "other_thread":
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(generation.generate_json, "Private concurrent study request", {}).result()
        return {"status": "not_found", "items": [], "sources": [], "trace_id": kwargs["trace_id"]}

    private_answer = "private_student_answer_after_public_eval_015"
    monkeypatch.setattr(run.StudyPipeline, "generate", generate)
    monkeypatch.setattr(generation, "generate_json", lambda *args: {"text": private_answer})
    out = tmp_path / "public_eval.json"
    if phase == "after_error":
        with pytest.raises(ValueError, match="case_id"):
            run.generation_eval(out, case_id="missing_case")
    else:
        run.generation_eval(out)
    samples = out.with_suffix(".samples.jsonl")
    before = samples.read_text(encoding="utf-8") if samples.exists() else ""
    if phase != "other_thread":
        generation.generate_json("Private study request, not part of the public benchmark", {})
    after = samples.read_text(encoding="utf-8") if samples.exists() else ""
    assert after == before
    assert private_answer not in after
