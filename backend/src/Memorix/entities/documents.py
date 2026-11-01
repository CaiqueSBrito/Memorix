from datetime import datetime

from sqlalchemy import BigInteger, CHAR, CheckConstraint, Computed, DateTime, ForeignKey, Identity, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("doc_sha256", name="uq_documents_doc_sha256"),
        CheckConstraint("source_type IN ('pdf', 'texto')", name="ck_documents_source_type"),
    )
    doc_id: Mapped[int] = mapped_column(primary_key=True)
    doc_sha256: Mapped[str] = mapped_column(CHAR(64))
    title: Mapped[str]
    source_type: Mapped[str]
    uploaded_by: Mapped[str] 
    extra: Mapped[dict[str, str]] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("doc_id", "position", name="uq_chunks_doc_id_position"),
        CheckConstraint("offset_end > offset_start", name="ck_chunks_offsets"),
        CheckConstraint("(embedding IS NULL) = (embedding_model IS NULL)", name="ck_chunks_embedding_pair"),
    )
    chunk_id: Mapped[str] = mapped_column(
        Text, Computed("doc_id::text || ':' || \"position\"::text", persisted=True), primary_key=True
    )
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"))
    position: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    offset_start: Mapped[int]
    offset_end: Mapped[int]
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(1024), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('public.pt_unaccent'::regconfig, text)", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped["Document"] = relationship(back_populates="chunks")


class ExcludedSpan(Base):
    """Canonical document offsets quarantined independently of chunk boundaries."""
    __tablename__ = "rag_excluded_spans"
    __table_args__ = (
        UniqueConstraint("doc_sha256", "offset_start", "offset_end", name="uq_rag_excluded_spans_exact"),
        CheckConstraint("offset_start >= 0 AND offset_end > offset_start", name="ck_rag_excluded_spans_offsets"),
        CheckConstraint("doc_sha256 ~ '^[0-9a-f]{64}$'", name="ck_rag_excluded_spans_sha"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_sha256: Mapped[str] = mapped_column(CHAR(64))
    offset_start: Mapped[int]
    offset_end: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
