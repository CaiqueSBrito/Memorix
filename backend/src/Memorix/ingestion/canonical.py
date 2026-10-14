"""Texto canônico: todos os offsets são calculados depois desta transformação."""

import hashlib
import re
import unicodedata


def canonicalize(content: str) -> str:
    content = content.replace("\ufeff", "")
    content = "".join(c for c in content if ord(c) >= 32 or c in "\n\t\r")
    content = unicodedata.normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n"))
    content = re.sub(r"[ \t]+(?=\n|$)", "", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def doc_sha256(canonical_text: str) -> str:
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
