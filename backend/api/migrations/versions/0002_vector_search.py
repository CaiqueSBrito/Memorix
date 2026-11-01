"""Add dense embeddings and accent-insensitive Portuguese full-text search.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions")
    op.execute("CREATE TEXT SEARCH DICTIONARY public.pt_stop (TEMPLATE = pg_catalog.simple, STOPWORDS = portuguese, ACCEPT = false)")
    op.execute("CREATE TEXT SEARCH CONFIGURATION public.pt_unaccent (COPY = pg_catalog.portuguese)")
    op.execute("ALTER TEXT SEARCH CONFIGURATION public.pt_unaccent ALTER MAPPING FOR asciiword, asciihword, hword_asciipart, word, hword, hword_part WITH public.pt_stop, extensions.unaccent, pg_catalog.portuguese_stem")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding extensions.vector(1024)")
    op.add_column("chunks", sa.Column("embedding_model", sa.Text(), nullable=True))
    op.create_check_constraint("ck_chunks_embedding_pair", "chunks", "(embedding IS NULL) = (embedding_model IS NULL)")
    op.add_column("chunks", sa.Column("tsv", TSVECTOR(), sa.Computed("to_tsvector('public.pt_unaccent'::regconfig, text)", persisted=True)))
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_column("chunks", "tsv")
    op.drop_constraint("ck_chunks_embedding_pair", "chunks", type_="check")
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "embedding")
    op.execute("DROP TEXT SEARCH CONFIGURATION public.pt_unaccent")
    op.execute("DROP TEXT SEARCH DICTIONARY public.pt_stop")
    # Extensions are shared resources and may predate this migration; never drop them.
