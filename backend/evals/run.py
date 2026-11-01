"""Real corpus ingestion/indexing and fixed-case local retrieval, Laya and generation evals.

Use MEMORIX_ENV_FILE=.env.local; DB_DATABASE selects isolated dev/test database.
No remote provider is used. Results contain case IDs and metrics, not student data.
"""
import argparse
import json
import os
from pathlib import Path
from statistics import mean
from threading import Lock, get_ident
from time import monotonic
from uuid import uuid4

from sqlalchemy import func, select

from backend.src.Memorix.contracts.questions import CONTENT_TYPE
from backend.src.Memorix.entities.documents import Chunk, Document, ExcludedSpan
from backend.src.Memorix.ingestion.pdf import ingest_pdf
from backend.src.Memorix.pipeline.retrieval import retrieve
from backend.src.Memorix.pipeline.gate import calibrate_gate
from backend.src.Memorix.pipeline.service import GATE_LOGIT, StudyPipeline, index_documents
from backend.src.Memorix.providers import embedding, reranking
from backend.src.Memorix.providers.database import SessionLocal
from backend.src.Memorix.providers.laya_provider import pin_local_checkpoint, router

HERE = Path(__file__).resolve().parent
_generation_eval_lock = Lock()


def ingest_corpus(directory):
    corpus = Path(directory).resolve()
    paths = sorted(corpus.glob("*.pdf"))
    if not paths:
        raise ValueError("diretório sem PDFs")
    original = Path.cwd()
    from backend.src.Memorix.config.config import ConfigIngestao
    trace_path = Path(os.getenv("MEMORIX_RASTRO_PATH", ConfigIngestao.trace_path))
    os.environ["MEMORIX_RASTRO_PATH"] = str(trace_path.resolve())
    os.chdir(corpus)
    try:
        for path in paths:
            with SessionLocal() as session:
                existing = session.scalar(select(Document.doc_id).where(Document.extra["fonte"].astext == path.name))
            result = ingest_pdf(path.name, title=path.stem.replace("_", " "), uploaded_by="admin-corpus-local", doc_id=existing)
            print(json.dumps({"file": path.name, "doc_id": result.doc_id, "status": result.status}, ensure_ascii=False), flush=True)
    finally:
        os.chdir(original)


def index_corpus():
    with SessionLocal.begin() as session:
        result = index_documents(session)
    embedding.unload()
    print(json.dumps(result))


def _overlap(row, item):
    if row["doc_sha256"] != item["doc_sha256"]:
        return False
    a = max(row["offset_start"], item["offset_start"])
    b = min(row["offset_end"], item["offset_end"])
    overlap = max(0, b - a)
    return overlap >= (item["offset_end"] - item["offset_start"]) * 0.5 or overlap >= (row["offset_end"] - row["offset_start"]) * 0.5


def _percentile(values):
    values = sorted(values)
    return values[(95 * len(values) + 99) // 100 - 1] if values else None


def _metrics(rows):
    positives = [r for r in rows if not r["out_of_corpus"]]
    return {"recall_at_5": mean(r["hit_at_5"] for r in positives),
            "mrr_at_10": mean(r["reciprocal_rank"] for r in positives),
            "context_recall_at_30": mean(r["hit_at_30"] for r in positives),
            "context_precision_at_10": mean(r["context_precision"] for r in positives),
            "p95_ms_one_pass": _percentile([r["duration_ms"] for r in rows])}


def _leave_one_out(rows, signal):
    positive = [r for r in rows if not r["out_of_corpus"]]
    negative = [r for r in rows if r["out_of_corpus"]]
    predicted = []
    for sample in rows:
        training_pos = [row[signal] for row in positive if row is not sample and row[signal] is not None]
        training_neg = [row[signal] for row in negative if row is not sample and row[signal] is not None]
        threshold = calibrate_gate(training_pos, training_neg)
        predicted.append((sample, sample[signal] is not None and sample[signal] >= threshold, threshold))
    return {"far": sum(admit for row, admit, _ in predicted if row["out_of_corpus"]) / len(negative),
            "frr": sum(not admit for row, admit, _ in predicted if not row["out_of_corpus"]) / len(positive),
            "thresholds": {row["case_id"]: threshold for row, _, threshold in predicted}}


def retrieval_eval(corpus):
    from backend.src.Memorix.ingestion.canonical import canonicalize, doc_sha256
    from backend.src.Memorix.ingestion.pdf import _extract_with_metadata

    cases = [json.loads(line) for line in (HERE / "retrieval" / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    indexed = {}
    with SessionLocal() as session:
        for row in session.execute(select(Document.doc_sha256, func.count(Chunk.chunk_id)).join(Chunk).where(Chunk.embedding_model == embedding.MODEL_ID).group_by(Document.doc_sha256)):
            indexed[row[0]] = row[1]
    canonical_texts = {}
    for case in cases:
        for expected in case["expected"]:
            filename = expected["file"]
            if filename not in canonical_texts:
                canonical_texts[filename] = canonicalize(_extract_with_metadata(Path(corpus) / filename)[0])
            source = canonical_texts[filename]
            if doc_sha256(source) != expected["doc_sha256"] or not source[expected["offset_start"]:expected["offset_end"]].startswith(expected["anchor"]):
                raise ValueError(f"âncora/sha inválidos para {case['case_id']}")
            if expected["doc_sha256"] not in indexed:
                raise ValueError(f"documento do caso {case['case_id']} não está indexado")
    if len(indexed) != len(list(Path(corpus).glob("*.pdf"))):
        raise ValueError("corpus incompleto: indexe todos os PDFs antes do eval")
    result = {"cases": len(cases), "indexed_documents": len(indexed), "indexed_chunks": sum(indexed.values()), "variants": {}}
    for variant in ("dense", "hybrid", "dense_rerank", "hybrid_rerank"):
        mode = "dense" if variant.startswith("dense") else "hybrid"
        scored, measured = [], []
        with SessionLocal() as session:
            warmup_ms = []
            for _ in range(3):
                warm_start = monotonic()
                warm_pool = retrieve(session, cases[0]["topic"], mode=mode, trace_id=str(uuid4()))
                if variant.endswith("_rerank"):
                    reranking.score(cases[0]["topic"], [row["text"] for row in warm_pool])
                warmup_ms.append((monotonic() - warm_start) * 1000)
            for repeat in range(5):
                for case in cases:
                    start = monotonic()
                    pool = retrieve(session, case["topic"], mode=mode, trace_id=str(uuid4()))
                    raw = list(pool)
                    if variant.endswith("_rerank"):
                        logits = reranking.score(case["topic"], [row["text"] for row in pool])
                        if len(logits) != len(pool):
                            raise ValueError("reranker devolveu quantidade incorreta")
                        pool = [row for row, _ in sorted(zip(pool, logits), key=lambda pair: (-pair[1], pair[0]["chunk_id"]))]
                        score = max(logits, default=None)
                    else:
                        score = max((row["cosine"] for row in pool if row["cosine"] is not None), default=None)
                    relevant = lambda rows: [any(_overlap(row, e) for e in case["expected"]) for row in rows]
                    hits = relevant(pool)
                    precision = sum((sum(hits[:index + 1]) / (index + 1)) for index, hit in enumerate(hits[:10]) if hit) / max(1, sum(hits[:10]))
                    entry = {"case_id": case["case_id"], "out_of_corpus": case["out_of_corpus"],
                             "hit_at_5": any(hits[:5]), "hit_at_30": any(relevant(raw)),
                             "reciprocal_rank": next((1 / (i + 1) for i, hit in enumerate(hits[:10]) if hit), 0),
                             "context_precision": precision, "score": score,
                             "duration_ms": (monotonic() - start) * 1000,
                             "top_chunk_ids": [row["chunk_id"] for row in pool[:5]]}
                    measured.append(entry)
                    if repeat == 0:
                        scored.append(entry)
        result["variants"][variant] = {**_metrics(measured), "cold_ms": warmup_ms[0], "warmups_ms": warmup_ms[1:],
                                       "gate_leave_one_out": _leave_one_out(scored, "score"), "cases": scored,
                                       "warm_samples": len(measured)}
    embedding.unload()
    reranking.unload()
    return result


def laya_eval():
    cases = [json.loads(line) for line in (HERE / "classification" / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    results = []
    pin_local_checkpoint()
    try:
        for index, case in enumerate(cases):
            prediction = router.predict(case["query"], questions=CONTENT_TYPE)["answers"]["o que devemos gerar"]
            choice = prediction["choice"]
            results.append({"index": index, "expected": case["label"], "choice": choice,
                            "probability_choice": prediction["probabilities"][choice], "correct": choice == case["label"]})
    finally:
        router.unload()
    false_positives = [row["probability_choice"] for row in results if not row["correct"]]
    threshold = max(false_positives, default=0) + 1e-4
    return {"cases": len(cases), "accuracy": mean(row["correct"] for row in results),
            "measured_no_false_choice_threshold": threshold, "results": results}


def duplicate_eval():
    from backend.src.Memorix.providers import generation

    cases = [json.loads(line) for line in (HERE / "generation_duplicates.jsonl").read_text(encoding="utf-8").splitlines()]
    records = []
    for case in cases:
        started = monotonic()
        row = {"case_id": case["case_id"], "type": case["type"],
               "expected_duplicate": case["expected_duplicate"], "correct": False}
        try:
            result = generation.check_duplicates(case["type"], case["items"])
            row.update(duplicate=result["duplicate"], correct=result["duplicate"] == case["expected_duplicate"],
                       usage=result.get("_usage", {}))
        except Exception as error:
            row.update(duplicate=None, error=type(error).__name__)
        row["duration_ms"] = (monotonic() - started) * 1000
        records.append(row)
    return {"configuration": {"model": generation.MODEL, "prompt_version": generation.DUPLICATE_VERSION,
                              "temperature": 0, "num_ctx": 4096},
            "cases": len(records), "correct": sum(row["correct"] for row in records),
            "accuracy": mean(row["correct"] for row in records),
            "false_positive": sum(row["duplicate"] is True and not row["expected_duplicate"] for row in records),
            "false_negative": sum(row["duplicate"] is False and row["expected_duplicate"] for row in records),
            "errors": sum("error" in row for row in records),
            "p95_ms_one_pass": _percentile([row["duration_ms"] for row in records]),
            "results": records}


def _generation_eval(out: Path | None = None, case_id: str | None = None):
    from backend.src.Memorix.providers import generation
    from backend.src.Memorix.providers.observabilitiy import read_trace

    samples_file = (out or HERE / "results" / "generation.json").with_suffix(".samples.jsonl")
    samples_file.parent.mkdir(parents=True, exist_ok=True)
    raw_generate = generation.generate_json
    current_case = ""
    benchmark_thread = get_ident()

    def capture(prompt, schema):
        result = raw_generate(prompt, schema)
        if get_ident() != benchmark_thread:
            return result
        stage = next((key for key in ("items", "lesson", "checks", "relevant", "score") if key in result), "other")
        with samples_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"case_id": current_case, "stage": stage, "raw_model_output": result},
                                  ensure_ascii=False) + "\n")
        return result

    generation.generate_json = capture

    cases = [json.loads(line) for line in (HERE / "retrieval" / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    if case_id:
        cases = [case for case in cases if case["case_id"] == case_id]
        if not cases:
            raise ValueError("case_id desconhecido")
    records, samples = [], {}
    schema = {"type": "object", "properties": {"relevant": {"type": "boolean"}}, "required": ["relevant"]}
    with SessionLocal() as session:
        active_span_count = session.scalar(select(func.count()).select_from(ExcludedSpan))
        for case in cases:
            quarantined = (case.get("pedagogical_status") == "requires_curation" and
                           any(session.scalar(select(ExcludedSpan.id).where(
                               ExcludedSpan.doc_sha256 == anchor["doc_sha256"],
                               ExcludedSpan.offset_start < anchor["offset_end"],
                               ExcludedSpan.offset_end > anchor["offset_start"]).limit(1))
                               for anchor in case["expected"]))
            expected = "not_found" if case["out_of_corpus"] else "ok"
            trace_id = str(uuid4())
            current_case = case["case_id"]
            try:
                output = StudyPipeline().generate({"prompt": case["query"], "topic": case["topic"], "type": case["type"], "count": 1},
                                                  session=session, trace_id=trace_id)
                valid = output["status"] == "ok" and bool(output.get("items") or output.get("lesson"))
                if (valid and output["status"] == expected and case["type"] not in samples and
                    case.get("pedagogical_status") != "requires_curation"):
                    samples[case["type"]] = {"case_id": case["case_id"], "output": output}
                with samples_file.open("a", encoding="utf-8") as file:
                    file.write(json.dumps({"case_id": current_case, "validated_output": output},
                                          ensure_ascii=False) + "\n")
                cited_expected = (any(ref["chunk_id"] == source["chunk_id"] and
                                      any(_overlap(source, anchor) for anchor in case["expected"])
                                      for item in (output.get("items") or output.get("lesson") or [])
                                      for ref in item["evidence"] for source in output["sources"])
                                  if valid else None)
                if valid:
                    entry = (output.get("items") or output.get("lesson"))[0]
                    content = json.dumps({k: v for k, v in entry.items() if k != "evidence"}, ensure_ascii=False)
                    verdict = generation.generate_json(
                        "Julgue estritamente se a SAÍDA avalia exatamente o objetivo específico do PEDIDO e "
                        "satisfaz o CRITÉRIO: tema adjacente ou mesmo assunto amplo não bastam. "
                        "Pergunta sobre outro eixo conceitual não mede o pedido. "
                        "Se faltar conceito ou relação exigida, relevant=false. "
                        f"PEDIDO: {case['query']}\nCRITÉRIO: {case['acceptable']}\nSAÍDA: {content}",
                        schema)["relevant"]
                    if type(verdict) is not bool:
                        raise ValueError("juiz de relevância não retornou booleano")
                    relevance = verdict and output["status"] == expected
                else:
                    relevance = (output["status"] == expected and not output.get("items") and
                                 not output.get("lesson"))
                records.append({"case_id": case["case_id"], "status": output["status"], "expected": expected,
                                "pedagogical_status": case.get("pedagogical_status", "reviewed"),
                                "expected_anchor_in_review": bool(quarantined),
                                "valid_output": (output["status"] == "not_found") if case["out_of_corpus"] else valid,
                                "expected_source_overlap": cited_expected,
                                "answer_relevancy_local_judge_and_status": relevance,
                                "requires_human_review": bool(valid and (quarantined or cited_expected is False))})
            except Exception as error:
                session.rollback()
                records.append({"case_id": case["case_id"], "status": "error", "expected": expected,
                                "pedagogical_status": case.get("pedagogical_status", "reviewed"),
                                "error": type(error).__name__, "error_detail": str(error)[:160], "valid_output": False,
                                "answer_relevancy_local_judge_and_status": False})
            checks = [event for event in read_trace(trace_id) if event["etapa"] == "validacao"]
            with samples_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"case_id": current_case, "result": records[-1]}, ensure_ascii=False) + "\n")
            if not case["out_of_corpus"]:
                records[-1].update(claims=checks[-1].get("claims", 0) if checks else 0,
                                   supported_claims=checks[-1].get("supported_claims", 0) if checks else 0)
        current_case = "essay-grade"
        try:
            essay = StudyPipeline().generate(
                {"prompt": "Crie uma pergunta dissertativa sobre ligações iônicas", "topic": "ligações iônicas",
                 "type": "essay", "count": 1}, session=session)
            grade = StudyPipeline().grade_answer(essay["items"][0], "Atração entre íons de cargas opostas.")
            samples["essay"] = {"output": essay, "grade": grade}
            with samples_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"case_id": current_case, "validated_output": essay, "grade": grade},
                                      ensure_ascii=False) + "\n")
        except Exception as error:
            samples["essay"] = {"error": type(error).__name__, "detail": str(error)[:160]}
    positive = [row for row, case in zip(records, cases) if not case["out_of_corpus"]]
    checked = sum(row["claims"] for row in positive)
    judged = [row["answer_relevancy_local_judge_and_status"] for row in records]
    return {"cases": len(records), "configuration": {"generation_model": generation.MODEL,
            "embedding_model": embedding.MODEL_ID, "reranking_model": f"{reranking.MODEL}@{reranking.REVISION}",
            "gate_logit": GATE_LOGIT, "temperature": 0, "num_ctx": 4096,
            "quarantine_spans_active": active_span_count},
            "valid_output_rate": mean(row["valid_output"] for row in records),
            "faithfulness_claim_supported_ratio": sum(row["supported_claims"] for row in positive) / checked if checked else None,
            "faithfulness_claims_checked": checked, "positives_reaching_claim_check": sum(bool(row["claims"]) for row in positive),
            "answer_relevancy_local_judge_and_status_rate": mean(judged) if judged else None,
            "answer_relevancy_judged": len(judged),
            "expected_source_overlap_positive_rate": (sum(row.get("expected_source_overlap") is True for row in positive) / len(positive)
                                                      if positive else None),
            "human_review_case_ids": [row["case_id"] for row in records if row.get("requires_human_review")],
            "results": records, "sample_outputs_for_pedagogy": samples}


def generation_eval(out: Path | None = None, case_id: str | None = None):
    from backend.src.Memorix.providers import generation

    # ponytail: global provider patch serializes benchmarks; inject a provider if parallel evals are needed.
    with _generation_eval_lock:
        original = generation.generate_json
        try:
            return _generation_eval(out, case_id)
        finally:
            generation.generate_json = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ingest", "index", "retrieval", "laya", "generation", "duplicates"))
    parser.add_argument("--corpus", default=str(Path.home() / "Documents" / "Docs Memorix"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--case-id", help="Execute only one public eval case (generation)")
    args = parser.parse_args()
    if args.action == "ingest":
        return ingest_corpus(args.corpus)
    if args.action == "index":
        return index_corpus()
    result = {"retrieval": lambda: retrieval_eval(args.corpus), "laya": laya_eval,
              "generation": lambda: generation_eval(args.out, args.case_id),
              "duplicates": duplicate_eval}[args.action]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
