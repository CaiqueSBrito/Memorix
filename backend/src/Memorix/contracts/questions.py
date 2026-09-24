"Questions and answers for the NLP step"

from typing import TypedDict, Dict

class LayaQuestion(TypedDict):
    question: str
    type: str
    instructions: str
    answers: Dict[str, str]

