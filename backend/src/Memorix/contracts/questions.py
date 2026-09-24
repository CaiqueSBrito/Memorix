"Questions and answers for the NLP step"

from typing import Literal, TypedDict

class LayaChoiceQuestion(TypedDict):
    type: Literal["choice"]
    instructions: str
    criteria: dict[str, str]



CONTENT_TYPE: dict[str, LayaChoiceQuestion] = {
        "o que devemos gerar": {
            "type": "choice",
            "instructions": "Qual tipo de material de estudo o usuário está pedindo?",
            "criteria": {
                "flashcards": "o usuário quer gerar flashcards",
                "exercicios": "o usuário quer gerar exercícios",
                "aula": "o usuário quer gerar uma aula",
                "outro": "o usuário quer gerar outro tipo de material",
            },
        }
    }
