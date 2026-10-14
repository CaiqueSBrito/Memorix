"""Chunking estrutural com offsets em code points do texto canônico."""

import re
from dataclasses import dataclass
from functools import lru_cache

from ..config.config import ConfigIngestao as Config

_HEADING = re.compile(r"^(?:#{1,6}\s+\S|\d+(?:\.\d+)*\.?\s+\S)")
_ABBREVIATION = re.compile(r"(?<!\w)(?i:Sr|Sra|Dr|art|p|pág|ex|fig|nº|cf)\.$|(?<!\w)[A-ZÁÉÍÓÚ]\.$")
_SEPARATORS = (
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


def n_tokens(content: str) -> int:
    return len(tokenizer()(content, add_special_tokens=False).input_ids)


def _trim_span(content: str, start: int, end: int) -> tuple[int, int]:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end


def _split_boundaries(content: str, start: int, end: int, level: int) -> list[int]:
    boundaries = [start]
    for match in _SEPARATORS[level].finditer(content, start, end):
        if level == 2 and match.group()[0] == "." and _ABBREVIATION.search(content[start : match.start() + 1]):
            continue
        if start < match.end() < end:
            boundaries.append(match.end())
    boundaries.append(end)
    return boundaries


def _split_span(content: str, start: int, end: int, level: int = 0) -> list[tuple[int, int]]:
    start, end = _trim_span(content, start, end)
    if start >= end:
        return []
    if n_tokens(content[start:end]) <= Config.max_tokens:
        return [(start, end)]
    if level < len(_SEPARATORS):
        boundaries = _split_boundaries(content, start, end, level)
        if len(boundaries) > 2:
            return [span for a, b in zip(boundaries, boundaries[1:]) for span in _split_span(content, a, b, level + 1)]
        return _split_span(content, start, end, level + 1)

    # Fallback terminal: só aqui precisamos do offset_mapping do tokenizer fast.
    # ponytail: recontagem pode ser quadrática num bloco sem separadores; perfilar
    # antes de trocar por busca binária, que pode violar o teto de 400 tokens.
    parts = []
    while start < end:
        mapping = tokenizer()(content[start:end], add_special_tokens=False, return_offsets_mapping=True).offset_mapping
        if len(mapping) <= Config.max_tokens:
            parts.append(_trim_span(content, start, end))
            break
        boundary = start + mapping[Config.max_tokens - 1][1]
        boundary = min(boundary, end)
        while boundary > start and n_tokens(content[start:boundary].rstrip()) > Config.max_tokens:
            boundary -= 1
        if boundary == start:
            raise ValueError("token do tokenizer excede max_tokens")
        part = _trim_span(content, start, boundary)
        if part[0] < part[1]:
            parts.append(part)
        start = boundary
        while start < end and content[start].isspace():
            start += 1
    return parts


def _sections(content: str) -> list[tuple[int, int]]:
    boundaries = [0]
    start = 0
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if start and len(stripped) <= 80 and _HEADING.match(stripped) and not stripped.endswith((".", ":", ";", ",")):
            boundaries.append(start)
        start += len(line)
    boundaries.append(len(content))
    return list(zip(boundaries, boundaries[1:]))


def chunking(canonical_text: str) -> list[Trecho]:
    spans: list[tuple[int, int]] = []
    for start, end in _sections(canonical_text):
        units = _split_span(canonical_text, start, end)
        grouped: list[tuple[int, int]] = []
        for s, e in units:
            if grouped and n_tokens(canonical_text[grouped[-1][0]:e].strip()) <= Config.max_tokens:
                grouped[-1] = (grouped[-1][0], e)
            else:
                grouped.append((s, e))
        # Uma passada de fusão do piso: anterior primeiro, depois o seguinte.
        i = 0
        while i < len(grouped):
            s, e = grouped[i]
            if n_tokens(canonical_text[s:e]) < Config.min_tokens and len(grouped) > 1:
                if i and n_tokens(canonical_text[grouped[i - 1][0]:e].strip()) <= Config.max_tokens:
                    grouped[i - 1] = (grouped[i - 1][0], e)
                    grouped.pop(i)
                    i = max(0, i - 1)
                    continue
                if i + 1 < len(grouped) and n_tokens(canonical_text[s:grouped[i + 1][1]].strip()) <= Config.max_tokens:
                    grouped[i + 1] = (s, grouped[i + 1][1])
                    grouped.pop(i)
                    continue
                if i:
                    previous, _ = grouped[i - 1]
                    best = None
                    for m in _SEPARATORS[2].finditer(canonical_text, previous, s):
                        if m.group()[0] == "." and _ABBREVIATION.search(canonical_text[previous:m.start() + 1]):
                            continue
                        left = _trim_span(canonical_text, previous, m.end())
                        right = _trim_span(canonical_text, m.end(), e)
                        a = n_tokens(canonical_text[left[0]:left[1]])
                        b = n_tokens(canonical_text[right[0]:right[1]])
                        if Config.min_tokens <= min(a, b) and max(a, b) <= Config.max_tokens:
                            candidate = (abs(a - b), left, right)
                            if best is None or candidate[0] < best[0]:
                                best = candidate
                    if best is not None:
                        grouped[i - 1], grouped[i] = best[1:]
            i += 1
        spans.extend((s, e) for s, e in grouped if any(c.isalnum() for c in canonical_text[s:e]))
    return [Trecho(i, s, e, canonical_text[s:e], n_tokens(canonical_text[s:e])) for i, (s, e) in enumerate(spans)]
