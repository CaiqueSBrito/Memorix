"""Contrato observável da 005: PDF selecionável, OCR português e ingestão atômica."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest
from conftest import ROOT, _test_session
from sqlalchemy import text

from backend.src.Memorix.ingestion.canonical import canonicalize, doc_sha256

try:
    from backend.src.Memorix.ingestion.pdf import extract_pdf, ingest_pdf
except ModuleNotFoundError as error:
    _missing_import = (str(error), error.name)

    def _missing_module(*_args, **_kwargs):
        raise ModuleNotFoundError(_missing_import[0], name=_missing_import[1]) from None

    extract_pdf = ingest_pdf = _missing_module


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pdf"
NATIVE_TEXT = ["A Terra gira ao redor do Sol.", "A água sustenta a vida na Terra."]
IMAGE_TEXT = [
    "A fotossíntese converte a luz solar em energia química para as plantas.",
    "A água líquida é essencial para a vida e regula a temperatura do planeta.",
]


def _fixture_source(fixture_name):
    return (FIXTURES / fixture_name).relative_to(ROOT)


def _ingest_fixture(conn, fixture_name, *, doc_id=None):
    return ingest_pdf(
        _fixture_source(fixture_name), title="Apostila PDF", uploaded_by="admin-opaco-teste",
        doc_id=doc_id, session=_test_session(conn),
    )


def _trace_records(path):
    assert path.is_file(), "PDF não deixou rastro"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _words(content):
    return re.findall(r"\w+", content.casefold())


@pytest.mark.parametrize("fixture_name", ("selecionavel.pdf", "digitalizado.pdf", "misto.pdf"))
def test_pdf_extracts_pages_in_order_without_mixing_text(fixture_name):
    expected = NATIVE_TEXT if fixture_name == "selecionavel.pdf" else IMAGE_TEXT if fixture_name == "digitalizado.pdf" else [NATIVE_TEXT[0], IMAGE_TEXT[1]]
    pages = extract_pdf(_fixture_source(fixture_name)).split("\n\n")
    assert len(pages) == 2
    for reference, extracted in zip(expected, pages):
        assert SequenceMatcher(None, _words(reference), _words(extracted)).ratio() >= 0.90
    assert pages[0] != pages[1]


@pytest.mark.parametrize("fixture_name", ("invalido.pdf", "protegido.pdf"))
def test_unreadable_pdf_fails_without_invented_text(fixture_name):
    with pytest.raises(ValueError):
        extract_pdf(_fixture_source(fixture_name))


@pytest.mark.banco
def test_selectable_pdf_persists_offsets_and_source(conn, trace_file):
    result = _ingest_fixture(conn, "selecionavel.pdf")
    document = conn.execute(
        text("select source_type, doc_sha256, metadata from documents where doc_id=:id"),
        {"id": result.doc_id},
    ).one()
    assert document.source_type == "pdf"
    assert document.metadata["fonte"] == _fixture_source("selecionavel.pdf").as_posix()
    assert document.doc_sha256 == doc_sha256(canonicalize(extract_pdf(_fixture_source("selecionavel.pdf"))))
    chunks = conn.execute(
        text("select chunk_id, offset_start, offset_end, text from chunks where doc_id=:id order by position"),
        {"id": result.doc_id},
    ).all()
    assert chunks
    canonical_text = canonicalize(extract_pdf(_fixture_source("selecionavel.pdf")))
    assert all(canonical_text[a:b] == chunk_text for _, a, b, chunk_text in chunks)
    rows = _trace_records(trace_file)
    assert {r["etapa"] for r in rows} == {"extracao", "ingestao", "chunking"}
    assert len({r["trace_id"] for r in rows}) == 1
    assert all(r["status"] == "ok" for r in rows)
    assert {c[0] for c in chunks} == {c["chunk_id"] for r in rows if r["etapa"] == "chunking" for c in r["chunks"]}
    assert all("A Terra gira" not in json.dumps(r, ensure_ascii=False) for r in rows)
    assert any("pdf" in str(r.get("extrator", "")).lower() for r in rows if r["etapa"] == "ingestao")


@pytest.mark.banco
def test_scanned_pdf_records_ocr_without_text_in_trace(conn, trace_file):
    result = _ingest_fixture(conn, "digitalizado.pdf")
    assert result.doc_id
    rows = _trace_records(trace_file)
    extraction = next(r for r in rows if r["etapa"] == "extracao")
    methods = extraction["paginas"]
    assert len(methods) == 2
    assert all(p["metodo"] == "ocr" and p["idioma"] == "por" and p["motor"] for p in methods)
    assert "fotossíntese" not in trace_file.read_text(encoding="utf-8")
    assert conn.execute(text("select count(*) from chunks where doc_id=:id"), {"id": result.doc_id}).scalar_one() > 0


@pytest.mark.banco
def test_mixed_pdf_uses_ocr_only_for_image_page(conn, trace_file):
    _ingest_fixture(conn, "misto.pdf")
    extraction = next(r for r in _trace_records(trace_file) if r["etapa"] == "extracao")
    assert [p["metodo"] for p in extraction["paginas"]] == ["texto", "ocr"]


@pytest.mark.banco
def test_identical_pdf_reingestion_is_noop_and_changed_pdf_replaces_spans(conn, trace_file):
    a = _ingest_fixture(conn, "selecionavel.pdf")
    query = text("select chunk_id, offset_start, offset_end, text, ctid::text from chunks where doc_id=:id order by position")
    before = conn.execute(query, {"id": a.doc_id}).all()
    again = _ingest_fixture(conn, "selecionavel.pdf", doc_id=a.doc_id)
    assert again.status == "no_changes"
    assert conn.execute(query, {"id": a.doc_id}).all() == before
    b = _ingest_fixture(conn, "alterado.pdf", doc_id=a.doc_id)
    assert b.status == "replaced"
    assert b.doc_sha256 != a.doc_sha256
    assert conn.execute(query, {"id": a.doc_id}).all() != before


@pytest.mark.banco
def test_invalid_pdf_preserves_chunks_and_records_error(conn, trace_file):
    previous = _ingest_fixture(conn, "selecionavel.pdf")
    query = text("select chunk_id, text from chunks where doc_id=:id order by position")
    before = conn.execute(query, {"id": previous.doc_id}).all()
    count = len(_trace_records(trace_file))
    with pytest.raises(ValueError):
        _ingest_fixture(conn, "invalido.pdf", doc_id=previous.doc_id)
    assert conn.execute(query, {"id": previous.doc_id}).all() == before
    new_entries = _trace_records(trace_file)[count:]
    assert len(new_entries) == 1 and new_entries[0]["etapa"] == "extracao"
    assert new_entries[0]["status"] == "erro" and new_entries[0]["erro"]
    assert new_entries[0]["trace_id"] != _trace_records(trace_file)[0]["trace_id"]
