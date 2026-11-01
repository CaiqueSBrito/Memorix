"""Quarantine removes a source interval, not a still-answerable positive topic."""
import json

from sqlalchemy.orm import Session

from backend.evals import run
from backend.src.Memorix.entities.documents import ExcludedSpan
from backend.src.Memorix.providers import generation


def test_quarantined_anchor_keeps_positive_label_and_all_metric_denominators(conn, tmp_path, monkeypatch, trace_file):
    digest = "e" * 64
    conn.execute(ExcludedSpan.__table__.insert().values(
        doc_sha256=digest, offset_start=0, offset_end=20, reason="Fonte em revisão"))
    cases_dir = tmp_path / "retrieval"
    cases_dir.mkdir()
    case = {"case_id": "safe_alternative", "type": "lesson", "query": "Explique a fotossíntese",
            "topic": "fotossíntese", "out_of_corpus": False, "pedagogical_status": "requires_curation",
            "expected": [{"doc_sha256": digest, "offset_start": 0, "offset_end": 20}],
            "acceptable": "Uso da energia luminosa"}
    (cases_dir / "cases.jsonl").write_text(json.dumps(case), encoding="utf-8")
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run, "SessionLocal", lambda: Session(bind=conn, join_transaction_mode="create_savepoint"))

    def generate(self, request, **kwargs):
        if request["type"] == "essay":
            raise ValueError("Dissertativa fora desta prova de política editorial")
        return {"status": "ok", "type": "lesson", "items": [], "trace_id": kwargs["trace_id"],
                "lesson": [{"text": "A fotossíntese utiliza energia luminosa.", "evidence": [{"chunk_id": "42:1"}]}],
                "sources": [{"chunk_id": "42:1", "doc_sha256": digest, "offset_start": 30, "offset_end": 100}]}

    monkeypatch.setattr(run.StudyPipeline, "generate", generate)
    monkeypatch.setattr(generation, "generate_json", lambda *args: {"relevant": True})
    result = run.generation_eval(tmp_path / "generation.json")
    assert result["results"][0]["expected"] == "ok"
    assert result["valid_output_rate"] == 1
    assert result["configuration"]["quarantine_spans_active"] == 1
    assert result["answer_relevancy_judged"] == result["cases"] == 1
    assert result["answer_relevancy_local_judge_and_status_rate"] == 1
    assert result["results"][0]["requires_human_review"] is True
