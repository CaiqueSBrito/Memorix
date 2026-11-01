"""Engine e sessão do Postgres (Supabase, Supavisor em modo session).

A URL usa as variáveis do arquivo selecionado por `MEMORIX_ENV_FILE` (ou `.env`).
`DB_SSLMODE` mantém TLS obrigatório por padrão. Nunca registre `DATABASE_URL`.
"""

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.config.config import ConfigDB

_missing = [n for n in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME") if not getattr(ConfigDB, n)]
if _missing:
    raise RuntimeError(f"variáveis do banco ausentes no .env: {_missing}")

DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=ConfigDB.DB_USER,
    password=ConfigDB.DB_PASSWORD,
    host=ConfigDB.DB_HOST,
    port=int(ConfigDB.DB_PORT),
    database=ConfigDB.DB_NAME,
    query={"sslmode": ConfigDB.DB_SSLMODE},
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
