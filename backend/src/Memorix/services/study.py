"""Ownership-safe generated content, answer history and derived review guidance."""

from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..entities.documents import ExcludedSpan
from ..entities.study import FlashcardReveal, GeneratedContent, StudyAnswer, User


def chunk_in_review(session: Session, sha: str, start: int, end: int) -> bool:
    return session.scalar(select(ExcludedSpan.id).where(
        ExcludedSpan.doc_sha256 == sha, ExcludedSpan.offset_start < end,
        ExcludedSpan.offset_end > start).limit(1)) is not None


def reviewed_content_ids(session: Session, contents: list[GeneratedContent]) -> set[str]:
    contents = list({content.id: content for content in contents}.values())
    shas = {source["doc_sha256"] for content in contents for source in content.payload["sources"]}
    if not shas:
        return set()
    spans = session.scalars(select(ExcludedSpan).where(ExcludedSpan.doc_sha256.in_(shas))).all()
    by_sha = defaultdict(list)
    for span in spans:
        by_sha[span.doc_sha256].append(span)
    return {content.id for content in contents for source in content.payload["sources"]
            if any(span.offset_start < source["offset_end"] and span.offset_end > source["offset_start"]
                   for span in by_sha[source["doc_sha256"]])}


def content_in_review(session: Session, content: GeneratedContent) -> bool:
    return bool(reviewed_content_ids(session, [content]))


def public_content(content: GeneratedContent) -> dict:
    payload = content.payload
    response = {"id": content.id, "type": content.kind, "trace_id": content.trace_id,
                "sources": [{key: source[key] for key in
                             ("chunk_id", "doc_id", "doc_sha256", "offset_start", "offset_end")}
                            for source in payload["sources"]],
                "created_at": content.created_at.isoformat()}
    if payload.get("message"):
        response["message"] = payload["message"]
        response["requested_count"] = payload.get("requested_count")
        response["generated_count"] = len(payload.get("lesson") or payload.get("items") or ())
    if content.kind == "lesson":
        response["lesson"] = [{"text": entry["text"],
                               "evidence": [{"chunk_id": source["chunk_id"]} for source in entry["evidence"]]}
                              for entry in payload["lesson"]]
    else:
        response["items"] = [{**{"id": item["id"], "question": item["question"]},
                              **({"options": item["options"]} if content.kind == "multiple_choice" else {}),
                              "evidence": [{"chunk_id": source["chunk_id"]} for source in item["evidence"]]}
                             for item in payload["items"]]
    return response


def save_content(session: Session, student_id: int, result: dict) -> GeneratedContent:
    kind = result["type"]
    if not result.get("sources") or kind not in ("multiple_choice", "true_false", "flashcards", "lesson", "essay"):
        raise ValueError("geração sem fontes ou tipo válido")
    known_sources = {source["chunk_id"] for source in result["sources"]}
    entries = result.get("lesson") if kind == "lesson" else result.get("items")
    if not isinstance(entries, list) or not entries:
        raise ValueError("geração sem conteúdo validado")
    for entry in entries:
        if not entry.get("evidence") or not all(source["chunk_id"] in known_sources for source in entry["evidence"]):
            raise ValueError("conteúdo sem evidência")
        if kind == "lesson":
            if not entry.get("text"):
                raise ValueError("aula vazia")
            continue
        if not entry.get("question"):
            raise ValueError("questão vazia")
        if kind == "multiple_choice" and (not entry.get("options") or entry.get("answer") not in entry["options"]):
            raise ValueError("gabarito inválido")
        if kind in ("true_false", "flashcards") and "answer" not in entry:
            raise ValueError("gabarito ausente")
        if kind == "essay" and not entry.get("rubric"):
            raise ValueError("rubrica ausente")
        entry["id"] = str(uuid4())
    content = GeneratedContent(id=str(uuid4()), student_id=student_id, kind=kind,
                               payload=result, trace_id=result["trace_id"])
    if content_in_review(session, content):
        raise ValueError("fonte em revisão")
    session.add(content)
    session.commit()
    return content


def owned_content(session: Session, student_id: int, content_id: str) -> GeneratedContent | None:
    return session.scalar(select(GeneratedContent).where(GeneratedContent.id == content_id,
                                                          GeneratedContent.student_id == student_id))


def owned_item(content: GeneratedContent, item_id: str) -> dict | None:
    return next((item for item in content.payload.get("items", ()) if item["id"] == item_id), None)

def reveal_flashcard(session: Session, content_id: str, item_id: str) -> None:
    session.execute(insert(FlashcardReveal).values(content_id=content_id, item_id=item_id)
                    .on_conflict_do_nothing(index_elements=("content_id", "item_id")))
    session.commit()


def grade_objective(kind: str, item: dict, answer: str, self_assessment: bool | None) -> bool:
    if kind == "flashcards":
        if self_assessment is None:
            raise ValueError("autoavaliação obrigatória para flashcard")
        return self_assessment
    if kind == "true_false":
        expected = item["answer"]
        expected_bool = expected if isinstance(expected, bool) else str(expected).casefold() in ("verdadeiro", "true")
        value = answer.strip().casefold()
        if value not in ("verdadeiro", "falso", "true", "false"):
            raise ValueError("resposta verdadeiro/falso inválida")
        return (value in ("verdadeiro", "true")) == expected_bool
    if kind == "multiple_choice":
        value = answer.strip().casefold()
        if not any(value == option.strip().casefold() for option in item["options"]):
            raise ValueError("resposta fora das alternativas")
        return value == str(item["answer"]).strip().casefold()
    raise ValueError("item não é objetivo")


def record_answer(session: Session, *, student_id: int, content: GeneratedContent, item: dict,
                  answer: str, request_id: str, self_assessment: bool | None, pipeline) -> tuple[StudyAnswer, bool]:
    # ponytail: a student row lock serializes retries; partition by item if throughput becomes a bottleneck.
    session.scalar(select(User).where(User.id == student_id).with_for_update())
    existing = session.scalar(select(StudyAnswer).where(StudyAnswer.student_id == student_id,
                                                       StudyAnswer.request_id == request_id))
    if existing is not None:
        if (existing.content_id, existing.item_id, existing.answer, existing.self_assessment) != (
            content.id, item["id"], answer, self_assessment
        ):
            raise ValueError("idempotency_conflict")
        return existing, False
    if content.kind == "flashcards" and session.get(FlashcardReveal, (content.id, item["id"])) is None:
        raise ValueError("flashcard_not_revealed")
    if content.kind == "essay":
        result = pipeline.grade_answer(item, answer, trace_id=str(uuid4()))
        score = result["score"]
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("nota inválida")
        correct, feedback, uncertainty, grading_trace_id = None, result["feedback"], result["uncertainty"], result["trace_id"]
    else:
        correct = grade_objective(content.kind, item, answer, self_assessment)
        score, feedback, uncertainty, grading_trace_id = float(correct), None, None, None
    attempt = StudyAnswer(id=str(uuid4()), student_id=student_id, content_id=content.id,
                          item_id=item["id"], request_id=request_id, answer=answer,
                          self_assessment=self_assessment, correct=correct, score=score,
                          feedback=feedback, uncertainty=uncertainty, grading_trace_id=grading_trace_id)
    session.add(attempt)
    session.commit()
    return attempt, True


def public_answer(attempt: StudyAnswer) -> dict:
    return {"id": attempt.id, "content_id": attempt.content_id, "item_id": attempt.item_id,
            "answer": attempt.answer, "self_assessment": attempt.self_assessment,
            "correct": attempt.correct, "score": attempt.score, "feedback": attempt.feedback,
            "uncertainty": attempt.uncertainty, "trace_id": attempt.grading_trace_id,
            "created_at": attempt.created_at.isoformat()}


def student_history(session: Session, student_id: int) -> list[dict]:
    rows = _study_rows(session, student_id)
    reviewed = reviewed_content_ids(session, [content for _, content in rows])
    seen = set()
    history = []
    for answer, content in rows:
        key = (answer.content_id, answer.item_id)
        kind = content.kind
        assessment_type = "self_assessment" if kind == "flashcards" else "essay_rubric" if kind == "essay" else "objective"
        history.append({**public_answer(answer), "type": kind, "assessment_type": assessment_type,
                        "is_review": key in seen, "source_in_review": content.id in reviewed})
        seen.add(key)
    return history


def accuracy(session: Session, student_id: int) -> dict:
    history = student_history(session, student_id)
    excluded = [entry for entry in history if entry["source_in_review"] and
                entry["type"] in ("multiple_choice", "true_false")]
    objective = [entry for entry in history if not entry["source_in_review"] and
                 entry["type"] in ("multiple_choice", "true_false")]
    items = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for attempt in objective:
        item = items[attempt["item_id"]]
        item["attempts"] += 1
        item["correct"] += attempt["correct"] is True
    correct = sum(row["correct"] for row in items.values())
    return {"attempts": len(objective), "correct": correct, "excluded_attempts": len(excluded),
            "accuracy": correct / len(objective) if objective else None,
            "first_attempts": sum(not row["is_review"] for row in objective),
            "review_attempts": sum(row["is_review"] for row in objective),
            "items": [{"item_id": item_id, **row, "accuracy": row["correct"] / row["attempts"]}
                      for item_id, row in items.items()]}


def _study_rows(session: Session, student_id: int) -> list[tuple[StudyAnswer, GeneratedContent]]:
    return session.execute(select(StudyAnswer, GeneratedContent).join(
        GeneratedContent, StudyAnswer.content_id == GeneratedContent.id
    ).where(StudyAnswer.student_id == student_id, GeneratedContent.student_id == student_id).order_by(
        StudyAnswer.sequence)).all()


def _active_study_rows(session: Session, student_id: int) -> list[tuple[StudyAnswer, GeneratedContent]]:
    rows = _study_rows(session, student_id)
    reviewed = reviewed_content_ids(session, [content for _, content in rows])
    return [(answer, content) for answer, content in rows if content.id not in reviewed]


def review_plan(session: Session, student_id: int) -> list[dict]:
    grouped = defaultdict(list)
    for attempt, content in _active_study_rows(session, student_id):
        if content.kind in ("multiple_choice", "true_false", "flashcards"):
            grouped[(attempt.content_id, attempt.item_id)].append((attempt, content))
    plan = []
    for (content_id, item_id), entries in grouped.items():
        streak = 0
        for attempt, _ in entries:
            streak = streak + 1 if attempt.correct else 0
        latest, content = entries[-1]
        days = (1, 3, 7, 14)[min(max(streak - 1, 0), 3)]
        plan.append({"content_id": content_id, "item_id": item_id, "type": content.kind,
                     "due_at": (latest.created_at + timedelta(days=days)).isoformat(),
                     "reason": "Erro ou autoavaliação negativa: reiniciar revisão" if not streak else
                               f"{streak} acerto(s) consecutivo(s): intervalo de {days} dia(s)",
                     "answer_ids": [answer.id for answer, _ in entries]})
    return sorted(plan, key=lambda row: row["due_at"])


def recommendations(session: Session, student_id: int) -> list[dict]:
    grouped = defaultdict(list)
    for attempt, content in _active_study_rows(session, student_id):
        grouped[(attempt.content_id, attempt.item_id)].append((attempt, content))
    result = []
    for (_, item_id), entries in grouped.items():
        latest, content = entries[-1]
        if latest.correct is not False:
            continue
        item = owned_item(content, item_id)
        evidence_ids = {source["chunk_id"] for source in item["evidence"]}
        for source in content.payload["sources"]:
            if source["chunk_id"] in evidence_ids:
                result.append({"doc_id": source["doc_id"], "sources": [source],
                               "reason": "Resposta incorreta ou flashcard marcado para revisão",
                               "answer_ids": [answer.id for answer, _ in entries], "item_id": item_id})
    return result
