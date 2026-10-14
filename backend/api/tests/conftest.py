"""Fixtures compartilhadas de `backend/api/tests/`.

As fixtures de banco (`engine`, `migrated`, `conn`), o mascaramento de segredo
(`_db_url`, `_secrets`, `_no_secrets_in_errors`) e o atalho `_alembic` vieram de
`test_persistence.py` (tarefa 002) por decisão do humano em 2026-10-01 — "Mover
para o conftest.py, escopo session" —, que autorizou editar aquele teste já
aprovado. Motivo material: duas cópias da fixture `migrated` rodando
`alembic downgrade base` no teardown, contra o **mesmo** banco de dev, derrubam o
schema no meio do outro arquivo durante a suíte completa.

`test_persistence.py` consome daqui por import de módulo (`from conftest import ...`),
não por fixture: `_secrets` e `_no_secrets_in_errors` são usados como funções
(inclusive fora de teste, dentro de `_alembic`). Funciona com o importmode
`prepend` padrão do pytest — esta pasta não tem `__init__.py`, então ela entra no
`sys.path` e o próprio `conftest` é importável pelo nome.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = "backend/api/alembic.ini"  # relativo à raiz (cwd)

# Tokenizer do chunking `estrutural-v1`. A revisão é literal de 40 hex de propósito:
# `main` faria o teto de 400 tokens depender da data do download e mataria o
# determinismo prometido por I1. Fixado aqui, e não lido de `ConfigIngestao`, para
# que o teste não valide a implementação contra ela mesma.
TOKENIZER = "BAAI/bge-m3"
TOKENIZER_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"

_CACHE_COMMAND = (
    './venv/Scripts/python.exe -c "from huggingface_hub import snapshot_download; '
    f"snapshot_download('{TOKENIZER}', revision='{TOKENIZER_REVISION}', allow_patterns="
    "['tokenizer.json','tokenizer_config.json','sentencepiece.bpe.model',"
    "'special_tokens_map.json','config.json'])\""
)


def pytest_configure(config):
    config.addinivalue_line("markers", "banco: usa o banco de dev (migração + transação revertida)")
    config.addinivalue_line("markers", "hf: usa o tokenizer do bge-m3 do cache local do Hugging Face")


# ---------------------------------------------------------------- segredo


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


# ---------------------------------------------------------------- banco


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


def _test_session(conn):
    """Sessão ORM presa à conexão do teste: o commit da ingestão vira SAVEPOINT e some no rollback.

    Sem isto a ingestão abriria a própria conexão e não enxergaria a constraint
    temporária que o teste de I13 cria dentro da transação.
    """
    return Session(bind=conn, join_transaction_mode="create_savepoint")


# ---------------------------------------------------------------- ingestão (004)


@pytest.fixture(scope="session")
def tokenizer():
    """Tokenizer real do bge-m3, só do cache local. A suíte nunca baixa sozinha."""
    from transformers import AutoTokenizer

    try:
        return AutoTokenizer.from_pretrained(TOKENIZER, revision=TOKENIZER_REVISION, local_files_only=True)
    except OSError:
        pytest.skip(f"tokenizer {TOKENIZER}@{TOKENIZER_REVISION[:7]} fora do cache local. Popule com:\n{_CACHE_COMMAND}")


@pytest.fixture
def trace_file(tmp_path, monkeypatch):
    """Redireciona o JSONL de rastro para um arquivo descartável deste teste."""
    path = tmp_path / "rastro.jsonl"
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(path))
    return path
