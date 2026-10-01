"""Chunking estrutural com offsets em code points do texto canônico."""

import re
from dataclasses import dataclass
from functools import lru_cache

from ..config.config import ConfigIngestao as Config

_TITULO = re.compile(r"^(?:#{1,6}\s+\S|\d+(?:\.\d+)*\.?\s+\S)")
_ABREVIACAO = re.compile(r"(?<!\w)(?i:Sr|Sra|Dr|art|p|pág|ex|fig|nº|cf)\.$|(?<!\w)[A-ZÁÉÍÓÚ]\.$")
_SEPARADORES = (
    re.compile(r"\n{2,}"),
    re.compile(r"\n"),
    re.compile(r"[.!?…]\s+"),
    re.compile(r"[;:]\s+"),
    re.compile(r"\s+"),
)


@dataclass(frozen=True)
class Trecho:
    position: int
    offset_start: int
    offset_end: int
    text: str
    n_tokens: int


@lru_cache(maxsize=1)
def tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(Config.tokenizer, revision=Config.revision, local_files_only=True)


def n_tokens(texto: str) -> int:
    return len(tokenizer()(texto, add_special_tokens=False).input_ids)


def _limpar(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    while inicio < fim and texto[inicio].isspace():
        inicio += 1
    while fim > inicio and texto[fim - 1].isspace():
        fim -= 1
    return inicio, fim


def _limites(texto: str, inicio: int, fim: int, nivel: int) -> list[int]:
    limites = [inicio]
    for match in _SEPARADORES[nivel].finditer(texto, inicio, fim):
        if nivel == 2 and match.group()[0] == "." and _ABREVIACAO.search(texto[inicio : match.start() + 1]):
            continue
        if inicio < match.end() < fim:
            limites.append(match.end())
    limites.append(fim)
    return limites


def _quebrar(texto: str, inicio: int, fim: int, nivel: int = 0) -> list[tuple[int, int]]:
    inicio, fim = _limpar(texto, inicio, fim)
    if inicio >= fim:
        return []
    if n_tokens(texto[inicio:fim]) <= Config.max_tokens:
        return [(inicio, fim)]
    if nivel < len(_SEPARADORES):
        limites = _limites(texto, inicio, fim, nivel)
        if len(limites) > 2:
            return [span for a, b in zip(limites, limites[1:]) for span in _quebrar(texto, a, b, nivel + 1)]
        return _quebrar(texto, inicio, fim, nivel + 1)

    # Fallback terminal: só aqui precisamos do offset_mapping do tokenizer fast.
    # ponytail: recontagem pode ser quadrática num bloco sem separadores; perfilar
    # antes de trocar por busca binária, que pode violar o teto de 400 tokens.
    partes = []
    while inicio < fim:
        mapping = tokenizer()(texto[inicio:fim], add_special_tokens=False, return_offsets_mapping=True).offset_mapping
        if len(mapping) <= Config.max_tokens:
            partes.append(_limpar(texto, inicio, fim))
            break
        limite = inicio + mapping[Config.max_tokens - 1][1]
        limite = min(limite, fim)
        while limite > inicio and n_tokens(texto[inicio:limite].rstrip()) > Config.max_tokens:
            limite -= 1
        if limite == inicio:
            raise ValueError("token do tokenizer excede max_tokens")
        parte = _limpar(texto, inicio, limite)
        if parte[0] < parte[1]:
            partes.append(parte)
        inicio = limite
        while inicio < fim and texto[inicio].isspace():
            inicio += 1
    return partes


def _secoes(texto: str) -> list[tuple[int, int]]:
    limites = [0]
    inicio = 0
    for linha in texto.splitlines(keepends=True):
        limpa = linha.rstrip("\n")
        if inicio and len(limpa) <= 80 and _TITULO.match(limpa) and not limpa.endswith((".", ":", ";", ",")):
            limites.append(inicio)
        inicio += len(linha)
    limites.append(len(texto))
    return list(zip(limites, limites[1:]))


def chunkar(canonico: str) -> list[Trecho]:
    spans: list[tuple[int, int]] = []
    for inicio, fim in _secoes(canonico):
        unidades = _quebrar(canonico, inicio, fim)
        agrupados: list[tuple[int, int]] = []
        for s, e in unidades:
            if agrupados and n_tokens(canonico[agrupados[-1][0]:e].strip()) <= Config.max_tokens:
                agrupados[-1] = (agrupados[-1][0], e)
            else:
                agrupados.append((s, e))
        # Uma passada de fusão do piso: anterior primeiro, depois o seguinte.
        i = 0
        while i < len(agrupados):
            s, e = agrupados[i]
            if n_tokens(canonico[s:e]) < Config.min_tokens and len(agrupados) > 1:
                if i and n_tokens(canonico[agrupados[i - 1][0]:e].strip()) <= Config.max_tokens:
                    agrupados[i - 1] = (agrupados[i - 1][0], e)
                    agrupados.pop(i)
                    i = max(0, i - 1)
                    continue
                if i + 1 < len(agrupados) and n_tokens(canonico[s:agrupados[i + 1][1]].strip()) <= Config.max_tokens:
                    agrupados[i + 1] = (s, agrupados[i + 1][1])
                    agrupados.pop(i)
                    continue
                if i:
                    anterior, _ = agrupados[i - 1]
                    melhor = None
                    for m in _SEPARADORES[2].finditer(canonico, anterior, s):
                        if m.group()[0] == "." and _ABREVIACAO.search(canonico[anterior:m.start() + 1]):
                            continue
                        esquerda = _limpar(canonico, anterior, m.end())
                        direita = _limpar(canonico, m.end(), e)
                        a = n_tokens(canonico[esquerda[0]:esquerda[1]])
                        b = n_tokens(canonico[direita[0]:direita[1]])
                        if Config.min_tokens <= min(a, b) and max(a, b) <= Config.max_tokens:
                            candidato = (abs(a - b), esquerda, direita)
                            if melhor is None or candidato[0] < melhor[0]:
                                melhor = candidato
                    if melhor is not None:
                        agrupados[i - 1], agrupados[i] = melhor[1:]
            i += 1
        spans.extend((s, e) for s, e in agrupados if any(c.isalnum() for c in canonico[s:e]))
    return [Trecho(i, s, e, canonico[s:e], n_tokens(canonico[s:e])) for i, (s, e) in enumerate(spans)]
