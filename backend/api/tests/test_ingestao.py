"""Tarefa 004 — ingestão de texto: canônico, chunking `estrutural-v1`, reingestão
atômica e rastro. Teste primeiro: escrito antes de existir qualquer módulo de produto.

Roda da raiz do repo:
    ./venv/Scripts/python.exe -m pytest backend/api/tests/test_ingestao.py -q
    ./venv/Scripts/python.exe -m pytest backend/api/tests/test_ingestao.py -q -m "not banco"

20 funções para os 17 critérios I1–I17 da tarefa. Tudo é observado de fora: offsets
recortados do próprio canônico, contagem de tokens feita com o tokenizer real do
bge-m3 (fixture `tokenizer`, nunca com a contagem da implementação), linhas lidas de
volta do banco com SQL cru e rastro lido como JSONL de `tmp_path`. Não há golden file
de spans: o único "esperado" é a execução anterior, dentro do teste de determinismo.

O teste estático da migração 0001 passa desde já — é pin, não feature. Por isso
os imports de produto são tolerados aqui no topo e trocados por um stub que
relança o `ModuleNotFoundError` quando chamado: a ausência do produto vira
falha dos 19 testes de feature, e não erro de coleta do arquivo inteiro.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pytest
from conftest import ROOT, _secrets, _sessao
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

try:  # código de produto do passo 4 em diante; hoje não existe — é esta a falha esperada
    from backend.src.Memorix.ingestion.canonical import canonicalizar, doc_sha256
    from backend.src.Memorix.ingestion.chunking import chunkar
    from backend.src.Memorix.ingestion.ingest import ingerir
    from backend.src.Memorix.providers.rastro import registrar  # noqa: F401 — a porta do rastro é exercitada via `ingerir`
except ModuleNotFoundError as erro:
    _FALTA = (str(erro), erro.name)

    def _ausente(*_args, **_kwargs):
        # Exceção nova a cada chamada: relançar a mesma acumularia o traceback de
        # todos os testes anteriores e a saída viraria megabytes de ruído.
        raise ModuleNotFoundError(_FALTA[0], name=_FALTA[1]) from None

    canonicalizar = doc_sha256 = chunkar = ingerir = registrar = _ausente


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestao"
NOMES = ("basico.txt", "numerado.txt", "bloco-gigante.txt", "resto-curto.txt", "sujeira.bin", "abreviacoes.txt")

MAX_TOKENS = 400
MIN_TOKENS = 80
UPLOADER = "admin-opaco-teste"

SHA_0001 = "eba47c8667c6d58aae774f8b41963abdadb1d81752088e5e019f50e6e3576562"

# Versão limpa equivalente a `sujeira.bin`: o mesmo conteúdo sem BOM, sem CRLF, sem CR
# solto, sem NUL, sem NFD, sem linhas em branco repetidas e sem espaço no fim de linha.
# Derivada dos 8 passos escritos na 004, não da implementação. O NBSP de "25 °C" fica no
# meio da linha de propósito: nenhum dos 8 passos o remove, e no fim da linha a regra
# "espaços/tabs" seria ambígua.
LIMPO = (
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
_TITULO = re.compile(r"^(?:#{1,6}\s+\S|\d+(?:\.\d+)*\.?\s+\S)")


# ---------------------------------------------------------------- helpers


def _texto(nome):
    """Borda da ingestão: bytes do arquivo → `str`, decode estrito. `canonicalizar` recebe `str`."""
    return (FIXTURES / nome).read_bytes().decode("utf-8")


def _tuplas(chunks):
    return [(c.position, c.offset_start, c.offset_end, c.text) for c in sorted(chunks, key=lambda c: c.position)]


def _inicios_de_titulo(canonico):
    """Offsets (code points) onde começa uma linha de título, pela regra da 004."""
    pos, inicios = 0, []
    for linha in canonico.split("\n"):
        if _TITULO.match(linha) and len(linha) <= 80 and not linha.endswith((".", ":", ";", ",")):
            inicios.append(pos)
        pos += len(linha) + 1
    return inicios


def _secoes(canonico):
    """Intervalos `[inicio, fim)` das seções: cada título abre a sua e vai até o próximo."""
    limites = sorted({0, len(canonico), *_inicios_de_titulo(canonico)})
    return list(zip(limites, limites[1:]))


def _secao_de(chunk, secoes):
    return next(i for i, (ini, fim) in enumerate(secoes) if ini <= chunk.offset_start < fim)


def _registros(caminho):
    assert caminho.is_file(), f"nenhum rastro escrito em {caminho}"
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _ngramas(texto, n=20):
    return {texto[i : i + n] for i in range(len(texto) - n + 1)}


def _vazamento(linha, grams, n=20):
    return next((linha[i : i + n] for i in range(len(linha) - n + 1) if linha[i : i + n] in grams), None)


def _ingerir(conn, nome, *, doc_id=None, title="Apostila sintética"):
    """Ingere uma fixture na transação do teste.

    `fonte` vai como caminho **relativo à raiz** de propósito: é o que a 004 manda
    gravar em `documents.metadata`. A sessão é a do teste (`_sessao`), senão a
    ingestão abriria outra conexão e não enxergaria o estado não commitado daqui.
    """
    fonte = (FIXTURES / nome).resolve().relative_to(ROOT)
    return ingerir(
        _texto(nome),
        doc_id=doc_id,
        title=title,
        source_type="texto",
        uploaded_by=UPLOADER,
        fonte=fonte,
        session=_sessao(conn),
    )


def _spans(conn, doc_id):
    return conn.execute(
        text("select position, offset_start, offset_end, text from chunks where doc_id = :d order by position"),
        {"d": doc_id},
    ).all()


# ------------------------------------------------- I2 — canônico (offline, sem tokenizer)


@pytest.mark.parametrize("nome", NOMES)
def test_canonicalizar_e_idempotente(nome):
    uma = canonicalizar(_texto(nome))
    assert canonicalizar(uma) == uma, f"{nome}: canonicalizar(canonicalizar(t)) != canonicalizar(t)"
    assert doc_sha256(uma) == doc_sha256(canonicalizar(uma)), f"{nome}: doc_sha256 mudou na segunda passada"
    assert uma == uma.strip(), f"{nome}: canônico com espaço nas pontas (passo 8 não rodou)"
    assert unicodedata.is_normalized("NFC", uma), f"{nome}: canônico não está em NFC (passo 5)"
    assert "\r" not in uma and "\x00" not in uma and "\ufeff" not in uma, f"{nome}: sujeira sobreviveu"
    assert "\n\n\n" not in uma, f"{nome}: três quebras seguidas sobreviveram ao passo 7"


def test_sujeira_produz_o_mesmo_canonico_e_sha_da_versao_limpa():
    sujo = canonicalizar(_texto("sujeira.bin"))
    assert sujo == LIMPO, "canonicalização de sujeira.bin divergiu da versão limpa equivalente"
    assert doc_sha256(sujo) == doc_sha256(LIMPO), "mesmo canônico com doc_sha256 diferente"
    assert canonicalizar(LIMPO) == LIMPO, "a versão limpa não é ponto fixo da canonicalização"
    assert "\u00a0" in sujo, "o NBSP do meio da linha não pertence a nenhum dos 8 passos e deve sobreviver"


# ------------------------------------------------- I1, I3–I9 — chunking (tokenizer real)


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_chunking_e_deterministico_em_duas_execucoes(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    primeira = _tuplas(chunkar(canonico))
    segunda = _tuplas(chunkar(canonico))
    assert primeira, f"{nome}: chunkar devolveu lista vazia"
    assert primeira == segunda, f"{nome}: chunkar não é determinístico entre duas execuções"


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_offsets_dentro_do_canonico(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    for c in chunkar(canonico):
        assert 0 <= c.offset_start < c.offset_end <= len(canonico), (
            f"{nome}: position={c.position} tem span ({c.offset_start}, {c.offset_end})"
            f" fora de [0, {len(canonico)}]"
        )


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_recorte_do_canonico_bate_com_o_texto_do_chunk(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    for c in chunkar(canonico):
        assert canonico[c.offset_start : c.offset_end] == c.text, (
            f"{nome}: position={c.position} — canonico[{c.offset_start}:{c.offset_end}] != text"
        )
        assert c.text == c.text.strip(), f"{nome}: position={c.position} começa ou termina em espaço"


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_chunks_sao_disjuntos_e_ordenados_por_position(nome, tokenizer):
    chunks = sorted(chunkar(canonicalizar(_texto(nome))), key=lambda c: c.position)
    assert [c.position for c in chunks] == list(range(len(chunks))), f"{nome}: position não é 0..n-1"
    for anterior, seguinte in zip(chunks, chunks[1:]):
        assert anterior.offset_end <= seguinte.offset_start, (
            f"{nome}: sobreposição entre position {anterior.position} (fim {anterior.offset_end})"
            f" e {seguinte.position} (início {seguinte.offset_start})"
        )


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_nenhum_alfanumerico_some_ou_troca_de_ordem(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    chunks = sorted(chunkar(canonico), key=lambda c: c.position)
    esperado = [ch for ch in canonico if ch.isalnum()]
    obtido = [ch for c in chunks for ch in c.text if ch.isalnum()]
    assert obtido == esperado, (
        f"{nome}: cobertura alfanumérica quebrada — {len(esperado)} caracteres no canônico,"
        f" {len(obtido)} nos chunks"
    )


@pytest.mark.hf
@pytest.mark.parametrize("nome", NOMES)
def test_nenhum_chunk_passa_de_400_tokens(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    if nome == "bloco-gigante.txt":
        inteiro = len(tokenizer(canonico, add_special_tokens=False).input_ids)
        assert inteiro > MAX_TOKENS, (
            f"a fixture do bloco gigante caiu para {inteiro} tokens e deixou de forçar corte: I7 passaria vazio"
        )
        assert "\n\n" not in canonico, "a fixture do bloco gigante ganhou linha em branco e deixou de ser um bloco só"
    for c in chunkar(canonico):
        n = len(tokenizer(c.text, add_special_tokens=False).input_ids)
        assert n <= MAX_TOKENS, f"{nome}: position={c.position} tem {n} tokens; o teto de {MAX_TOKENS} é duro"


@pytest.mark.hf
def test_chunk_abaixo_de_80_tokens_e_unico_da_secao_ou_infundivel(tokenizer):
    canonico = canonicalizar(_texto("resto-curto.txt"))
    chunks = sorted(chunkar(canonico), key=lambda c: c.position)
    secoes = _secoes(canonico)

    def n(span):
        return len(tokenizer(span, add_special_tokens=False).input_ids)

    por_secao = {}
    for c in chunks:
        por_secao.setdefault(_secao_de(c, secoes), []).append(c)

    curtos = [c for c in chunks if n(c.text) < MIN_TOKENS]
    assert curtos, "resto-curto.txt deixou de produzir chunk abaixo de 80 tokens: I8 estaria passando vazio"

    for c in curtos:
        irmaos = por_secao[_secao_de(c, secoes)]
        if len(irmaos) == 1:
            continue  # (a) seção inteira abaixo do piso: é mantida
        i = irmaos.index(c)
        cabe_antes = i > 0 and n(canonico[irmaos[i - 1].offset_start : c.offset_end]) <= MAX_TOKENS
        cabe_depois = i + 1 < len(irmaos) and n(canonico[c.offset_start : irmaos[i + 1].offset_end]) <= MAX_TOKENS
        assert not (cabe_antes or cabe_depois), (
            f"position={c.position} tem {n(c.text)} tokens e ainda cabia fundido na mesma seção"
            f" (anterior={cabe_antes}, seguinte={cabe_depois}): a passada de fusão não rodou"
        )


@pytest.mark.hf
@pytest.mark.parametrize("nome", ("basico.txt", "numerado.txt"))
def test_nenhum_chunk_atravessa_inicio_de_titulo(nome, tokenizer):
    canonico = canonicalizar(_texto(nome))
    inicios = _inicios_de_titulo(canonico)
    assert len(inicios) >= 3, f"{nome}: fixture ficou sem títulos ({inicios}); o teste passaria vazio"
    for c in chunkar(canonico):
        atravessa = [p for p in inicios if c.offset_start < p < c.offset_end]
        assert not atravessa, (
            f"{nome}: position={c.position} ({c.offset_start}, {c.offset_end}) engole o início de título em {atravessa}"
        )


# ------------------------------------------------- I3/I4 banco, I10–I17 — persistência e rastro


@pytest.mark.banco
@pytest.mark.hf
def test_recorte_exato_relido_do_banco(conn, tokenizer, rastro):
    canonico = canonicalizar(_texto("basico.txt"))
    r = _ingerir(conn, "basico.txt")
    linhas = _spans(conn, r.doc_id)
    assert linhas, "nenhum chunk persistido"
    for position, inicio, fim, gravado in linhas:
        # O INSERT ter passado já prova I3 no banco: `ck_chunks_offsets` recusa offset_end <= offset_start.
        assert 0 <= inicio < fim <= len(canonico), f"position={position}: span ({inicio}, {fim}) fora do canônico"
        assert canonico[inicio:fim] == gravado, f"position={position}: recorte do canônico != `text` gravado"


@pytest.mark.banco
@pytest.mark.hf
def test_position_contigua_de_zero_a_n_menos_um_e_chunk_id_gerado(conn, tokenizer, rastro):
    r = _ingerir(conn, "basico.txt")
    linhas = conn.execute(
        text("select chunk_id, position from chunks where doc_id = :d order by position"), {"d": r.doc_id}
    ).all()
    assert linhas, "nenhum chunk persistido"
    assert [p for _, p in linhas] == list(range(len(linhas))), f"position não é 0..n-1: {[p for _, p in linhas]}"
    divergentes = [cid for cid, p in linhas if cid != f"{r.doc_id}:{p}"]
    assert not divergentes, f"chunk_id fora do formato doc_id:position: {divergentes}"


@pytest.mark.banco
@pytest.mark.hf
def test_reingestao_com_sha_identico_nao_toca_chunks_e_registra_sem_mudanca(conn, tokenizer, rastro):
    primeira = _ingerir(conn, "basico.txt")
    # `ctid` é o detector real: dentro de uma só transação `now()` não muda, então
    # `created_at` sozinho não distingue NO-OP de apagar-e-reinserir.
    consulta = text("select chunk_id, created_at, ctid::text from chunks where doc_id = :d order by position")
    antes = conn.execute(consulta, {"d": primeira.doc_id}).all()
    assert antes, "nenhum chunk persistido na primeira ingestão"

    segunda = _ingerir(conn, "basico.txt", doc_id=primeira.doc_id)
    assert segunda.resultado == "sem_mudanca", f"sha idêntico devia ser NO-OP, veio resultado={segunda.resultado!r}"
    depois = conn.execute(consulta, {"d": primeira.doc_id}).all()
    assert len(depois) == len(antes), f"a contagem de chunks mudou: {len(antes)} → {len(depois)}"
    assert depois == antes, "as linhas de chunks foram recriadas (ctid/created_at mudou) em vez de ficarem intactas"
    assert any(r.get("resultado") == "sem_mudanca" for r in _registros(rastro)), (
        "nenhum registro de rastro com resultado='sem_mudanca'"
    )


@pytest.mark.banco
@pytest.mark.hf
def test_reingerir_a_depois_b_depois_a_reproduz_os_spans_da_primeira_ingestao(conn, tokenizer, rastro):
    a1 = _ingerir(conn, "basico.txt")
    spans_a = _spans(conn, a1.doc_id)
    assert spans_a, "nenhum chunk persistido"

    b = _ingerir(conn, "numerado.txt", doc_id=a1.doc_id)
    assert b.resultado == "reingerido", f"conteúdo diferente devia reingerir, veio {b.resultado!r}"
    assert _spans(conn, a1.doc_id) != spans_a, "A e B produziram os mesmos spans: o teste passaria vazio"

    a2 = _ingerir(conn, "basico.txt", doc_id=a1.doc_id)
    assert a2.resultado == "reingerido", f"voltar para A devia reingerir, veio {a2.resultado!r}"
    assert a2.doc_sha256 == a1.doc_sha256, "o mesmo texto gerou doc_sha256 diferente"
    assert _spans(conn, a1.doc_id) == spans_a, "voltar para A não reproduziu os spans da primeira ingestão"


@pytest.mark.banco
@pytest.mark.hf
def test_falha_no_meio_dos_inserts_preserva_os_chunks_antigos(conn, tokenizer, rastro):
    antigo = _ingerir(conn, "numerado.txt")
    antes = _spans(conn, antigo.doc_id)
    assert antes, "nenhum chunk persistido"
    novos = chunkar(canonicalizar(_texto("bloco-gigante.txt")))
    assert len(novos) >= 3, f"o novo conteúdo gera {len(novos)} chunks; são precisos 3 para falhar no meio"

    # DDL é transacional no Postgres: a constraint some no rollback da fixture e não
    # exige monkeypatch de ORM. NOT VALID não checa as linhas antigas, só os INSERTs novos.
    conn.execute(text("alter table chunks add constraint ck_tmp check (position <> 2) not valid"))
    with pytest.raises(IntegrityError) as falha:
        _ingerir(conn, "bloco-gigante.txt", doc_id=antigo.doc_id)
    assert "ck_tmp" in str(falha.value), f"a exceção não veio da constraint injetada: {falha.value}"
    assert _spans(conn, antigo.doc_id) == antes, "o DELETE da reingestão sobreviveu à falha: chunks antigos perdidos"


@pytest.mark.banco
@pytest.mark.hf
def test_ingestao_grava_duas_linhas_de_rastro_com_o_mesmo_trace_id(conn, tokenizer, rastro):
    r = _ingerir(conn, "basico.txt")
    registros = _registros(rastro)
    assert len(registros) == 2, f"esperava 2 linhas de rastro, vieram {len(registros)}"
    assert {x["etapa"] for x in registros} == {"ingestao", "chunking"}, f"etapas: {[x['etapa'] for x in registros]}"
    assert len({x["trace_id"] for x in registros}) == 1, "as duas etapas usaram trace_id diferente"
    for x in registros:
        assert x["status"] == "ok", f"etapa {x['etapa']} com status {x['status']!r}"
        assert x["timestamp"], f"etapa {x['etapa']} sem timestamp"
        assert isinstance(x["duracao_ms"], (int, float)), f"etapa {x['etapa']} sem duracao_ms numérica"

    chunking = next(x for x in registros if x["etapa"] == "chunking")
    gravado = conn.execute(text("select doc_sha256 from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert chunking["doc_sha256"] == gravado, "doc_sha256 do rastro de chunking diverge do gravado em documents"
    faltando = [c for c in chunking["chunks"] if not {"chunk_id", "offset_start", "offset_end", "n_tokens"} <= set(c)]
    assert not faltando, f"registros de chunk sem os campos obrigatórios: {faltando[:1]}"
    persistidos = set(
        conn.execute(text("select chunk_id from chunks where doc_id = :d"), {"d": r.doc_id}).scalars()
    )
    assert persistidos, "nenhum chunk persistido"
    ausentes = persistidos - {c["chunk_id"] for c in chunking["chunks"]}
    assert not ausentes, f"chunk_id persistido e fora do rastro de chunking: {sorted(ausentes)[:3]}"


@pytest.mark.banco
@pytest.mark.hf
def test_ingestao_que_falha_grava_rastro_com_status_erro_e_mesmo_trace_id(conn, tokenizer, rastro):
    ok = _ingerir(conn, "basico.txt")
    antes = _registros(rastro)

    # Mesmo texto entrando como documento novo: `uq_documents_doc_sha256` recusa.
    with pytest.raises(IntegrityError):
        _ingerir(conn, "basico.txt")

    novos = _registros(rastro)[len(antes) :]
    assert novos, "a ingestão que falhou não deixou rastro algum: erro silencioso é proibido"
    assert len({x["trace_id"] for x in novos}) == 1, "a ingestão que falhou usou mais de um trace_id"
    assert novos[0]["trace_id"] != antes[0]["trace_id"], "a ingestão que falhou reaproveitou o trace_id anterior"
    com_erro = [x for x in novos if x.get("status") == "erro"]
    assert com_erro, f"nenhum registro com status='erro': {novos}"
    assert all(x.get("erro") for x in com_erro), "registro de erro com o campo `erro` vazio"
    assert ok.doc_id, "a primeira ingestão devia ter criado o documento"


@pytest.mark.banco
@pytest.mark.hf
def test_rastro_nao_contem_texto_do_documento_nem_segredo(conn, tokenizer, rastro):
    canonico = canonicalizar(_texto("basico.txt"))
    _ingerir(conn, "basico.txt")
    linhas = [linha for linha in rastro.read_text(encoding="utf-8").splitlines() if linha.strip()]
    assert linhas, "nenhuma linha de rastro para varrer"

    grams = _ngramas(canonico)
    proibidos = ["HF_TOKEN", "password", "DB_", *_secrets()]
    for linha in linhas:
        vazou = _vazamento(linha, grams)
        assert vazou is None, f"rastro carrega trecho do documento: {vazou!r}"
        achados = [p for p in proibidos if p in linha]
        assert not achados, f"rastro carrega segredo ou variável de ambiente: {achados[:1]}"


@pytest.mark.banco
@pytest.mark.hf
def test_metadata_guarda_caminho_relativo_do_fonte_que_reproduz_o_sha(conn, tokenizer, rastro):
    r = _ingerir(conn, "basico.txt")
    extra = conn.execute(text("select metadata from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert isinstance(extra, dict) and extra, f"documents.metadata vazio ou não é objeto JSON: {extra!r}"

    candidatos = [v for v in extra.values() if isinstance(v, str) and (ROOT / v).is_file()]
    assert candidatos, f"nenhum caminho de arquivo legível em documents.metadata: {extra}"
    caminho = candidatos[0]
    assert not Path(caminho).is_absolute(), f"caminho absoluto gravado em metadata: {caminho}"
    assert Path(caminho).name == "basico.txt", f"metadata aponta para outro arquivo: {caminho}"

    relido = (ROOT / caminho).read_bytes().decode("utf-8")
    gravado = conn.execute(text("select doc_sha256 from documents where doc_id = :d"), {"d": r.doc_id}).scalar_one()
    assert doc_sha256(canonicalizar(relido)) == gravado, "reler o fonte pelo caminho de metadata não reproduz o sha"

    serializado = json.dumps(extra, ensure_ascii=False)
    vazou = _vazamento(serializado, _ngramas(canonicalizar(_texto("basico.txt"))))
    assert vazou is None, f"texto do documento dentro de documents.metadata: {vazou!r}"


# ------------------------------------------------- migração 0001 inalterada


def test_migracao_0001_inalterada():
    versions = sorted((ROOT / "backend/api/migrations/versions").glob("*.py"))
    assert [p.name for p in versions] == ["0001_documents_chunks.py"], (
        f"versions/ devia ter só a 0001: {[p.name for p in versions]}"
    )
    sha = hashlib.sha256(versions[0].read_bytes()).hexdigest()
    assert sha == SHA_0001, f"a migração 0001 foi alterada (sha256 {sha})"
