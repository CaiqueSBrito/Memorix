import os

from laya import Router
from ..config.config import ConfigLaya

router = Router(
    models=ConfigLaya.model,
    preload=False,
    lang_guess=ConfigLaya.language,
    device="cuda",
    token=os.getenv("HF_TOKEN"),
)