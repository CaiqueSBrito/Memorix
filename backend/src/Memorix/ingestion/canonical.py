"""Texto canônico: todos os offsets são calculados depois desta transformação."""

import hashlib
import re
import unicodedata


def canonicalizar(texto: str) -> str:
    texto = texto.replace("\ufeff", "")
    texto = "".join(c for c in texto if ord(c) >= 32 or c in "\n\t\r")
    texto = unicodedata.normalize("NFC", texto.replace("\r\n", "\n").replace("\r", "\n"))
    texto = re.sub(r"[ \t]+(?=\n|$)", "", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def doc_sha256(canonico: str) -> str:
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
