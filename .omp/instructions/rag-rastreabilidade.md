# Auditoria e rastreabilidade — sistema RAG

Toda resposta do Memorix deve poder ser reconstruída: de qual documento veio, quais trechos foram usados, com qual configuração, e por que saiu daquele jeito. Etapa sem rastro = etapa incompleta.

## Identificadores

- `trace_id` — um por requisição (pergunta do aluno ou geração de item); propagado por todas as etapas.
- `doc_id` + `doc_sha256` — por documento ingerido; muda o conteúdo → novo hash.
- `chunk_id` — estável, derivado de `doc_id` + posição; guarda `offset_inicio`/`offset_fim` no documento.
- Configuração do índice — modelo/revisão de embedding, estratégia de chunking e configuração FTS; decisão humana da 003: não criar campo `index_version`.
- `prompt_version` — hash do template do prompt.

## Registro por etapa

Cada etapa emite **um registro estruturado** (JSON Lines) com, no mínimo: `trace_id`, `etapa`, `timestamp`, `duracao_ms`, `status` (ok/erro) e `erro` quando houver.

| Etapa | Campos adicionais |
| --- | --- |
| Ingestão | `doc_id`, `doc_sha256`, origem, tamanho, extrator usado |
| Chunking | `doc_id`, estratégia e parâmetros, `chunk_id`s gerados com offsets |
| Embedding / indexação | modelo e revisão, estratégia de chunking/configuração FTS, quantidade de vetores |
| Retrieval | consulta (ou seu hash), `k`, filtros, `chunk_id`s retornados com score e posição |
| Reranking | modelo, ordem antes → depois, scores |
| Compreensão pedagógica | tipo explícito ou rótulo Laya, probabilidades da escolha, modelo/revisão; sem texto do aluno |
| Gate de suficiência | modelo/revisão do sinal, limiar medido, `n_sup`, decisão de admitir/recusar |
| Montagem do prompt | `prompt_version`, `chunk_id`s incluídos, tokens de entrada |
| Geração | provider, modelo, parâmetros (temperatura etc.), tokens de saída, custo estimado |
| Validação | schema/regras aplicadas, resultado, reparos feitos |
| Resposta | cada afirmação/item gerado → `chunk_id`s que a sustentam; item sem fonte é marcado e não é entregue como fato |
| Correção dissertativa | modelo, hash da rubrica/versão, referências de fonte, estado da correção; nunca copiar resposta do aluno |

## Regras

- Rastro é requisito da feature: a tarefa de IA só termina com teste que prova que cada etapa tocada emite seu registro com os campos acima (ver `teste-primeiro.md`).
- Registros são somente de acréscimo; nunca reescritos ou apagados pelo código da aplicação.
- Sem segredos (`HF_TOKEN`, chaves) em registro algum.
- Conteúdo do aluno por referência (`doc_id`, `chunk_id`, hash), não copiado para o log; texto só no armazenamento do próprio documento.
- Falha em uma etapa também é registrada, com o `trace_id` — erro silencioso é proibido.
- Implementação inicial: `logging` da stdlib com formatação JSON, um arquivo JSONL. Ferramenta dedicada de observabilidade (OpenTelemetry, Langfuse etc.) só quando a stdlib não bastar — e é decisão do humano.
