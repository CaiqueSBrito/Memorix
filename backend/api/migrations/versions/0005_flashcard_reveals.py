"""Persist delivered flashcard backs before students rate them.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flashcard_reveals",
        sa.Column("content_id", sa.Text(), sa.ForeignKey("generated_content.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_id", sa.Text(), primary_key=True),
    )
    op.execute("ALTER TABLE flashcard_reveals ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("flashcard_reveals")
