"""Tarefa 002 — persistência base (documents/chunks, sem vetor), teste primeiro.

Roda da raiz do repo contra o banco de dev do `.env` (autorizado, gate 1 resp. 03):
    ./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py -q

Tudo é observado de fora, com SQL cru via `text()`. Da implementação, só a URL do
banco é importada (`providers.database.DATABASE_URL`, montada a partir das variáveis
`DB_*` do `.env`). A fixture de sessão roda `alembic upgrade head` no setup e
`alembic downgrade base` no teardown. As inserções ficam numa transação desfeita no
fim de cada teste. Nenhuma mensagem de erro exibe URL, senha ou host.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = "backend/api/alembic.ini"  # relativo à raiz (cwd)
SHA_A = "a" * 64
SHA_B = "b" * 64


def _db_url():
    """URL do banco vinda da implementação (lê o `.env`); import tardio para o teste coletar sem ela."""
    from backend.src.Memorix.providers.database import DATABASE_URL

    return DATABASE_URL


def _secrets():
    u = _db_url()
    return [s for s in (u.render_as_string(hide_password=False), u.password, u.host, os.getenv("DB_PASSWORD")) if s]


@contextmanager
def _no_secrets_in_errors():
    """Reemite qualquer erro com URL/senha/host mascarados (critério: nada em log)."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 — só re-embala a mensagem
        msg = f"{type(e).__name__}: {e}"
        for s in _secrets():
            msg = msg.replace(s, "***")
        raise RuntimeError(msg) from None


def _alembic(action):
    cfg = Config(ALEMBIC_INI)
    with _no_secrets_in_errors():
        if action == "upgrade":
            command.upgrade(cfg, "head")
        else:
            command.downgrade(cfg, "base")


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def engine():
    if not (ROOT / ALEMBIC_INI).is_file():
        pytest.fail(f"{ALEMBIC_INI} não existe: migração 0001 ainda não implementada")
    assert _db_url(), "URL do banco ausente no .env"
    eng = create_engine(_db_url(), pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def migrated(engine):
    old_cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        with _no_secrets_in_errors(), engine.connect() as c:
            docs, chunks, ver = c.execute(
                text(
                    "select to_regclass('public.documents'), to_regclass('public.chunks'),"
                    " to_regclass('public.alembic_version')"
                )
            ).one()
        if (docs or chunks) and not ver:
            pytest.fail("documents/chunks já existem fora do Alembic; nada foi apagado")
        _alembic("upgrade")
        yield
        _alembic("downgrade")
    finally:
        os.chdir(old_cwd)


@pytest.fixture
def conn(engine, migrated):
    """Conexão numa transação desfeita no fim: nada inserido persiste."""
    with engine.connect() as c:
        tx = c.begin()
        try:
            yield c
        finally:
            tx.rollback()


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


def test_upgrade_head_cria_documents_e_chunks(conn):
    docs, chunks = _tables(conn)
    assert docs == "documents"
    assert chunks == "chunks"


def test_downgrade_base_remove_tabelas_e_upgrade_roda_de_novo(engine, migrated):
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


def test_source_type_aceita_so_pdf_e_texto(conn):
    _insert_doc(conn, SHA_A, "pdf")
    _insert_doc(conn, SHA_B, "texto")
    for bad in ("docx", "PDF", "", "txt"):
        _fails(conn, lambda bad=bad: _insert_doc(conn, "c" * 64, bad))


def test_chunk_id_textual_pk_igual_doc_id_dois_pontos_position(conn):
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
    assert all(cid == f"{doc}:{pos}" for cid, pos in ids)

    sp = conn.begin_nested()
    try:
        conn.execute(text("update chunks set chunk_id = 'divergente:1' where doc_id = :d"), {"d": doc})
        sp.commit()
    except DBAPIError:
        sp.rollback()
    ids = conn.execute(text("select chunk_id, position from chunks where doc_id = :d"), {"d": doc}).all()
    assert ids and all(cid == f"{doc}:{pos}" for cid, pos in ids)


def test_chunks_unique_doc_id_position(conn):
    assert {"doc_id", "position"} in _unique_column_sets(conn, "chunks")

    doc_a = _insert_doc(conn, SHA_A)
    doc_b = _insert_doc(conn, SHA_B)
    _insert_chunk(conn, doc_a, 0)
    _insert_chunk(conn, doc_b, 0)  # mesma posição em outro doc: ok
    _fails(conn, lambda: _insert_chunk(conn, doc_a, 0), DBAPIError)


def test_offsets_not_null_e_end_maior_que_start(conn):
    for col in ("offset_start", "offset_end"):
        assert _column(conn, "chunks", col)[2] == "NO"

    doc = _insert_doc(conn, SHA_A)
    _insert_chunk(conn, doc, 0, start=0, end=1)
    _fails(conn, lambda: _insert_chunk(conn, doc, 1, start=10, end=5))  # invertido
    _fails(conn, lambda: _insert_chunk(conn, doc, 2, start=7, end=7))  # vazio
    _fails(conn, lambda: _insert_chunk(conn, doc, 3, start=None, end=5))
    _fails(conn, lambda: _insert_chunk(conn, doc, 4, start=0, end=None))


def test_chunks_sem_embedding_nem_embedding_model(conn):
    cols = set(
        conn.execute(
            text("select column_name from information_schema.columns where table_schema = 'public' and table_name = 'chunks'")
        ).scalars()
    )
    assert {"chunk_id", "doc_id", "position", "text", "offset_start", "offset_end"} <= cols
    assert not {"embedding", "embedding_model"} & cols


def test_apagar_document_apaga_chunks_on_delete_cascade(conn):
    doc = _insert_doc(conn, SHA_A)
    keep = _insert_doc(conn, SHA_B)
    _insert_chunk(conn, doc, 0)
    _insert_chunk(conn, doc, 1, start=10, end=20)
    _insert_chunk(conn, keep, 0)
    conn.execute(text("delete from documents where doc_id = :d"), {"d": doc})
    count = "select count(*) from chunks where doc_id = :d"
    assert conn.execute(text(count), {"d": doc}).scalar_one() == 0
    assert conn.execute(text(count), {"d": keep}).scalar_one() == 1


def test_rls_habilitada_sem_policies(conn):
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


def test_url_do_banco_so_no_env_sem_credencial_em_codigo():
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
