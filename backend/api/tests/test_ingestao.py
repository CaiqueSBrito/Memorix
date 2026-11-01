
import json
import re
import unicodedata
from pathlib import Path

import pytest
from conftest import ROOT, _secrets, _test_session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

try:  # código de produto do passo 4 em diante; hoje não existe — é esta a falha esperada
    from backend.src.Memorix.ingestion.canonical import canonicalize, doc_sha256
    from backend.src.Memorix.ingestion.chunking import chunking
    from backend.src.Memorix.ingestion.ingest import ingest_document
    from backend.src.Memorix.providers.observabilitiy import record_trace  # noqa: F401 — a porta do rastro é exercitada via `ingest_document`
except ModuleNotFoundError as error:
    _MISSING_IMPORT = (str(error), error.name)

    def _missing_module(*_args, **_kwargs):
        # Exceção nova a cada chamada: relançar a mesma acumularia o traceback de
        # todos os testes anteriores e a saída viraria megabytes de ruído.
        raise ModuleNotFoundError(_MISSING_IMPORT[0], name=_MISSING_IMPORT[1]) from None

    canonicalize = doc_sha256 = chunking = ingest_document = record_trace = _missing_module


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestao"
FIXTURE_NAMES = ("basico.txt", "numerado.txt", "bloco-gigante.txt", "resto-curto.txt", "sujeira.bin", "abreviacoes.txt")

MAX_TOKENS = 400
MIN_TOKENS = 80
UPLOADER = "admin-opaco-teste"


# Versão limpa equivalente a `sujeira.bin`: o mesmo conteúdo sem BOM, sem CRLF, sem CR
# solto, sem NUL, sem NFD, sem linhas em branco repetidas e sem espaço no fim de linha.
# Derivada dos 8 passos escritos na 004, não da implementação. O NBSP de "25 °C" fica no
# meio da linha de propósito: nenhum dos 8 passos o remove, e no fim da linha a regra
# "espaços/tabs" seria ambígua.
CLEAN_TEXT = (
    "# Água e soluções\n"
    "\n"
    "A água é o solvente universal e dissolve a maior parte dos sais a 25\u00a0°C.\n"
    "\n"
    "Numa solução saturada, o soluto em excesso se deposita no fundo do recipiente.\n"
    "\n"
    "## Concentração\n"
    "\n"
    "A concentração comum relaciona a massa do soluto com o volume da solução.\n"
    "A molaridade usa a quantidade de matéria em vez da massa."
)

# Regra de título da 004, escrita a partir da especificação (não lida do produto).
_HEADING = re.compile(r"^(?:#{1,6}\s+\S|\d+(?:\.\d+)*\.?\s+\S)")


# ---------------------------------------------------------------- helpers


def _fixture_text(fixture_name):
    """Borda da ingestão: bytes do arquivo → `str`, decode estrito. `canonicalize` recebe `str`."""
    return (FIXTURES / fixture_name).read_bytes().decode("utf-8")


def _chunk_tuples(chunks):
    return [(c.position, c.offset_start, c.offset_end, c.text) for c in sorted(chunks, key=lambda c: c.position)]


def _heading_starts(canonical_text):
    """Offsets (code points) onde começa uma linha de título, pela regra da 004."""
    offset, starts = 0, []
    for line in canonical_text.split("\n"):
        if _HEADING.match(line) and len(line) <= 80 and not line.endswith((".", ":", ";", ",")):
            starts.append(offset)
        offset += len(line) + 1
    return starts


def _sections(canonical_text):
    """Intervalos `[inicio, fim)` das seções: cada título abre a sua e vai até o próximo."""
    boundaries = sorted({0, len(canonical_text), *_heading_starts(canonical_text)})
    return list(zip(boundaries, boundaries[1:]))


def _chunk_section(chunk, sections):
    return next(i for i, (start, end) in enumerate(sections) if start <= chunk.offset_start < end)


def _trace_records(path):
    assert path.is_file(), f"nenhum rastro escrito em {path}"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ngrams(content, n=20):
    return {content[i : i + n] for i in range(len(content) - n + 1)}


def _leaked_fragment(line, grams, n=20):
    return next((line[i : i + n] for i in range(len(line) - n + 1) if line[i : i + n] in grams), None)


def _ingest_fixture(conn, fixture_name, *, doc_id=None, title="Apostila sintética"):
    """Ingere uma fixture na transação do teste.

    `fonte` vai como caminho **relativo à raiz** de propósito: é o que a 004 manda
    gravar em `documents.metadata`. A sessão é a do teste (`_test_session`), senão a
    ingestão abriria outra conexão e não enxergaria o estado não commitado daqui.
    """
    source = (FIXTURES / fixture_name).resolve().relative_to(ROOT)
    return ingest_document(
        _fixture_text(fixture_name),
        doc_id=doc_id,
        title=title,
        source_type="texto",
        uploaded_by=UPLOADER,
        source=source,
        session=_test_session(conn),
    )


def _spans(conn, doc_id):
    return conn.execute(
        text("select position, offset_start, offset_end, text from chunks where doc_id = :d order by position"),
        {"d": doc_id},
    ).all()


# ------------------------------------------------- I2 — canônico (offline, sem tokenizer)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_canonicalization_is_idempotent(fixture_name):
    once = canonicalize(_fixture_text(fixture_name))
    assert canonicalize(once) == once, f"{fixture_name}: canonicalize(canonicalize(t)) != canonicalize(t)"
    assert doc_sha256(once) == doc_sha256(canonicalize(once)), f"{fixture_name}: doc_sha256 mudou na segunda passada"
    assert once == once.strip(), f"{fixture_name}: canônico com espaço nas pontas (passo 8 não rodou)"
    assert unicodedata.is_normalized("NFC", once), f"{fixture_name}: canônico não está em NFC (passo 5)"
    assert "\r" not in once and "\x00" not in once and "\ufeff" not in once, f"{fixture_name}: sujeira sobreviveu"
    assert "\n\n\n" not in once, f"{fixture_name}: três quebras seguidas sobreviveram ao passo 7"


def test_dirty_text_matches_clean_canonical_text_and_hash():
    dirty = canonicalize(_fixture_text("sujeira.bin"))
    assert dirty == CLEAN_TEXT, "canonicalização de sujeira.bin divergiu da versão limpa equivalente"
    assert doc_sha256(dirty) == doc_sha256(CLEAN_TEXT), "mesmo canônico com doc_sha256 diferente"
    assert canonicalize(CLEAN_TEXT) == CLEAN_TEXT, "a versão limpa não é ponto fixo da canonicalização"
    assert "\u00a0" in dirty, "o NBSP do meio da linha não pertence a nenhum dos 8 passos e deve sobreviver"


# ------------------------------------------------- I1, I3–I9 — chunking (tokenizer real)


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_chunking_is_deterministic_across_runs(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    first = _chunk_tuples(chunking(canonical_text))
    second = _chunk_tuples(chunking(canonical_text))
    assert first, f"{fixture_name}: chunking devolveu lista vazia"
    assert first == second, f"{fixture_name}: chunking não é determinístico entre duas execuções"


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_offsets_stay_within_canonical_text(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    for c in chunking(canonical_text):
        assert 0 <= c.offset_start < c.offset_end <= len(canonical_text), (
            f"{fixture_name}: position={c.position} tem span ({c.offset_start}, {c.offset_end})"
            f" fora de [0, {len(canonical_text)}]"
        )


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_canonical_slice_matches_chunk_text(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    for c in chunking(canonical_text):
        assert canonical_text[c.offset_start : c.offset_end] == c.text, (
            f"{fixture_name}: position={c.position} — canonico[{c.offset_start}:{c.offset_end}] != text"
        )
        assert c.text == c.text.strip(), f"{fixture_name}: position={c.position} começa ou termina em espaço"


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_chunks_are_disjoint_and_position_ordered(fixture_name, tokenizer):
    chunks = sorted(chunking(canonicalize(_fixture_text(fixture_name))), key=lambda c: c.position)
    assert [c.position for c in chunks] == list(range(len(chunks))), f"{fixture_name}: position não é 0..n-1"
    for previous, next_chunk in zip(chunks, chunks[1:]):
        assert previous.offset_end <= next_chunk.offset_start, (
            f"{fixture_name}: sobreposição entre position {previous.position} (fim {previous.offset_end})"
            f" e {next_chunk.position} (início {next_chunk.offset_start})"
        )


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_alphanumeric_characters_are_preserved_in_order(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    chunks = sorted(chunking(canonical_text), key=lambda c: c.position)
    expected = [ch for ch in canonical_text if ch.isalnum()]
    actual = [ch for c in chunks for ch in c.text if ch.isalnum()]
    assert actual == expected, (
        f"{fixture_name}: cobertura alfanumérica quebrada — {len(expected)} caracteres no canônico,"
        f" {len(actual)} nos chunks"
    )


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_chunks_never_exceed_400_tokens(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    if fixture_name == "bloco-gigante.txt":
        whole = len(tokenizer(canonical_text, add_special_tokens=False).input_ids)
        assert whole > MAX_TOKENS, (
            f"a fixture do bloco gigante caiu para {whole} tokens e deixou de forçar corte: I7 passaria vazio"
        )
        assert "\n\n" not in canonical_text, "a fixture do bloco gigante ganhou linha em branco e deixou de ser um bloco só"
    for c in chunking(canonical_text):
        n = len(tokenizer(c.text, add_special_tokens=False).input_ids)
        assert n <= MAX_TOKENS, f"{fixture_name}: position={c.position} tem {n} tokens; o teto de {MAX_TOKENS} é duro"


@pytest.mark.hf
def test_short_chunk_is_only_one_in_section_or_cannot_merge(tokenizer):
    canonical_text = canonicalize(_fixture_text("resto-curto.txt"))
    chunks = sorted(chunking(canonical_text), key=lambda c: c.position)
    sections = _sections(canonical_text)

    def n(span):
        return len(tokenizer(span, add_special_tokens=False).input_ids)

    by_section = {}
    for c in chunks:
        by_section.setdefault(_chunk_section(c, sections), []).append(c)

    short_chunks = [c for c in chunks if n(c.text) < MIN_TOKENS]
    assert short_chunks, "resto-curto.txt deixou de produzir chunk abaixo de 80 tokens: I8 estaria passando vazio"

    for c in short_chunks:
        siblings = by_section[_chunk_section(c, sections)]
        if len(siblings) == 1:
            continue  # (a) seção inteira abaixo do piso: é mantida
        i = siblings.index(c)
        fits_previous = i > 0 and n(canonical_text[siblings[i - 1].offset_start : c.offset_end]) <= MAX_TOKENS
        fits_next = i + 1 < len(siblings) and n(canonical_text[c.offset_start : siblings[i + 1].offset_end]) <= MAX_TOKENS
        assert not (fits_previous or fits_next), (
            f"position={c.position} tem {n(c.text)} tokens e ainda cabia fundido na mesma seção"
            f" (anterior={fits_previous}, seguinte={fits_next}): a passada de fusão não rodou"
        )


@pytest.mark.hf
@pytest.mark.parametrize("fixture_name", ("basico.txt", "numerado.txt"))
def test_no_chunk_crosses_heading_start(fixture_name, tokenizer):
    canonical_text = canonicalize(_fixture_text(fixture_name))
    starts = _heading_starts(canonical_text)
    assert len(starts) >= 3, f"{fixture_name}: fixture ficou sem títulos ({starts}); o teste passaria vazio"
    for c in chunking(canonical_text):
        crossed = [p for p in starts if c.offset_start < p < c.offset_end]
        assert not crossed, (
            f"{fixture_name}: position={c.position} ({c.offset_start}, {c.offset_end}) engole o início de título em {crossed}"
        )


# ------------------------------------------------- I3/I4 banco, I10–I17 — persistência e rastro


@pytest.mark.banco
@pytest.mark.hf
def test_exact_slice_matches_database_row(conn, tokenizer, trace_file):
    canonical_text = canonicalize(_fixture_text("basico.txt"))
    r = _ingest_fixture(conn, "basico.txt")
    rows = _spans(conn, r.doc_id)
    assert rows, "nenhum chunk persistido"
    for position, start, end, stored in rows:
        # O INSERT ter passado já prova I3 no banco: `ck_chunks_offsets` recusa offset_end <= offset_start.
        assert 0 <= start < end <= len(canonical_text), f"position={position}: span ({start}, {end}) fora do canônico"
        assert canonical_text[start:end] == stored, f"position={position}: recorte do canônico != `text` gravado"


@pytest.mark.banco
@pytest.mark.hf
def test_positions_are_contiguous_and_chunk_ids_generated(conn, tokenizer, trace_file):
    r = _ingest_fixture(conn, "basico.txt")
    rows = conn.execute(
        text("select chunk_id, position from chunks where doc_id = :d order by position"), {"d": r.doc_id}
    ).all()
    assert rows, "nenhum chunk persistido"
    assert [p for _, p in rows] == list(range(len(rows))), f"position não é 0..n-1: {[p for _, p in rows]}"
    mismatched = [cid for cid, p in rows if cid != f"{r.doc_id}:{p}"]
    assert not mismatched, f"chunk_id fora do formato doc_id:position: {mismatched}"


@pytest.mark.banco
@pytest.mark.hf
def test_same_hash_reingestion_leaves_chunks_intact(conn, tokenizer, trace_file):
    first = _ingest_fixture(conn, "basico.txt")
    # `ctid` é o detector real: dentro de uma só transação `now()` não muda, então
    # `created_at` sozinho não distingue NO-OP de apagar-e-reinserir.
    query = text("select chunk_id, created_at, ctid::text from chunks where doc_id = :d order by position")
    before = conn.execute(query, {"d": first.doc_id}).all()
    assert before, "nenhum chunk persistido na primeira ingestão"

    second = _ingest_fixture(conn, "basico.txt", doc_id=first.doc_id)
    assert second.status == "no_changes", f"sha idêntico devia ser NO-OP, veio resultado={second.status!r}"
    after = conn.execute(query, {"d": first.doc_id}).all()
    assert len(after) == len(before), f"a contagem de chunks mudou: {len(before)} → {len(after)}"
    assert after == before, "as linhas de chunks foram recriadas (ctid/created_at mudou) em vez de ficarem intactas"
    assert any(r.get("resultado") == "no_changes" for r in _trace_records(trace_file)), (
        "nenhum registro de rastro com resultado='no_changes'"
    )


@pytest.mark.banco
@pytest.mark.hf
def test_reingesting_a_after_b_restores_original_spans(conn, tokenizer, trace_file):
    a1 = _ingest_fixture(conn, "basico.txt")
    spans_a = _spans(conn, a1.doc_id)
    assert spans_a, "nenhum chunk persistido"

    b = _ingest_fixture(conn, "numerado.txt", doc_id=a1.doc_id)
    assert b.status == "replaced", f"conteúdo diferente devia reingerir, veio {b.status!r}"
    assert _spans(conn, a1.doc_id) != spans_a, "A e B produziram os mesmos spans: o teste passaria vazio"

    a2 = _ingest_fixture(conn, "basico.txt", doc_id=a1.doc_id)
    assert a2.status == "replaced", f"voltar para A devia reingerir, veio {a2.status!r}"
    assert a2.doc_sha256 == a1.doc_sha256, "o mesmo texto gerou doc_sha256 diferente"
    assert _spans(conn, a1.doc_id) == spans_a, "voltar para A não reproduziu os spans da primeira ingestão"


@pytest.mark.banco
@pytest.mark.hf
def test_insert_failure_preserves_existing_chunks(conn, tokenizer, trace_file):
    existing = _ingest_fixture(conn, "numerado.txt")
    before = _spans(conn, existing.doc_id)
    assert before, "nenhum chunk persistido"
    new_entries = chunking(canonicalize(_fixture_text("bloco-gigante.txt")))
    assert len(new_entries) >= 3, f"o novo conteúdo gera {len(new_entries)} chunks; são precisos 3 para falhar no meio"

    # DDL é transacional no Postgres: a constraint some no rollback da fixture e não
    # exige monkeypatch de ORM. NOT VALID não checa as linhas antigas, só os INSERTs novos.
    conn.execute(text("alter table chunks add constraint ck_tmp check (position <> 2) not valid"))
    with pytest.raises(IntegrityError) as failure:
        _ingest_fixture(conn, "bloco-gigante.txt", doc_id=existing.doc_id)
    assert "ck_tmp" in str(failure.value), f"a exceção não veio da constraint injetada: {failure.value}"
    assert _spans(conn, existing.doc_id) == before, "o DELETE da reingestão sobreviveu à falha: chunks antigos perdidos"


@pytest.mark.banco
@pytest.mark.hf
def test_ingestion_records_two_events_with_same_trace_id(conn, tokenizer, trace_file):
    r = _ingest_fixture(conn, "basico.txt")
    records = _trace_records(trace_file)
    assert len(records) == 2, f"esperava 2 linhas de rastro, vieram {len(records)}"
    assert {x["etapa"] for x in records} == {"ingestao", "chunking"}, f"etapas: {[x['etapa'] for x in records]}"
    assert len({x["trace_id"] for x in records}) == 1, "as duas etapas usaram trace_id diferente"
    for x in records:
        assert x["status"] == "ok", f"etapa {x['etapa']} com status {x['status']!r}"
        assert x["timestamp"], f"etapa {x['etapa']} sem timestamp"
        assert isinstance(x["duracao_ms"], (int, float)), f"etapa {x['etapa']} sem duracao_ms numérica"

    chunking = next(x for x in records if x["etapa"] == "chunking")
    stored = conn.execute(text("select doc_sha256 from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert chunking["doc_sha256"] == stored, "doc_sha256 do rastro de chunking diverge do gravado em documents"
    missing = [c for c in chunking["chunks"] if not {"chunk_id", "offset_start", "offset_end", "n_tokens"} <= set(c)]
    assert not missing, f"registros de chunk sem os campos obrigatórios: {missing[:1]}"
    persisted = set(
        conn.execute(text("select chunk_id from chunks where doc_id = :d"), {"d": r.doc_id}).scalars()
    )
    assert persisted, "nenhum chunk persistido"
    absent = persisted - {c["chunk_id"] for c in chunking["chunks"]}
    assert not absent, f"chunk_id persistido e fora do rastro de chunking: {sorted(absent)[:3]}"


@pytest.mark.banco
@pytest.mark.hf
def test_failed_ingestion_records_error_with_same_trace_id(conn, tokenizer, trace_file):
    ok = _ingest_fixture(conn, "basico.txt")
    before = _trace_records(trace_file)

    # Mesmo texto entrando como documento novo: `uq_documents_doc_sha256` recusa.
    with pytest.raises(IntegrityError):
        _ingest_fixture(conn, "basico.txt")

    new_entries = _trace_records(trace_file)[len(before) :]
    assert new_entries, "a ingestão que falhou não deixou rastro algum: erro silencioso é proibido"
    assert len({x["trace_id"] for x in new_entries}) == 1, "a ingestão que falhou usou mais de um trace_id"
    assert new_entries[0]["trace_id"] != before[0]["trace_id"], "a ingestão que falhou reaproveitou o trace_id anterior"
    errors = [x for x in new_entries if x.get("status") == "erro"]
    assert errors, f"nenhum registro com status='erro': {new_entries}"
    assert all(x.get("erro") for x in errors), "registro de erro com o campo `erro` vazio"
    assert ok.doc_id, "a primeira ingestão devia ter criado o documento"


@pytest.mark.banco
@pytest.mark.hf
def test_trace_contains_neither_document_text_nor_secrets(conn, tokenizer, trace_file):
    canonical_text = canonicalize(_fixture_text("basico.txt"))
    _ingest_fixture(conn, "basico.txt")
    rows = [line for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "nenhuma linha de rastro para varrer"

    grams = _ngrams(canonical_text)
    forbidden = ["HF_TOKEN", "password", "DB_", *_secrets()]
    for line in rows:
        leak = _leaked_fragment(line, grams)
        assert leak is None, f"rastro carrega trecho do documento: {leak!r}"
        found = [p for p in forbidden if p in line]
        assert not found, f"rastro carrega segredo ou variável de ambiente: {found[:1]}"


@pytest.mark.banco
@pytest.mark.hf
def test_metadata_source_path_reproduces_hash(conn, tokenizer, trace_file):
    r = _ingest_fixture(conn, "basico.txt")
    extra = conn.execute(text("select metadata from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert isinstance(extra, dict) and extra, f"documents.metadata vazio ou não é objeto JSON: {extra!r}"

    candidates = [v for v in extra.values() if isinstance(v, str) and (ROOT / v).is_file()]
    assert candidates, f"nenhum caminho de arquivo legível em documents.metadata: {extra}"
    path = candidates[0]
    assert not Path(path).is_absolute(), f"caminho absoluto gravado em metadata: {path}"
    assert Path(path).name == "basico.txt", f"metadata aponta para outro arquivo: {path}"

    reread = (ROOT / path).read_bytes().decode("utf-8")
    stored = conn.execute(text("select doc_sha256 from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert doc_sha256(canonicalize(reread)) == stored, "reler o fonte pelo caminho de metadata não reproduz o sha"

    serialized = json.dumps(extra, ensure_ascii=False)
    leak = _leaked_fragment(serialized, _ngrams(canonicalize(_fixture_text("basico.txt"))))
    assert leak is None, f"texto do documento dentro de documents.metadata: {leak!r}"


