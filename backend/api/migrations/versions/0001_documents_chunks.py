"""documents e chunks (sem vetor), com RLS sem policies

Revision ID: 0001
Revises:
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.Integer(), primary_key=True),
        sa.Column("doc_sha256", sa.CHAR(64), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("doc_sha256", name="uq_documents_doc_sha256"),
        sa.CheckConstraint("source_type IN ('pdf', 'texto')", name="ck_documents_source_type"),
    )
    op.create_table(
        "chunks",
        sa.Column(
            "chunk_id",
            sa.Text(),
            sa.Computed("doc_id::text || ':' || \"position\"::text", persisted=True),
            primary_key=True,
        ),
        sa.Column("doc_id", sa.Integer(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("offset_start", sa.Integer(), nullable=False),
        sa.Column("offset_end", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("doc_id", "position", name="uq_chunks_doc_id_position"),
        sa.CheckConstraint("offset_end > offset_start", name="ck_chunks_offsets"),
    )
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chunks ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
