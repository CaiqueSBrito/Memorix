"""Fluxo local: recuperar evidências, gerar e validar antes de entregar."""

from ..contracts.generation import GenerationRequest
from ..generation_adapter.material import build_messages, response_schema, validate_material
from ..ingestion.corpus import Corpus
from ..providers.local_llm import LocalLLM


def generate_material(
    corpus: Corpus,
    request: GenerationRequest,
    *,
    client: LocalLLM,
    retrieval_limit: int = 5,
) -> dict:
    hits = corpus.search(request.topic, limit=retrieval_limit)
    if not hits:
        raise ValueError("Nenhum trecho encontrado para o tema; não há fontes para gerar material.")
    payload = client.complete(
        messages=build_messages(request, hits),
        schema=response_schema(request, hits),
    )
    return validate_material(payload, request, hits)
