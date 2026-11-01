"""Account, revocable session and student-owned study records."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class User(Base):
    __tablename__ = "study_users"
    __table_args__ = (CheckConstraint("role IN ('student', 'admin')", name="ck_study_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="student")
    adult_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginLimit(Base):
    __tablename__ = "login_limits"

    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("study_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MinorInvitation(Base):
    __tablename__ = "minor_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    minor_email: Mapped[str] = mapped_column(Text)
    verified_by_id: Mapped[int] = mapped_column(ForeignKey("study_users.id"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_by_id: Mapped[int | None] = mapped_column(ForeignKey("study_users.id"), unique=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedContent(Base):
    __tablename__ = "generated_content"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("study_users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    trace_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlashcardReveal(Base):
    __tablename__ = "flashcard_reveals"

    content_id: Mapped[str] = mapped_column(ForeignKey("generated_content.id", ondelete="CASCADE"), primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)


class StudyAnswer(Base):
    __tablename__ = "study_answers"
    __table_args__ = (UniqueConstraint("student_id", "request_id", name="uq_study_answers_request"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("study_users.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("generated_content.id", ondelete="CASCADE"))
    item_id: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    self_assessment: Mapped[bool | None] = mapped_column(Boolean)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None]
    feedback: Mapped[str | None] = mapped_column(Text)
    uncertainty: Mapped[str | None] = mapped_column(Text)
    grading_trace_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("clock_timestamp()"))
