"""BGE multilingual cross-encoder logits for retrieval and sufficiency gating."""
from functools import lru_cache

MODEL = "BAAI/bge-reranker-v2-m3"
REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, revision=REVISION, local_files_only=True,
        dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device).eval()
    return tokenizer, model, device


def score(query: str, passages: list[str]) -> list[float]:
    import torch

    if not passages:
        return []
    tokenizer, model, device = _model()
    logits = []
    for start in range(0, len(passages), 8):
        pairs = [[query, passage] for passage in passages[start:start + 8]]
        batch = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt").to(device)
        with torch.inference_mode():
            logits.extend(model(**batch).logits.float().flatten().cpu().tolist())
    return logits


def unload():
    _model.cache_clear()
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
