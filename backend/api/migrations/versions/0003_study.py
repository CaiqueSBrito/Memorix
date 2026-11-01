"""Student accounts, revocable sessions, invitations and study history.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("adult_confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('student', 'admin')", name="ck_study_users_role"),
    )
    op.create_table(
        "login_limits",
        sa.Column("key_hash", sa.Text(), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("study_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_study_sessions_user_id", "study_sessions", ["user_id"])
    op.create_table(
        "minor_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.Text(), unique=True, nullable=False),
        sa.Column("minor_email", sa.Text(), nullable=False),
        sa.Column("verified_by_id", sa.Integer(), sa.ForeignKey("study_users.id"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by_id", sa.Integer(), sa.ForeignKey("study_users.id"), unique=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "generated_content",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("study_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_generated_content_student_id", "generated_content", ["student_id"])
    op.create_table(
        "study_answers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("sequence", sa.Integer(), sa.Identity(), unique=True, nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("study_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_id", sa.Text(), sa.ForeignKey("generated_content.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("self_assessment", sa.Boolean()),
        sa.Column("correct", sa.Boolean()),
        sa.Column("score", sa.Float()),
        sa.Column("feedback", sa.Text()),
        sa.Column("uncertainty", sa.Text()),
        sa.Column("grading_trace_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.UniqueConstraint("student_id", "request_id", name="uq_study_answers_request"),
    )
    op.create_index("ix_study_answers_student_id", "study_answers", ["student_id"])
    for table in ("study_users", "login_limits", "study_sessions", "minor_invitations", "generated_content", "study_answers"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in ("study_answers", "generated_content", "minor_invitations", "study_sessions", "login_limits", "study_users"):
        op.drop_table(table)
