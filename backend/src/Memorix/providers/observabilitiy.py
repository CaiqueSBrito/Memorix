"""Rastro append-only; o caminho é resolvido em cada chamada."""

import hmac
import json
import logging
import os
from datetime import datetime, timezone
from hashlib import sha256
from math import ceil
from pathlib import Path

from ..config.config import ConfigIngestao

_QUERY_KEY = os.urandom(32)  # Ephemeral: trace_id correlates stages; hashes resist a topic dictionary.


def query_digest(value: str) -> str:
    return hmac.new(_QUERY_KEY, value.encode("utf-8"), sha256).hexdigest()


def _trace_file() -> Path:
    return Path(os.getenv("MEMORIX_RASTRO_PATH", ConfigIngestao.trace_path))


def record_trace(trace_id: str, stage: str, **fields) -> None:
    destination = _trace_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    entry = {"trace_id": trace_id, "etapa": stage, "timestamp": datetime.now(timezone.utc).isoformat(), **fields}
    handler = logging.FileHandler(destination, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        handler.emit(logging.makeLogRecord({"msg": json.dumps(entry, ensure_ascii=False), "levelno": logging.INFO}))
    finally:
        handler.close()


def _records():
    path = _trace_file()
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def read_trace(trace_id: str) -> list[dict]:
    """Retorna, em ordem de gravação, somente as etapas desta execução."""
    return [entry for entry in _records() if entry["trace_id"] == trace_id]


def summarize_traces() -> dict[str, dict]:
    """Agrega etapas do JSONL; p95 usa nearest-rank sobre durações observadas."""
    stages: dict[str, dict] = {}
    for entry in _records():
        stage = entry["etapa"]
        summary = stages.setdefault(stage, {"durations": [], "erros": 0})
        summary["durations"].append(entry["duracao_ms"])
        summary["erros"] += entry["status"] == "erro"
        if stage in ("geracao", "deduplicacao"):
            for field in ("tokens_entrada", "tokens_saida", "custo_estimado"):
                if field in entry:
                    summary[field] = summary.get(field, 0) + entry[field]

    for summary in stages.values():
        durations = sorted(summary.pop("durations"))
        total = len(durations)
        summary.update(total=total, taxa_erro=summary["erros"] / total,
                       p95_ms=durations[ceil(0.95 * total) - 1])
    return stages
