"""Contrato público de consulta dos rastros da ingestão e de etapas futuras."""

import pytest

from backend.src.Memorix.providers.observabilitiy import record_trace, read_trace, summarize_traces


def test_trace_lookup_and_stage_metrics(tmp_path, monkeypatch):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(trace_file))
    for duration in range(1, 21):
        record_trace("first", "chunking", status="erro" if duration == 20 else "ok",
                     erro="ValueError" if duration == 20 else None, duracao_ms=duration)
    record_trace("second", "geracao", status="ok", duracao_ms=30,
                 tokens_entrada=11, tokens_saida=7, custo_estimado=0.03)
    record_trace("third", "geracao", status="erro", erro="TimeoutError", duracao_ms=40)

    records = read_trace("first")
    assert len(records) == 20 and {row["trace_id"] for row in records} == {"first"}
    assert [row["duracao_ms"] for row in records] == list(range(1, 21))
    assert read_trace("missing") == []

    metrics = summarize_traces()
    assert metrics["chunking"] == {"total": 20, "erros": 1, "taxa_erro": 0.05, "p95_ms": 19}
    assert metrics["geracao"] == {"total": 2, "erros": 1, "taxa_erro": 0.5, "p95_ms": 40,
                                   "tokens_entrada": 11, "tokens_saida": 7, "custo_estimado": 0.03}


def test_failed_chunking_traces_both_stages(tmp_path, monkeypatch):
    from backend.src.Memorix.ingestion import ingest

    monkeypatch.setenv("MEMORIX_RASTRO_PATH", str(tmp_path / "trace.jsonl"))

    def fail_chunking(_):
        raise ValueError("conteúdo privado")

    monkeypatch.setattr(ingest, "chunking", fail_chunking)
    with pytest.raises(ValueError, match="conteúdo privado"):
        ingest.ingest_document("conteúdo privado", title="Exemplo", source_type="texto",
                               uploaded_by="admin", source="exemplo.txt", trace_id="failed")

    records = read_trace("failed")
    assert {row["etapa"] for row in records} == {"chunking", "ingestao"}
    assert all(row["status"] == "erro" and row["erro"] == "ValueError" for row in records)
    assert "conteúdo privado" not in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
