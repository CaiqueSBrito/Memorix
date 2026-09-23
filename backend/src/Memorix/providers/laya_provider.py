import os

from laya import Router
from ..config.config import ConfigLaya
router = Router(
    models={
        "multilingual": "convaiinnovations/laya",
    },
    preload=True,
    lang_guess=ConfigLaya.language,
    device="cuda",
    token=os.getenv("HF_TOKEN"),
)

resposta = router.predict(
    state="Olá, como você está?",
    questions={
        "is_greeting": {
            "type": "noul",
            "instructions": "A mensagem é uma saudação?",
            "criteria": {
                "true": "é uma saudação",
                "false": "não é uma saudação",
            },
        }
    },
)
print(resposta)