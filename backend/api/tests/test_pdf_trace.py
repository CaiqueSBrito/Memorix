"""O upload propaga o trace_id mesmo quando a extração do PDF falha."""

import pytest

from backend.src.Memorix.ingestion.pdf import ingest_pdf
from backend.src.Memorix.providers.observabilitiy import read_trace


def test_pdf_extraction_failure_keeps_request_trace_id(trace_file):
    with pytest.raises(ValueError, match="PDF inválido ou ilegível"):
        ingest_pdf("absent-upload.pdf", title="Material", uploaded_by="admin-test", trace_id="upload-trace")
    events = read_trace("upload-trace")
    assert [(event["etapa"], event["status"], event["erro"]) for event in events] == [
        ("extracao", "erro", "ValueError"),
    ]
