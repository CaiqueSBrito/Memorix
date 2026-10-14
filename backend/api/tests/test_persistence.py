"""Tarefa 002 — persistência base (documents/chunks, sem vetor), teste primeiro.

Roda da raiz do repo contra o banco de dev do `.env` (autorizado, gate 1 resp. 03):
    ./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py -q

Tudo é observado de fora, com SQL cru via `text()`. Da implementação, só a URL do
banco é importada (`providers.database.DATABASE_URL`, montada a partir das variáveis
`DB_*` do `.env`). As fixtures de banco e o mascaramento de segredo moram em
`conftest.py` desde 2026-10-01 (decisão do humano, "Mover para o conftest.py, escopo
session"): a fixture de sessão roda `alembic upgrade head` no setup e `alembic
downgrade base` no teardown. As inserções ficam numa transação desfeita no fim de
cada teste. Nenhuma mensagem de erro exibe URL, senha ou host.
"""

import pytest
from conftest import ALEMBIC_INI, ROOT, _alembic, _db_url, _secrets
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

SHA_A = "a" * 64
SHA_B = "b" * 64


# ---------------------------------------------------------------- helpers


def _tables(c):
    return c.execute(text("select to_regclass('public.documents'), to_regclass('public.chunks')")).one()


def _column(c, table, column):
    return c.execute(
        text(
            "select data_type, character_maximum_length, is_nullable, is_generated"
            " from information_schema.columns"
            " where table_schema = 'public' and table_name = :t and column_name = :col"
        ),
        {"t": table, "col": column},
    ).one_or_none()


def _unique_column_sets(c, table):
    rows = c.execute(
        text(
            "select array_agg(a.attname::text order by a.attname) from pg_index i"
            " join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
            " where i.indrelid = cast(:t as regclass) and i.indisunique group by i.indexrelid"
        ),
        {"t": f"public.{table}"},
    ).scalars()
    return [set(r) for r in rows]


def _insert_doc(c, sha, source_type="pdf"):
    return c.execute(
        text(
            "insert into documents (title, source_type, uploaded_by, doc_sha256)"
            " values ('Apostila sintética', :st, 'admin-opaco-teste', :sha) returning doc_id"
        ),
        {"st": source_type, "sha": sha},
    ).scalar_one()


def _chunk_id_generated(c):
    return _column(c, "chunks", "chunk_id")[3] == "ALWAYS"


def _insert_chunk(c, doc_id, position, start=0, end=10, chunk_id=None):
    """Grava chunk; `chunk_id` só vai no INSERT se a coluna não for GENERATED
    (ou se o teste forçar um valor)."""
    cols = "doc_id, position, text, offset_start, offset_end"
    vals = ":d, :p, 'trecho sintético', :s, :e"
    params = {"d": doc_id, "p": position, "s": start, "e": end}
    if chunk_id is None and not _chunk_id_generated(c):
        chunk_id = f"{doc_id}:{position}"
    if chunk_id is not None:
        cols, vals, params["cid"] = cols + ", chunk_id", vals + ", :cid", chunk_id
    c.execute(text(f"insert into chunks ({cols}) values ({vals})"), params)


def _fails(c, fn, exc=IntegrityError):
    """Executa `fn` num savepoint e exige que o banco recuse com `exc`."""
    sp = c.begin_nested()
    with pytest.raises(exc):
        fn()
    sp.rollback()


# ---------------------------------------------------------------- critérios


def test_upgrade_head_creates_documents_and_chunks(conn):
    docs, chunks = _tables(conn)
    assert docs == "documents"
    assert chunks == "chunks"


def test_downgrade_removes_tables_and_upgrade_recreates_them(engine, migrated):
    _alembic("downgrade")
    with engine.connect() as c:
        assert _tables(c) == (None, None)
    _alembic("upgrade")
    with engine.connect() as c:
        assert _tables(c) == ("documents", "chunks")


def test_doc_sha256_char64_not_null_unique(conn):
    data_type, length, nullable, _ = _column(conn, "documents", "doc_sha256")
    assert (data_type, length, nullable) == ("character", 64, "NO")
    assert {"doc_sha256"} in _unique_column_sets(conn, "documents")

    _insert_doc(conn, SHA_A)
    _fails(conn, lambda: _insert_doc(conn, SHA_A))  # mesmo hash duas vezes
    _fails(conn, lambda: _insert_doc(conn, None))  # NOT NULL


def test_source_type_accepts_only_pdf_and_text(conn):
    _insert_doc(conn, SHA_A, "pdf")
    _insert_doc(conn, SHA_B, "texto")
    for bad in ("docx", "PDF", "", "txt"):
        _fails(conn, lambda bad=bad: _insert_doc(conn, "c" * 64, bad))


def test_chunk_id_primary_key_matches_doc_id_and_position(conn):
    pk = conn.execute(
        text(
            "select array_agg(a.attname::text) from pg_index i"
            " join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
            " where i.indrelid = 'public.chunks'::regclass and i.indisprimary"
        )
    ).scalar_one()
    assert pk == ["chunk_id"]
    assert _column(conn, "chunks", "chunk_id")[0] in ("text", "character varying")

    doc = _insert_doc(conn, SHA_A)
    _insert_chunk(conn, doc, 3)
    read = conn.execute(text("select chunk_id from chunks where doc_id = :d and position = 3"), {"d": doc})
    assert read.scalar_one() == f"{doc}:3"

    # Divergente: o banco recusa (CHECK/GENERATED) ou não deixa o valor divergente ficar.
    sp = conn.begin_nested()
    try:
        _insert_chunk(conn, doc, 4, chunk_id=f"{doc}:999")
        sp.commit()
    except DBAPIError:
        sp.rollback()
    ids = conn.execute(text("select chunk_id, position from chunks where doc_id = :d"), {"d": doc}).all()
    assert all(cid == f"{doc}:{position}" for cid, position in ids)

    sp = conn.begin_nested()
    try:
        conn.execute(text("update chunks set chunk_id = 'divergente:1' where doc_id = :d"), {"d": doc})
        sp.commit()
    except DBAPIError:
        sp.rollback()
    ids = conn.execute(text("select chunk_id, position from chunks where doc_id = :d"), {"d": doc}).all()
    assert ids and all(cid == f"{doc}:{position}" for cid, position in ids)


def test_chunks_unique_doc_id_position(conn):
    assert {"doc_id", "position"} in _unique_column_sets(conn, "chunks")

    doc_a = _insert_doc(conn, SHA_A)
    doc_b = _insert_doc(conn, SHA_B)
    _insert_chunk(conn, doc_a, 0)
    _insert_chunk(conn, doc_b, 0)  # mesma posição em outro doc: ok
    _fails(conn, lambda: _insert_chunk(conn, doc_a, 0), DBAPIError)


def test_offsets_are_required_and_end_exceeds_start(conn):
    for col in ("offset_start", "offset_end"):
        assert _column(conn, "chunks", col)[2] == "NO"

    doc = _insert_doc(conn, SHA_A)
    _insert_chunk(conn, doc, 0, start=0, end=1)
    _fails(conn, lambda: _insert_chunk(conn, doc, 1, start=10, end=5))  # invertido
    _fails(conn, lambda: _insert_chunk(conn, doc, 2, start=7, end=7))  # vazio
    _fails(conn, lambda: _insert_chunk(conn, doc, 3, start=None, end=5))
    _fails(conn, lambda: _insert_chunk(conn, doc, 4, start=0, end=None))


def test_chunks_have_no_embedding_columns(conn):
    cols = set(
        conn.execute(
            text("select column_name from information_schema.columns where table_schema = 'public' and table_name = 'chunks'")
        ).scalars()
    )
    assert {"chunk_id", "doc_id", "position", "text", "offset_start", "offset_end"} <= cols
    assert not {"embedding", "embedding_model"} & cols


def test_deleting_document_cascades_to_chunks(conn):
    doc = _insert_doc(conn, SHA_A)
    keep = _insert_doc(conn, SHA_B)
    _insert_chunk(conn, doc, 0)
    _insert_chunk(conn, doc, 1, start=10, end=20)
    _insert_chunk(conn, keep, 0)
    conn.execute(text("delete from documents where doc_id = :d"), {"d": doc})
    count = "select count(*) from chunks where doc_id = :d"
    assert conn.execute(text(count), {"d": doc}).scalar_one() == 0
    assert conn.execute(text(count), {"d": keep}).scalar_one() == 1


def test_rls_enabled_without_policies(conn):
    rls = dict(
        conn.execute(
            text(
                "select relname::text, relrowsecurity from pg_class"
                " where oid in ('public.documents'::regclass, 'public.chunks'::regclass)"
            )
        ).all()
    )
    assert rls == {"documents": True, "chunks": True}
    policies = conn.execute(
        text("select count(*) from pg_policies where schemaname = 'public' and tablename in ('documents', 'chunks')")
    ).scalar_one()
    assert policies == 0


def test_database_url_comes_from_env_without_hardcoded_credentials():
    """Sem banco: os arquivos da implementação existem e nenhum contém URL/senha/host."""
    assert _db_url(), "URL do banco ausente no .env"
    required = [
        ROOT / ALEMBIC_INI,
        ROOT / "backend/api/migrations/env.py",
        ROOT / "backend/src/Memorix/providers/database.py",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    assert missing == [], "arquivos da implementação ausentes"
    assert list((ROOT / "backend/api/migrations/versions").glob("*.py")), "nenhuma migração em versions/"

    scanned = required + [
        p
        for d in ("backend/api/migrations", "backend/api/tests")
        for p in (ROOT / d).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    secrets = _secrets()
    leaks = sorted(
        {str(p.relative_to(ROOT)) for p in scanned if any(s in p.read_text(errors="ignore") for s in secrets)}
    )
    assert leaks == [], "credencial do banco encontrada nestes arquivos"
