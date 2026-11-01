"""Local normalized BGE-M3 dense vectors; revision matches the ingestion tokenizer."""
from functools import lru_cache

from ..config.config import ConfigIngestao

MODEL = ConfigIngestao.tokenizer
REVISION = ConfigIngestao.revision
MODEL_ID = f"{MODEL}@{REVISION}"


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL, revision=REVISION, local_files_only=True,
                                      dtype=torch.float16 if device == "cuda" else torch.float32).to(device).eval()
    return tokenizer, model, device


def embed(texts: list[str]) -> list[list[float]]:
    import torch
    import torch.nn.functional as F

    tokenizer, model, device = _model()
    vectors = []
    for start in range(0, len(texts), 8):
        batch = tokenizer(texts[start:start + 8], padding=True, truncation=True,
                          max_length=512, return_tensors="pt").to(device)
        with torch.inference_mode():
            dense = F.normalize(model(**batch).last_hidden_state[:, 0].float(), p=2, dim=1)
        vectors.extend(dense.cpu().tolist())
    return vectors


def unload():
    """Release VRAM before Ollama loads llama3 on a 6 GiB GPU."""
    _model.cache_clear()
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
