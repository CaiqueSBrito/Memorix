from logging.config import fileConfig

from alembic import context

from backend.src.Memorix.entities import Base
from backend.src.Memorix.entities import documents  # noqa: F401 — registra as tabelas em Base.metadata
from backend.src.Memorix.providers.database import engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
