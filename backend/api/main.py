"""HTTP API for the student study cycle; no user-provided owner or role is trusted."""

from datetime import datetime, timezone
from hashlib import sha256
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from backend.src.Memorix.entities.documents import Chunk, Document, ExcludedSpan
from backend.src.Memorix.entities.study import LoginSession, User
from backend.src.Memorix.ingestion import ingest, pdf
from backend.src.Memorix.pipeline import service as ai_service
from backend.src.Memorix.providers.database import SessionLocal
from backend.src.Memorix.providers.observabilitiy import read_trace, summarize_traces
from backend.src.Memorix.services import auth, study

app = FastAPI(title="Memorix API")
logger = logging.getLogger(__name__)
SOURCE_IN_REVIEW = "Fonte em revisão; conteúdo temporariamente indisponível"
bearer = HTTPBearer(auto_error=False)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Register(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=256)
    adult_confirmed: bool
    invitation_token: str | None = Field(default=None, max_length=256)


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Invite(Input):
    guardian_verified: bool
    minor_email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class TextUpload(Input):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=255)


class IndexRequest(Input):
    doc_ids: list[int] | None = None


class ReviewSpanRequest(Input):
    doc_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset_start: int = Field(ge=0)
    offset_end: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class GenerateRequest(Input):
    prompt: str = Field(min_length=1, max_length=1000)
    topic: str | None = Field(default=None, min_length=1, max_length=500)
    type: str | None = Field(default=None, pattern=r"^(multiple_choice|true_false|flashcards|lesson|essay)$")
    count: int | None = Field(default=None, ge=1, le=5)
    difficulty: Literal["basic", "intermediate", "advanced"] | None = None
    cognitive_level: Literal["recall", "understand", "apply", "analyze"] | None = None

    @field_validator("prompt", "topic")
    @classmethod
    def require_learning_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("texto de aprendizagem vazio")
        return value


class AnswerRequest(Input):
    item_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=5000)
    request_id: str = Field(min_length=1, max_length=100)
    self_assessment: bool | None = None


def get_session():
    with SessionLocal() as session:
        yield session


def authenticated(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                  session: Session = Depends(get_session)) -> tuple[User, LoginSession]:
    active = auth.get_active_session(session, credentials.credentials) if credentials and len(credentials.credentials) <= 256 else None
    if active is None:
        raise HTTPException(401, "Sessão inválida ou expirada")
    return active


def student(principal: tuple[User, LoginSession] = Depends(authenticated)) -> User:
    if principal[0].role != "student":
        raise HTTPException(403, "Acesso restrito a alunos")
    return principal[0]


def admin(principal: tuple[User, LoginSession] = Depends(authenticated)) -> User:
    if principal[0].role != "admin":
        raise HTTPException(403, "Acesso restrito a administradores")
    return principal[0]


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Entrada inválida"})


@app.middleware("http")
async def internal_failure(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Model/provider exceptions can contain student input; never let the server log their text.
        return JSONResponse(status_code=500, content={"detail": "Falha interna"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", status_code=201)
def register(body: Register, session: Session = Depends(get_session)):
    if body.adult_confirmed and body.invitation_token:
        raise HTTPException(422, "Convite é exclusivo para menor")
    try:
        user = auth.register_student(session, body.email, body.password,
                                     adult_confirmed=body.adult_confirmed,
                                     invitation_token=body.invitation_token)
        if user is None:
            raise HTTPException(403, "Convite de responsável verificado necessário")
        return {"token": auth.start_session(session, user), "role": user.role}
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Cadastro indisponível") from None


@app.post("/auth/login")
def login(body: Login, session: Session = Depends(get_session)):
    user, limited = auth.check_login(session, body.email, body.password)
    if limited:
        raise HTTPException(429, "Tente novamente mais tarde")
    if user is None:
        raise HTTPException(401, "Credenciais inválidas")
    return {"token": auth.start_session(session, user), "role": user.role}


@app.post("/auth/logout", status_code=204)
def logout(principal: tuple[User, LoginSession] = Depends(authenticated),
           session: Session = Depends(get_session)):
    principal[1].revoked_at = datetime.now(timezone.utc)
    session.commit()
    return Response(status_code=204)


@app.post("/admin/minor-invitations", status_code=201)
def invite_minor(body: Invite, administrator: User = Depends(admin), session: Session = Depends(get_session)):
    if not body.guardian_verified:
        raise HTTPException(422, "Verificação externa do responsável necessária")
    return {"invitation_token": auth.create_invitation(session, administrator, body.minor_email)}


def _index(session: Session, doc_ids: list[int] | None, trace_id: str):
    result = ai_service.index_documents(session, doc_ids=doc_ids, trace_id=trace_id)
    session.commit()
    return result


@app.post("/admin/ingest/text", status_code=201)
async def ingest_text(request: Request, administrator: User = Depends(admin), session: Session = Depends(get_session)):
    if request.headers.get("transfer-encoding") or not (request.headers.get("content-length") or "").isdigit():
        raise HTTPException(411, "Tamanho de documento obrigatório")
    if int(request.headers["content-length"]) > 8 * 1024 * 1024:
        raise HTTPException(413, "Documento excede o limite")
    received = bytearray()
    async for block in request.stream():
        received.extend(block)
        if len(received) > 8 * 1024 * 1024:
            raise HTTPException(413, "Documento excede o limite")
    try:
        body = TextUpload.model_validate_json(received)
    except ValidationError:
        raise HTTPException(422, "Entrada inválida") from None
    uploaded_by = str(administrator.id)
    session.commit()  # ingest_document owns session.begin(); release auth SELECT transaction first.
    trace_id = str(uuid4())
    try:
        document = ingest.ingest_document(body.text, title=body.title, source_type="texto",
                                          uploaded_by=uploaded_by, source=body.source,
                                          session=session, trace_id=trace_id)
    except ValueError:
        raise HTTPException(422, "Documento inválido") from None
    result = _index(session, [document.doc_id], trace_id)
    return {"doc_id": document.doc_id, "status": document.status, "indexed": result["indexed"],
            "trace_id": trace_id}


@app.post("/admin/ingest/pdf", status_code=201)
async def ingest_pdf(request: Request, administrator: User = Depends(admin),
                     session: Session = Depends(get_session)):
    if request.headers.get("transfer-encoding") or not (request.headers.get("content-length") or "").isdigit():
        raise HTTPException(411, "Tamanho de upload obrigatório")
    if int(request.headers["content-length"]) > 256 * 1024 * 1024:
        raise HTTPException(413, "PDF excede o limite")
    original_receive = request._receive
    received = 0
    async def limited_receive():
        nonlocal received
        event = await original_receive()
        received += len(event.get("body", b""))
        if received > 256 * 1024 * 1024:
            raise HTTPException(413, "PDF excede o limite")
        return event
    request._receive = limited_receive
    form = await request.form()
    file = form.get("file")
    title = form.get("title")
    if (not isinstance(file, UploadFile) or not file.filename or
            not file.filename.lower().endswith(".pdf") or not isinstance(title, str) or not title.strip()):
        await form.close()
        raise HTTPException(422, "PDF ou título inválido")
    uploaded_by = str(administrator.id)
    session.commit()
    trace_id = str(uuid4())
    upload_dir = Path("backend/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid4()}.pdf"
    ingested = False
    try:
        with path.open("xb") as destination:
            size = 0
            while block := await file.read(1024 * 1024):
                size += len(block)
                if size > 256 * 1024 * 1024:
                    raise HTTPException(413, "PDF excede o limite")
                destination.write(block)
        try:
            document = pdf.ingest_pdf(path.as_posix(), title=title, uploaded_by=uploaded_by,
                                      session=session, trace_id=trace_id)
        except ValueError:
            raise HTTPException(422, "PDF inválido") from None
        ingested = True
        result = _index(session, [document.doc_id], trace_id)
        return {"doc_id": document.doc_id, "status": document.status, "indexed": result["indexed"],
                "trace_id": trace_id}
    finally:
        await form.close()
        if not ingested:
            path.unlink(missing_ok=True)


@app.post("/admin/index")
def index_documents(body: IndexRequest | None = None, administrator: User = Depends(admin),
                    session: Session = Depends(get_session)):
    return _index(session, body.doc_ids if body else None, str(uuid4()))


@app.get("/admin/traces/{trace_id}")
def trace(trace_id: str, administrator: User = Depends(admin)):
    return {"trace_id": trace_id, "stages": read_trace(trace_id)}


@app.get("/admin/metrics")
def metrics(administrator: User = Depends(admin)):
    return summarize_traces()


@app.post("/admin/review-spans", status_code=201)
def add_review_span(body: ReviewSpanRequest, administrator: User = Depends(admin),
                    session: Session = Depends(get_session)):
    document = session.scalar(select(Document).where(Document.doc_sha256 == body.doc_sha256))
    if document is None:
        raise HTTPException(404, "Documento não encontrado")
    max_offset = session.scalar(select(func.max(Chunk.offset_end)).where(Chunk.doc_id == document.doc_id))
    if not body.reason.strip() or max_offset is None or body.offset_start >= body.offset_end or body.offset_end > max_offset:
        raise HTTPException(422, "Intervalo ou motivo inválido")
    span = ExcludedSpan(doc_sha256=body.doc_sha256, offset_start=body.offset_start,
                        offset_end=body.offset_end, reason=body.reason.strip())
    session.add(span)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Trecho já está em revisão") from None
    logger.info("review_span_created id=%s reason_sha256=%s", span.id, sha256(span.reason.encode()).hexdigest())
    return {"id": span.id, "doc_sha256": span.doc_sha256, "offset_start": span.offset_start,
            "offset_end": span.offset_end, "reason": span.reason, "created_at": span.created_at}


@app.get("/admin/review-spans")
def list_review_spans(administrator: User = Depends(admin), session: Session = Depends(get_session)):
    spans = session.scalars(select(ExcludedSpan).order_by(ExcludedSpan.id)).all()
    return [{"id": span.id, "doc_sha256": span.doc_sha256, "offset_start": span.offset_start,
             "offset_end": span.offset_end, "reason": span.reason, "created_at": span.created_at} for span in spans]


@app.delete("/admin/review-spans/{span_id}", status_code=204)
def remove_review_span(span_id: int, administrator: User = Depends(admin),
                       session: Session = Depends(get_session)):
    span = session.get(ExcludedSpan, span_id)
    if span is None:
        raise HTTPException(404, "Trecho não encontrado")
    reason_hash = sha256(span.reason.encode()).hexdigest()
    session.delete(span)
    session.commit()
    logger.info("review_span_deleted id=%s reason_sha256=%s", span_id, reason_hash)
    return Response(status_code=204)


@app.get("/study/materials/{doc_id}")
def material(doc_id: int, chunk_id: str, learner: User = Depends(student),
             session: Session = Depends(get_session)):
    record = session.get(Document, doc_id)
    chunk = session.scalar(select(Chunk).where(Chunk.doc_id == doc_id, Chunk.chunk_id == chunk_id))
    if record is None or chunk is None:
        raise HTTPException(404, "Material não encontrado")
    if study.chunk_in_review(session, record.doc_sha256, chunk.offset_start, chunk.offset_end):
        raise HTTPException(410, SOURCE_IN_REVIEW)
    return {"doc_id": doc_id, "title": record.title, "chunk_id": chunk_id, "text": chunk.text}


@app.get("/study/materials/{doc_id}/download")
def download_material(doc_id: int, principal: tuple[User, LoginSession] = Depends(authenticated),
                      session: Session = Depends(get_session)):
    record = session.get(Document, doc_id)
    if record is None or record.source_type != "pdf":
        raise HTTPException(404, "Material não encontrado")
    if session.scalar(select(ExcludedSpan.id).where(ExcludedSpan.doc_sha256 == record.doc_sha256).limit(1)) is not None:
        raise HTTPException(410, SOURCE_IN_REVIEW)
    location = record.extra.get("fonte", "")
    path = Path(location)
    # Only archive-managed uploads, never arbitrary paths or original client filenames.
    if not path.is_relative_to(Path("backend/uploads")) or not path.is_file():
        raise HTTPException(404, "PDF indisponível")
    return FileResponse(path, media_type="application/pdf", filename=f"material-{doc_id}.pdf")


@app.post("/study/generate")
def generate(body: GenerateRequest, learner: User = Depends(student), session: Session = Depends(get_session)):
    trace_id = str(uuid4())
    request = body.model_dump(exclude_none=True)
    try:
        result = ai_service.StudyPipeline().generate(request, session=session, trace_id=trace_id)
    except ValueError:
        session.rollback()
        return JSONResponse(
            {"status": "rejected", "message": "Não foi possível validar o conteúdo gerado; reformule o pedido.",
             "trace_id": trace_id},
            status_code=422,
        )
    if result["status"] != "ok":
        session.rollback()
        return {"status": result["status"], "message": result["message"], "trace_id": result["trace_id"]}
    if result.get("message") and "requested_count" not in result:
        result["requested_count"] = body.count or 1
    try:
        content = study.save_content(session, learner.id, result)
    except (ValueError, KeyError, TypeError):
        session.rollback()
        raise HTTPException(422, "Conteúdo sem fontes válidas") from None
    return JSONResponse(study.public_content(content), status_code=201)


@app.get("/study/content/{content_id}")
def content(content_id: str, learner: User = Depends(student), session: Session = Depends(get_session)):
    document = study.owned_content(session, learner.id, content_id)
    if document is None:
        raise HTTPException(404, "Conteúdo não encontrado")
    if study.content_in_review(session, document):
        raise HTTPException(410, SOURCE_IN_REVIEW)
    return study.public_content(document)


@app.post("/study/content/{content_id}/items/{item_id}/reveal")
def reveal_flashcard(content_id: str, item_id: str, learner: User = Depends(student),
                     session: Session = Depends(get_session)):
    document = study.owned_content(session, learner.id, content_id)
    if document is None or document.kind != "flashcards":
        raise HTTPException(404, "Flashcard não encontrado")
    if study.content_in_review(session, document):
        raise HTTPException(410, SOURCE_IN_REVIEW)
    item = study.owned_item(document, item_id)
    if item is None:
        raise HTTPException(404, "Flashcard não encontrado")
    study.reveal_flashcard(session, document.id, item_id)
    sources = [source for source in document.payload["sources"]
               if source["chunk_id"] in {ref["chunk_id"] for ref in item["evidence"]}]
    return {"answer": item["answer"], "explanation": item.get("explanation"), "sources": sources}


@app.post("/study/content/{content_id}/answer")
def answer(content_id: str, body: AnswerRequest, learner: User = Depends(student),
           session: Session = Depends(get_session)):
    document = study.owned_content(session, learner.id, content_id)
    item = study.owned_item(document, body.item_id) if document else None
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    if study.content_in_review(session, document):
        raise HTTPException(410, SOURCE_IN_REVIEW)
    try:
        attempt, created = study.record_answer(session, student_id=learner.id, content=document, item=item,
                                                answer=body.answer, request_id=body.request_id,
                                                self_assessment=body.self_assessment, pipeline=ai_service.StudyPipeline())
    except ValueError as error:
        if str(error) == "idempotency_conflict":
            raise HTTPException(409, "Reenvio incompatível") from None
        if str(error) == "flashcard_not_revealed":
            raise HTTPException(409, "Revele o verso do flashcard antes da autoavaliação") from None
        raise HTTPException(422, "Resposta inválida") from None
    response = study.public_answer(attempt)
    response["sources"] = [source for source in document.payload["sources"]
                           if source["chunk_id"] in {evidence["chunk_id"] for evidence in item["evidence"]}]
    if document.kind in ("multiple_choice", "true_false", "flashcards"):
        response["answer_key"] = item["answer"]
        response["explanation"] = item.get("explanation")
    return JSONResponse(response, status_code=201 if created else 200)


@app.get("/study/history")
def history(learner: User = Depends(student), session: Session = Depends(get_session)):
    return study.student_history(session, learner.id)


@app.get("/study/accuracy")
def accuracy(learner: User = Depends(student), session: Session = Depends(get_session)):
    return study.accuracy(session, learner.id)


@app.get("/study/plan")
def plan(learner: User = Depends(student), session: Session = Depends(get_session)):
    return study.review_plan(session, learner.id)


@app.get("/study/recommendations")
def recommendations(learner: User = Depends(student), session: Session = Depends(get_session)):
    return study.recommendations(session, learner.id)
