"""Pedido explícito para gerar material educacional a partir do acervo."""

from dataclasses import dataclass


CONTENT_TYPES = ("flashcards", "multipla_escolha", "verdadeiro_falso", "aula")
DIFFICULTIES = ("basica", "intermediaria", "avancada")


@dataclass(frozen=True)
class GenerationRequest:
    kind: str
    topic: str
    count: int = 5
    difficulty: str = "basica"

    def __post_init__(self) -> None:
        if self.kind not in CONTENT_TYPES:
            raise ValueError("Tipo de material não suportado.")
        if not isinstance(self.topic, str) or not self.topic.strip():
            raise ValueError("Informe um tema não vazio.")
        if type(self.count) is not int or not 1 <= self.count <= 20:
            raise ValueError("A quantidade deve ser um inteiro entre 1 e 20.")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("Dificuldade não suportada.")
