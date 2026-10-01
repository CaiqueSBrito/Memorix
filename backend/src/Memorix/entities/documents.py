from datetime import datetime

from sqlalchemy import CHAR, CheckConstraint, Computed, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
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
    uploaded_by: Mapped[str]  # id opaco do admin
    extra: Mapped[dict[str, str]] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("doc_id", "position", name="uq_chunks_doc_id_position"),
        CheckConstraint("offset_end > offset_start", name="ck_chunks_offsets"),
    )
    # Sempre "{doc_id}:{position}", calculado pelo banco. Ordene por `position`, nunca por `chunk_id`.
    chunk_id: Mapped[str] = mapped_column(
        Text, Computed("doc_id::text || ':' || \"position\"::text", persisted=True), primary_key=True
    )
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"))
    position: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    offset_start: Mapped[int]
    offset_end: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped["Document"] = relationship(back_populates="chunks")
