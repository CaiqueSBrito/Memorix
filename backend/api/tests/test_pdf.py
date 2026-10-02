"""Contrato observável da 005: PDF selecionável, OCR português e ingestão atômica."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest
from conftest import ROOT, _sessao
from sqlalchemy import text

from backend.src.Memorix.ingestion.canonical import canonicalizar, doc_sha256

try:
    from backend.src.Memorix.ingestion.pdf import extrair_pdf, ingerir_pdf
except ModuleNotFoundError as erro:
    _faltando = (str(erro), erro.name)

    def _ausente(*_args, **_kwargs):
        raise ModuleNotFoundError(_faltando[0], name=_faltando[1]) from None

    extrair_pdf = ingerir_pdf = _ausente


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pdf"
NATIVO = ["A Terra gira ao redor do Sol.", "A água sustenta a vida na Terra."]
IMAGEM = [
    "A fotossíntese converte a luz solar em energia química para as plantas.",
    "A água líquida é essencial para a vida e regula a temperatura do planeta.",
]


def _fonte(nome):
    return (FIXTURES / nome).relative_to(ROOT)


def _ingerir(conn, nome, *, doc_id=None):
    return ingerir_pdf(
        _fonte(nome), title="Apostila PDF", uploaded_by="admin-opaco-teste",
        doc_id=doc_id, session=_sessao(conn),
    )


def _registros(caminho):
    assert caminho.is_file(), "PDF não deixou rastro"
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def _palavras(texto):
    return re.findall(r"\w+", texto.casefold())


@pytest.mark.parametrize("nome", ("selecionavel.pdf", "digitalizado.pdf", "misto.pdf"))
def test_pdf_extrai_paginas_na_ordem_sem_misturar_texto(nome):
    esperado = NATIVO if nome == "selecionavel.pdf" else IMAGEM if nome == "digitalizado.pdf" else [NATIVO[0], IMAGEM[1]]
    paginas = extrair_pdf(_fonte(nome)).split("\n\n")
    assert len(paginas) == 2
    for referencia, extraido in zip(esperado, paginas):
        assert SequenceMatcher(None, _palavras(referencia), _palavras(extraido)).ratio() >= 0.90
    assert paginas[0] != paginas[1]


@pytest.mark.parametrize("nome", ("invalido.pdf", "protegido.pdf"))
def test_pdf_ilegivel_falha_sem_inventar_texto(nome):
    with pytest.raises(ValueError):
        extrair_pdf(_fonte(nome))


@pytest.mark.banco
def test_pdf_selecionavel_chega_ao_banco_com_offsets_e_origem(conn, rastro):
    resultado = _ingerir(conn, "selecionavel.pdf")
    documento = conn.execute(
        text("select source_type, doc_sha256, metadata from documents where doc_id=:id"),
        {"id": resultado.doc_id},
    ).one()
    assert documento.source_type == "pdf"
    assert documento.metadata["fonte"] == _fonte("selecionavel.pdf").as_posix()
    assert documento.doc_sha256 == doc_sha256(canonicalizar(extrair_pdf(_fonte("selecionavel.pdf"))))
    chunks = conn.execute(
        text("select chunk_id, offset_start, offset_end, text from chunks where doc_id=:id order by position"),
        {"id": resultado.doc_id},
    ).all()
    assert chunks
    canonico = canonicalizar(extrair_pdf(_fonte("selecionavel.pdf")))
    assert all(canonico[a:b] == trecho for _, a, b, trecho in chunks)
    linhas = _registros(rastro)
    assert {r["etapa"] for r in linhas} == {"extracao", "ingestao", "chunking"}
    assert len({r["trace_id"] for r in linhas}) == 1
    assert all(r["status"] == "ok" for r in linhas)
    assert {c[0] for c in chunks} == {c["chunk_id"] for r in linhas if r["etapa"] == "chunking" for c in r["chunks"]}
    assert all("A Terra gira" not in json.dumps(r, ensure_ascii=False) for r in linhas)
    assert any("pdf" in str(r.get("extrator", "")).lower() for r in linhas if r["etapa"] == "ingestao")


@pytest.mark.banco
def test_pdf_digitalizado_registra_ocr_por_pagina_sem_texto_no_rastro(conn, rastro):
    resultado = _ingerir(conn, "digitalizado.pdf")
    assert resultado.doc_id
    linhas = _registros(rastro)
    extracao = next(r for r in linhas if r["etapa"] == "extracao")
    metodos = extracao["paginas"]
    assert len(metodos) == 2
    assert all(p["metodo"] == "ocr" and p["idioma"] == "por" and p["motor"] for p in metodos)
    assert "fotossíntese" not in rastro.read_text(encoding="utf-8")
    assert conn.execute(text("select count(*) from chunks where doc_id=:id"), {"id": resultado.doc_id}).scalar_one() > 0


@pytest.mark.banco
def test_pdf_misto_faz_ocr_somente_na_pagina_sem_camada_textual(conn, rastro):
    _ingerir(conn, "misto.pdf")
    extracao = next(r for r in _registros(rastro) if r["etapa"] == "extracao")
    assert [p["metodo"] for p in extracao["paginas"]] == ["texto", "ocr"]


@pytest.mark.banco
def test_reingerir_pdf_identico_e_noop_e_outro_pdf_substitui_spans(conn, rastro):
    a = _ingerir(conn, "selecionavel.pdf")
    consulta = text("select chunk_id, offset_start, offset_end, text, ctid::text from chunks where doc_id=:id order by position")
    antes = conn.execute(consulta, {"id": a.doc_id}).all()
    novamente = _ingerir(conn, "selecionavel.pdf", doc_id=a.doc_id)
    assert novamente.resultado == "sem_mudanca"
    assert conn.execute(consulta, {"id": a.doc_id}).all() == antes
    b = _ingerir(conn, "alterado.pdf", doc_id=a.doc_id)
    assert b.resultado == "reingerido"
    assert b.doc_sha256 != a.doc_sha256
    assert conn.execute(consulta, {"id": a.doc_id}).all() != antes


@pytest.mark.banco
def test_pdf_invalido_nao_apaga_chunks_anteriores_e_registra_erro(conn, rastro):
    anterior = _ingerir(conn, "selecionavel.pdf")
    consulta = text("select chunk_id, text from chunks where doc_id=:id order by position")
    antes = conn.execute(consulta, {"id": anterior.doc_id}).all()
    quantidade = len(_registros(rastro))
    with pytest.raises(ValueError):
        _ingerir(conn, "invalido.pdf", doc_id=anterior.doc_id)
    assert conn.execute(consulta, {"id": anterior.doc_id}).all() == antes
    novos = _registros(rastro)[quantidade:]
    assert len(novos) == 1 and novos[0]["etapa"] == "extracao"
    assert novos[0]["status"] == "erro" and novos[0]["erro"]
    assert novos[0]["trace_id"] != _registros(rastro)[0]["trace_id"]
