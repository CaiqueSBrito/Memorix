from pathlib import Path

from huggingface_hub import hf_hub_download
from laya import Router

from ..config.config import ConfigLaya

router = Router(models=ConfigLaya.model, preload=False, lang_guess=ConfigLaya.language, device="cuda")


def pin_local_checkpoint():
    """Resolve the cached pinned checkpoint only when classification is requested."""
    config_file = hf_hub_download(ConfigLaya.model["multilingual"], "rl_agent_config.json",
                                  revision=ConfigLaya.revision, local_files_only=True)
    router.models["multilingual"] = str(Path(config_file).parent)