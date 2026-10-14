"Configuration for the RAG system"

class ConfigLaya:
    language = "multilingual"
    model = {
        "multilingual": "Riupul/laya-multilingual-finetuning-memorix"
    }


class ConfigIngestao:
    strategy = "estrutural-v1"
    extractor = "texto-bruto@v1"
    max_tokens = 400
    min_tokens = 80
    overlap = 0
    tokenizer = "BAAI/bge-m3"
    revision = "5617a9f61b028005a4858fdac845db406aefb181"
    trace_path = "backend/logs/rag-rastro.jsonl"