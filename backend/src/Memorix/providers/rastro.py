"""Rastro append-only; o caminho é resolvido em cada chamada."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..config.config import ConfigIngestao


def registrar(trace_id: str, etapa: str, **campos) -> None:
    destino = Path(os.getenv("MEMORIX_RASTRO_PATH", ConfigIngestao.rastro_path))
    destino.parent.mkdir(parents=True, exist_ok=True)
    registro = {"trace_id": trace_id, "etapa": etapa, "timestamp": datetime.now(timezone.utc).isoformat(), **campos}
    handler = logging.FileHandler(destino, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        handler.emit(logging.makeLogRecord({"msg": json.dumps(registro, ensure_ascii=False), "levelno": logging.INFO}))
    finally:
        handler.close()
