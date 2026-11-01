"""Quarantine canonical spans independently of chunk and vector lifecycle.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_excluded_spans",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("doc_sha256", sa.CHAR(64), nullable=False),
        sa.Column("offset_start", sa.Integer(), nullable=False),
        sa.Column("offset_end", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("doc_sha256 ~ '^[0-9a-f]{64}$'", name="ck_rag_excluded_spans_sha"),
        sa.CheckConstraint("offset_start >= 0 AND offset_end > offset_start", name="ck_rag_excluded_spans_offsets"),
        sa.UniqueConstraint("doc_sha256", "offset_start", "offset_end", name="uq_rag_excluded_spans_exact"),
    )
    op.create_index("ix_rag_excluded_spans_sha_offsets", "rag_excluded_spans", ["doc_sha256", "offset_start", "offset_end"])
    op.execute("ALTER TABLE rag_excluded_spans ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("rag_excluded_spans")
