# 003 — Pesquisa da estratégia de retrieval (antes de escolher o modelo)
Goal: 6 — Pipeline RAG (desenho); alimenta o 1.3 — Retrieval medido (parte de desenho)        Trilha: IA        Estado: Concluída (aceite do humano em 2026-09-24)

## Objetivo

Decidir no papel como o Memorix vai recuperar trechos do acervo e, só então, recomendar o modelo de embedding. O pedido vem literalmente do humano, no gate 1 da 002: "precisamos de uma pesquisa ampla considerando como vai ser feito o retrieval, precisamos pensar primeiro como faremos o retrieval antes de decidir o modelo".

É pesquisa de mesa: sem código de produto, sem banco e sem download de modelo. A tarefa entrega:

- opções comparadas;
- uma recomendação por pergunta;
- o protocolo de medição que a tarefa proposta 007 vai executar;
- o impacto de cada opção no schema (migração `0002`).

O modelo definitivo sai da medição (princípio 4 do pipeline), não desta tarefa.

## Critérios de aceitação

- [x] Cada pergunta (P1–P6) compara pelo menos 2 opções e termina em 1 recomendação. Evidência: "Resultado da pesquisa" §2 (resumo) e as tabelas completas por opção em `.omp/tasks/003-anexos/P1-hibrido.json` … `P6-supabase.json`. As opções são comparadas em:
  - qualidade esperada em PT-BR;
  - latência;
  - RAM/VRAM no hardware-alvo;
  - licença;
  - compatibilidade com pgvector/Supabase;
  - para opções via API: custo por 1M tokens e o que isso implica para LGPD.
- As perguntas:
  - **P1:** denso só ou híbrido (denso + lexical: FTS `portuguese` do Postgres ou sparse do BGE-M3). No híbrido, como fundir os resultados (ex.: RRF).
  - **P2:** modelos de embedding candidatos para PT-BR, **locais e via API**, com dimensão, limite de tokens, licença e custo.
  - **P3:** chunking: tamanho, sobreposição, corte por estrutura e se parent/child vale a pena. Inclui um chunking provisório para a 004.
  - **P4:** reranker: sim ou não, local ou API.
  - **P5:** `k` e o sinal de score para o gate de suficiência ("não está no acervo").
  - **P6:** Supabase: versão do pgvector, `sparsevec`/`halfvec`, limite de dimensões do HNSW, FTS `portuguese` e `unaccent`.
- [x] Todo fato técnico cita fonte primária (URL). O que não foi verificado fica marcado [INFERÊNCIA]. Evidência: URLs em §2–§4 e nos JSON dos pesquisadores; [INFERÊNCIA] mantidas. Exceções registradas: regra de três (Wikipedia, fórmula conferida) e gist de 2023 da Supabase (não oficial, possivelmente desatualizado).
- [x] Local × API comparados lado a lado. Evidência: §4.
  - Hardware local: RTX 4050 Laptop 6 GiB.
  - API: o humano admite usar chave de API (gate 2, resposta 5).
  - O material do acervo é do admin; a consulta do aluno pode conter texto escrito por menor.
  - Adotar API continua sendo decisão do humano (envio de dados a terceiros).
  - A recomendação indica o caminho local equivalente.
- [x] Protocolo de medição da 007 definido (evidência: §5):
  - formato do caso: consulta, trecho esperado por `doc_sha256` + intervalo de offsets, ou "fora do acervo";
  - métricas: recall@5, MRR@10, latência p95 e comportamento fora do acervo;
  - baseline denso-só;
  - uma variável por vez;
  - critério numérico de decisão.
- [x] Hipóteses testáveis listadas para a 007. Evidência: §6 (H1–H27, deduplicadas de P1–P6).
- [x] Para cada opção, o impacto no schema: colunas e índices da `0002`. Confirmar que a `0001` da 002 não muda. Evidência: §7.
- [x] Nenhum código, migração, banco ou download de modelo. Evidência: os pesquisadores só leram e rodaram verificações em memória (stemmer Snowball do sdist PyPI, protótipo de chunker, numpy 10k×1024, compilação offline do DDL); a consolidação editou só este arquivo.

## Fora do escopo

- Medir modelos ou rodar benchmark: fica para a 007, com os casos da 006.
- Implementar reranking, gate de suficiência, `pedagogical_understand` e geração.
- Adotar provider pago: exige decisão do humano. Aqui a API só é comparada.

## Esclarecer

Nenhum aberto.
- Volume do acervo: o humano não respondeu. A pesquisa assume até ~10 mil trechos no MVP e marca isso como suposição.
- Material real para os evals: virá de um scraping posterior (gate 2, resposta 16) e afeta a 006, não esta tarefa.

## Plano

| Passo | Quem | Arquivos | Status |
| --- | --- | --- | --- |
| 1. Gate humano: plano | humano | — | Concluído ("sim", gate 2; tempo indeterminado só para esta tarefa) |
| 2. 6 acionamentos paralelos, um por pergunta (P1–P6), só leitura + pesquisa web com fontes primárias, sem limite de tempo | `ai-rag-specialist` ×6 | `.omp/tasks/003-anexos/` (saídas brutas) | Concluído. P2 e P6 caíram por rate limit (429) e foram retomados |
| 3. Consolidação: coerência entre as recomendações (modelo × dimensão × limite do HNSW × hardware), protocolo, hipóteses e impacto no schema. O resultado é escrito na seção "Resultado da pesquisa" | `ai-rag-specialist` (`Orch002.Consol003`) | esta tarefa | Concluído |
| 4. Revisar: o orquestrador confere cada critério (feito). Parecer pedagógico sobre os 4 pontos do §8, a pedido da consolidação. **Aceite do humano** | `orchestrator`, `pedagogy-specialist`, humano | esta tarefa | Aguardando o humano |
| 5. Registrar: recomendações aceitas vão para `produto.md` (seção Pipeline RAG), marcadas como proposta; atualizar `progresso.md` | `orchestrator` | `.omp/context/produto.md`, `.omp/progress/progresso.md` | — |

## Resultado da pesquisa

Consolidação do `ai-rag-specialist` (passo 3). Os detalhes e todas as fontes estão em `.omp/tasks/003-anexos/P1-hibrido.json` … `P6-supabase.json`, que são as saídas brutas dos pesquisadores. Nada foi medido: latência e VRAM locais são estimativas por FLOPs e ficam [INFERÊNCIA] até a 007. O volume de ~10 mil trechos é SUPOSIÇÃO.

### 1. Pipeline recomendado

O tema da consulta (saída do `pedagogical_understand`) vira um vetor denso local com `BAAI/bge-m3` (1024, normalizado, sem prefixo). No Supabase, uma única query com CTEs roda dois ramos: denso por busca exata (`embedding <=> :q`, sem índice ANN, top-30) e lexical por FTS `pt_unaccent` (tsquery em OR, `ts_rank_cd`, GIN, top-30). Os ramos são fundidos por RRF (k=60, pesos 1:1, desempate por `chunk_id`), e a query devolve também o cosseno e o `ts_rank_cd` brutos, que vão para o rastro. O pool `k_cand=30` passa pelo `bge-reranker-v2-m3` local (fp16, `max_length` 512), que reordena e dá um logit por trecho. O gate conta `n_sup = #{logit ≥ τ_rr}`: com `n_sup = 0` o aluno recebe "não está no acervo" e a geração não é chamada; senão entram `min(k_ger, n_sup)` trechos, ordenados por escore. Esse é o desenho-alvo. O baseline da 007 é o denso-só, e cada peça só entra se passar no critério do §5.

```text
consulta → pedagogical_understand (tema)
  → embedding bge-m3 (1024, local, GPU)
  → Supabase, 1 query:
       denso exato <=> (top-30) ─────────┐
       FTS pt_unaccent, OR, GIN (top-30) ┴→ RRF k=60 → pool k_cand=30 (+ cosseno e ts_rank_cd brutos)
  → reranker bge-reranker-v2-m3 (local, 512) → logit por trecho
  → gate: n_sup = #{logit ≥ τ_rr}; n_sup = 0 → "não está no acervo" (sem geração)
  → k_ger = min(8 questão/flashcard ou 15 aula, n_sup) → geração
Cada seta grava rastro JSONL: hash da consulta, chunk_ids, scores, modelos, duracao_ms.
```

### 2. Recomendação por pergunta

| P | Escolhido | Descartado (motivo) | Fontes principais |
| --- | --- | --- | --- |
| P1 | Híbrido denso + FTS `pt_unaccent` (stopwords → unaccent → `portuguese_stem`), tsquery em OR, RRF k=60, 30 por ramo. Denso-só fica como baseline. | Sparse do BGE-M3 como ramo padrão: amarra o lexical ao modelo e não normaliza acento [INFERÊNCIA]; vira H11. `pg_search`/BM25: não existe no Supabase (e é AGPL). Soma ponderada: escalas de cosseno × `ts_rank_cd` exigem calibração por modelo. | https://supabase.com/docs/guides/ai/hybrid-search · https://github.com/pgvector/pgvector#hybrid-search · https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf · https://www.postgresql.org/docs/current/textsearch-dictionaries.html · https://www.postgresql.org/docs/current/unaccent.html · https://arxiv.org/html/2404.06976 · https://github.com/supabase/postgres/tree/develop/nix/ext |
| P2 | `BAAI/bge-m3` denso 1024, local (MIT, 8192 tokens, ~1,1 GB FP16; MKQA pt R@100 76,3 contra 77,5 do OpenAI-3). Desafiantes: `Qwen/Qwen3-Embedding-0.6B` em 1024 (Apache-2.0; melhor retrieval aberto no MTEB-PT, 78,9) e OpenAI `text-embedding-3-large` com `dimensions=1024` (só com autorização). | Gemini API: os termos proíbem apps acessíveis a menores de 18. `jina-embeddings-v3`: CC BY-NC. Serafim: 128 tokens e retrieval 54,9. e5-large(-instruct): cosseno comprimido em 0,7–1,0 e abaixo do Qwen3 no MTEB-PT. | https://huggingface.co/BAAI/bge-m3 · https://arxiv.org/abs/2402.03216 · https://arxiv.org/abs/2607.04071 · https://huggingface.co/Qwen/Qwen3-Embedding-0.6B · https://github.com/embeddings-benchmark/results · https://ai.google.dev/gemini-api/terms · https://huggingface.co/jinaai/jina-embeddings-v3 |
| P3 | `estrutural-v1`: recursivo por estrutura, títulos como limite rígido, `max_tokens` 400, `min_tokens` 80, overlap 0, contagem no tokenizer XLM-R do bge-m3, offsets `[s,e)` em code points sobre o texto canônico NFC. É o chunking provisório da 004. | Semântico: ganho inconsistente (Vectara). Late chunking: bge-m3 usa pooling CLS e o e5 aceita só 512. Parent/child: sem ganho (sentence window foi pior em PT-BR); vira H23. Proposições: quebram os offsets. Contextual via LLM: custo e envio do acervo; vira H24. | https://arxiv.org/abs/2604.04948 · https://research.trychroma.com/evaluating-chunking · https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/ · https://arxiv.org/abs/2410.13070 · https://arxiv.org/abs/2401.07883 |
| P4 | `BAAI/bge-reranker-v2-m3` local (Apache-2.0), fp16, `max_length` 512, `k_cand=30`, ligado por config; a adoção sai da 007. Desafiantes: `Qwen3-Reranker-0.6B` (qualidade) e `gte-multilingual-reranker-base` (latência). | `bge-reranker-v2-gemma`/`minicpm`: ~5 GB, não cabem com o embedding. Jina v2/v3: CC BY-NC; o v3 é listwise, ruim para limiar [INFERÊNCIA]. APIs Cohere/Voyage/Jina: LGPD; só como desafiante autorizado. | https://huggingface.co/BAAI/bge-reranker-v2-m3 · https://huggingface.co/Qwen/Qwen3-Reranker-0.6B · https://qwenlm.github.io/blog/qwen3-embedding/ · https://docs.cohere.com/docs/reranking-best-practices · https://docs.voyageai.com/docs/faq |
| P5 | Gate S3+S4: logit do cross-encoder e `n_sup ≥ 1`; `τ_rr` calibrado na 007 (FAR = 0 nos casos fora, menor FRR, leave-one-out), guardado como constante chaveada por (`embedding_model`, reranker). `k_cand=30`; `k_ger` 8 (questão/flashcard) e 15 (aula), sempre ≤ `n_sup`; ordem por escore; sem MMR. | Cosseno absoluto (S1): não é portável entre modelos; fica só no baseline e como fallback sem reranker. Margem top1−top5: QPP é fraco em IR neural. LLM como gate primário: custo, injeção, LGPD. Recusa pelo próprio gerador: no RGB, rejeição ≤ 45%. | https://arxiv.org/abs/2401.15884 · https://arxiv.org/abs/2411.06037 · https://arxiv.org/abs/2309.01431 · https://arxiv.org/abs/2302.09947 · https://huggingface.co/BAAI/bge-large-en-v1.5 · https://docs.cohere.com/docs/reranking-best-practices |
| P6 | pgvector 0.8.2 (imagem Supabase atual). `vector(1024)` com busca exata, sem HNSW/IVFFlat. `tsv` gerado + GIN. Extensões no schema `extensions`. Conexão pelo Supavisor em session mode (IPv4) com `postgresql+psycopg2`. | HNSW na 0002 (ver 3a). IVFFlat: o Supabase prefere HNSW e não há ganho com 10k. `halfvec` no baseline: arredonda o score do gate; vira H25. `pg_search`: ausente. | https://github.com/pgvector/pgvector · https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md · https://github.com/supabase/postgres/blob/develop/nix/ext/versions.json · https://supabase.com/docs/guides/ai/going-to-prod · https://supabase.com/docs/guides/ai/vector-indexes/hnsw-indexes · https://supabase.com/docs/guides/database/connecting-to-postgres |

### 3. Coerência e divergências resolvidas

| Tema | Opções | Decisão | Motivo |
| --- | --- | --- | --- |
| (a) Índice vetorial | HNSW `vector_cosine_ops` m=16/ef_construction=64 (1ª rodada da 002, "válido para a 008") × busca exata sem índice (P6) | **Busca exata na 0002.** HNSW fica atrás de gatilho: p95 do ramo denso > 100 ms ou acervo > ~100 mil trechos, e só com pgvector ≥ 0.8.4. Os parâmetros m=16/ef_construction=64 continuam a referência para esse dia. | ~10 mil × 1024 ≈ 41 MB de vetores. A busca exata devolve o top-k verdadeiro e a distância real, que o gate e o rastro usam. `k_cand` até 50 funciona sem mexer em `hnsw.ef_search` (padrão 40). Não há pós-filtro. A 0.8.2 do Supabase não tem as correções de corrupção do HNSW em VACUUM (0.8.3/0.8.4). E o recall do ANN sai das variáveis da 007. Criar o índice depois é `CREATE INDEX CONCURRENTLY`, sem mudar a coluna. A posição da 1ª rodada da 002 fica revista. |
| (b) Onde fica o vetor | Coluna em `chunks` + `embedding_model` (P6; forma aprovada pelo humano: "embedding só no chunk", nome `embedding_model`) × tabela `chunk_embeddings` (P2) | **Coluna em `chunks`.** Se a tabela separada for escolhida, a chave é (`chunk_id`, `embedding_model`), nunca `index_version`. É ponto de decisão do humano (§8), porque a alternativa muda uma forma aprovada. | Em produção há um modelo por vez. A reingestão da 004 já apaga e reinsere os chunks numa transação, então chunk e vetor nascem juntos. Vetor, `tsv` e texto na mesma linha dão uma query sem JOIN. A 007 compara modelos reindexando (~2–3 min para 10k [INFERÊNCIA]). A tabela só compensa se for preciso manter dois modelos vivos ao mesmo tempo (troca sem janela). |
| (c) Chunking do baseline | P5: "~300 tokens, overlap 10–15%" × P3: `estrutural-v1` 400/80/0 | **`estrutural-v1` (max 400, min 80, overlap 0).** | A P5 citou a posição inicial da P3 no hub, que a própria P3 revisou com as tabelas da Chroma (recursivo 400/0: recall 89,5; 400/200: 88,1). Com overlap 0, cada caractere pertence a um só chunk e o acerto por offsets fica sem ambiguidade. "~300" é a média esperada com teto 400 [INFERÊNCIA]. O overlap vira H5. |
| (d) k do RRF | 60 (P1, Cormack 2009) × 50 (exemplo do Supabase) | **k=60**, fixo e fora das variáveis da 007. | É o único valor com evidência empírica, e o próprio Cormack diz que k "não é crítico". O 50 do Supabase é um exemplo sem justificativa. |
| (e) Config de texto | P1: dicionário `pt_stop` (`simple`, stopwords `portuguese`, ACCEPT=false) → `unaccent` → `portuguese_stem` × P6: padrão da doc do unaccent (`unaccent` → `portuguese_stem`) | **Config da P1.** | Com o `unaccent` antes, ~30 stopwords acentuadas ("não", "também", "você", "são") perdem o acento, deixam de casar com a stoplist e vazam para o índice (verificado pela P1 contra a stoplist Snowball). A P6 já tinha deixado a ordem para a P1. Custo: um dicionário a mais. |
| (f) Critério numérico | Limiares por hipótese de P1/P3/P4 (+3 p.p., +0,03) × resolução da amostra (12 respondíveis: 1 caso = 8,3 p.p.) | **Critério geral da P5** (≥ 2 casos líquidos) enquanto houver < 40 respondíveis. Os limiares finos voltam com ≥ 40 casos ou com teste pareado (McNemar) [INFERÊNCIA]. | Um limiar de +3 p.p. com 12 casos é menor que um caso, ou seja, é ruído. |
| (g) Pool do banco | NullPool (painel do Supabase, via Orch002) × `pool_size` pequeno + `pool_pre_ping` (P6) | **Pool pequeno + `pool_pre_ping` em session mode** (decisão da 008). | Em session mode o NullPool abre TLS e backend a cada checkout; ele só é necessário em transaction mode [INFERÊNCIA; a recomendação do painel não foi achada em doc oficial]. |

**(h) Coerência modelo × dimensão × tipo × hardware.**

| Peça | Escolha | Dimensão / limite | Tipo no banco | GPU (RTX 4050, 6 GiB) |
| --- | --- | --- | --- | --- |
| Embedding baseline | bge-m3 denso | 1024; 8192 tokens | `vector(1024)`, `<=>` | ~1,1 GB FP16 |
| Desafiante local | Qwen3-Embedding-0.6B | 1024 (MRL); 32k tokens | mesma coluna | ~1,2 GB |
| Desafiante API | OpenAI 3-large, `dimensions=1024` | 1024; 8192 tokens | mesma coluna | 0 (só com autorização) |
| Lexical | FTS `pt_unaccent`; sparse só se o modelo for bge-m3 | chunk ≤ 400 tokens < 1.000 não-zeros do HNSW sparsevec | `tsvector` + GIN; `sparsevec(250002)` condicional | 0 |
| Reranker | bge-reranker-v2-m3 | 512 = consulta + chunk ≤ 400 | — | ~1,1 GB |
| Classifier existente | hoje é o `Router` da Laya com checkpoint fine-tuned próprio (`progresso.md`), e não o mDeBERTa de `produto.md`, que está desatualizado | — | — | ~1 GB [INFERÊNCIA; mesma ordem para os dois] |
| **Total** | | | | ~3,5–4,5 GB [INFERÊNCIA]; um LLM local de geração não cabe junto |

Consequências: (1) os três candidatos de embedding usam `vector(1024)`, então a 0002 pode fixar D=1024 antes do fim da 007; só muda se a 007 escolher um modelo fora da lista. (2) A contagem de tokens do chunk continua no XLM-R mesmo se o Qwen3 vencer, porque o limite que amarra é o do reranker (512 XLM-R). (3) Vetados: Gemini (termos sobre menores), jina-v3 e rerankers Jina (CC BY-NC).

### 4. Local × API

| | Local (recomendado) | API (só desafiante, com decisão do humano) |
| --- | --- | --- |
| Embedding | bge-m3 / Qwen3-0.6B: US$ 0 | Por reindexação de ~3M tokens (10k × ~300): OpenAI 3-large US$ 0,13/1M → ~US$ 0,39; 3-small US$ 0,02/1M → ~US$ 0,06; Cohere embed-v4 US$ 0,12/1M → ~US$ 0,36; Voyage-4 US$ 0,06/1M → ~US$ 0,18 (200M tokens grátis). 100 mil consultas × ~30 tokens ≈ 3M tokens, mesma ordem. |
| Reranker | bge-reranker-v2-m3: US$ 0 | Cohere rerank v4.0: US$ 2,00–2,50 por 1 mil buscas; Voyage rerank-2.5: ~US$ 0,50 e 2.5-lite ~US$ 0,20 por 1 mil buscas; Jina: preço não extraído [INFERÊNCIA]. |
| Latência | Embedding da consulta ~10–25 ms; rerank de 30 pares ~0,25–0,5 s [INFERÊNCIA] | ~100–300 ms por embedding e ~150–400 ms por rerank, com rede Brasil↔EUA [INFERÊNCIA] |
| Dados que saem | Nenhum | A cada busca: a consulta do aluno (possível menor) e, no rerank, os 30 trechos. Embedding via API obriga a consulta a sair, porque não dá para embedá-la localmente em outro espaço vetorial. Única exceção: `voyage-4-large` + `voyage-4-nano` local (afirmação do fornecedor, não verificada). |
| LGPD | Sem terceiro novo além do Supabase | Transferência internacional (art. 33) de dado de criança/adolescente (art. 14: melhor interesse; consentimento específico de um dos pais para criança). https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm |
| Termos | Licenças MIT/Apache-2.0 | OpenAI: sem treino por padrão, logs de 30 dias, ZDR sob aprovação; Services Agreement §3.3(c) proíbe uso por menores sem consentimento dos pais ou responsáveis (https://openai.com/policies/services-agreement/). Cohere: logs de 30 dias, opt-out de treino no painel (https://cohere.com/data-usage-policy). Voyage: por padrão guarda e treina; o opt-out exige cartão e admin (https://docs.voyageai.com/docs/faq). Gemini API: veta apps acessíveis a menores de 18 → descartado (https://ai.google.dev/gemini-api/terms). |

Conclusão: o custo é irrelevante (centavos por reindexação); decidem LGPD e qualidade. **Recomendação: local.** API só como desafiante medido na 007 e com decisão do humano. O caminho local equivalente é Qwen3-Embedding-0.6B e Qwen3-Reranker-0.6B. Na 007 os casos são escritos à mão, sem dado de menor, então medir API ali envia só o acervo do admin e consultas sintéticas. A questão do menor aparece em produção.

### 5. Protocolo da 007

**Casos** em `backend/evals/retrieval/casos.jsonl` (criado pela 006), um por linha:

```json
{"case_id":"ret-0001","suite":"capacidade","tipo":"questionario","classe":"no_acervo","consulta":"quero 5 questoes sobre fases da mitose","tema":"fases da mitose","fora_do_acervo":false,"tags":["sem_acento"],"esperado":[{"doc_sha256":"<64 hex>","offset_start":1200,"offset_end":1650,"ancora":"primeiros ~50 caracteres","essencial":true}],"extrator":"id+versão","nota":"por que o intervalo sustenta o pedido"}
{"case_id":"ret-0013","suite":"capacidade","tipo":"flashcard","classe":"fora_vizinho","consulta":"flashcards sobre meiose","tema":"meiose","fora_do_acervo":true,"esperado":[],"verificacao_ausencia":"FTS dos termos + leitura humana dos 10 primeiros candidatos, com data"}
```

- Classes: `no_acervo`, `fora_distante`, `fora_vizinho`. A classe `parcial` espera a decisão pedagógica (§8).
- Offsets `[start, end)` em code points sobre o texto canônico NFC, a mesma convenção do `estrutural-v1` na 004. Não dependem do chunking. O harness re-extrai o arquivo (conferindo o sha256) e checa `texto[start:end].startswith(ancora)`; se não bater, falha rápido, porque o extrator mudou.
- Tags por consulta (`sigla_nome_numero`, `termo_tecnico`, `parafrase`, `sem_acento`), para H8 e H9. Nunca dado real de menor.

**Regra de acerto por offsets.** Um chunk c `[a_c, b_c)` acerta o intervalo esperado e `[a_e, b_e)` se `doc_sha256` coincide (via JOIN `chunks.doc_id → documents.doc_sha256`) e `ov = max(0, min(b_c,b_e) − max(a_c,a_e))` satisfaz `ov ≥ 0,5·(b_e − a_e)` OU `ov ≥ 0,5·(b_c − a_c)`. O 50% é convenção e vai no relatório.

**Métricas.**
- Retrieval (só `no_acervo`): recall@5, MRR@10, recall@30 do pool e recall com orçamento de ~1.500 tokens (para comparar tamanhos de chunk). Medidos antes e depois do rerank.
- Gate (classe positiva = recusar): FAR (fora aceitos / fora; métrica crítica, separada em distante e vizinho), FRR (`no_acervo` recusados / `no_acervo`), precisão da recusa, AUROC do sinal, tabela τ → (FAR, FRR) e gráfico de pontos dos escores por caso.
- Latência: p95 por etapa (embedding, SQL + rede, rerank, gate) e total, lida do `duracao_ms` do rastro. Modelos carregados, 3 aquecimentos, cada caso 5× (≥ 100 amostras). Cold start à parte. RTX 4050 fixa.
- Extras: `n_sup` por classe, tokens entregues à geração, VRAM de pico.

**Baseline denso-só** (ajustado ao §3c):

| Item | Valor |
| --- | --- |
| Modelo | bge-m3 denso 1024, normalizado, cosseno `<=>` |
| Chunking | `estrutural-v1` (400/80/0, XLM-R) |
| Busca | exata, sem índice |
| `k_cand` | 30 |
| Lexical / reranker | nenhum |
| Gate | S1: cosseno top-1 ≥ `τ_cos` calibrado nos casos, `n_sup ≥ 1` |
| `k_ger` | 8 |
| Diversidade | dedupe por `chunk_id`, sem MMR |

**Ordem das variáveis.** Uma por vez; a vencedora fica fixa antes da próxima.
1. Modelo de embedding, com denso-só: bge-m3 × Qwen3-0.6B (× OpenAI 3-large, se autorizado).
2. Chunk (reindexa): 400 × 256, overlap 0 × 15%, breadcrumb. Comparar também pelo recall com orçamento.
3. Híbrido: FTS `pt_unaccent` + RRF; o sparse entra só se o modelo for bge-m3.
4. Reranker: sim/não, depois qual.
5. `k_cand`: 20 / 30 / 50.
6. Sinal do gate e τ: S1 × S3 × S3+S4 (m=2) × S3+S2. Sempre por último, e recalibrado se 1–5 mudarem.
7. `k_ger`, dedupe, vizinhos, MMR: com os evals de geração.

Infra fora da ordem, porque não mexe em qualidade: HNSW só se o p95 denso passar de 100 ms; `halfvec` só se for preciso.

**Critério numérico.**
- **C-ret** (mudança de retrieval): adotar se (a) o ganho líquido no recall@5 for ≥ 2 casos (acertos novos − perdidos; ≈ +17 p.p. com 12), ou ganho 0 com ΔMRR@10 ≥ +0,05; (b) nenhum caso da regressão for perdido; (c) o FAR não piorar; (d) o p95 de retrieval + rerank + gate ficar ≤ 1,0 s em regime quente. Empate: fica a opção mais simples, local e barata.
- **C-gate**: FAR = 0 em todos os fora (leave-one-out) e FRR ≤ 1/12. Entre sinais, o de maior AUROC; diferença < 0,05 → o mais simples.
- **C-API**: a API só entra se vencer o melhor local por C-ret e o humano autorizar.

**Amostra.** 20 casos: 12 `no_acervo` (4 questionário, 4 flashcard, 4 aula) + 8 fora (4 `fora_distante`, 4 `fora_vizinho`). Cerca de 25% das consultas são informais, com erro de digitação ou sem acento. Os `fora_vizinho` só podem ser escritos com o acervo real (scraping). Toda falha vira caso de regressão. Metas: 30 fora + 30 respondíveis; depois 60 fora e separação calibração/teste 50/50.

**Ressalva estatística.** Com 12 respondíveis, 1 caso = 8,3 p.p. Regra de três: 0 falhas em 8 fora só garante FAR < ~37% com 95% de confiança; FAR < 10% exige 30 fora sem falha, e < 5% exige 60. Até lá o gate não é garantia sozinho, e a validação pós-geração (item → `chunk_id` + fidelidade) continua obrigatória.

### 6. Hipóteses para a 007

Critérios C-ret, C-gate e C-API conforme o §5. Entre colchetes, a origem.

1. **H1** Trocar bge-m3 por Qwen3-Embedding-0.6B (1024, instrução em inglês na consulta) melhora recall@5 sem piorar MRR@10, FAR nem p95 da consulta (≤ +30 ms). Métrica: recall@5, MRR@10, p95. C-ret. [P2-H1]
2. **H2** Só se H1 vencer: usar instrução em inglês no Qwen3 melhora recall@5 frente à instrução em português e à ausência de instrução, sem mudar o p95. Métrica: recall@5. [P2-H2]
3. **H3** (só com autorização) Trocar pelo OpenAI 3-large `dimensions=1024` melhora recall@5 sobre o melhor local sem piorar MRR@10 nem FAR. C-API. [P2-H3]
4. **H4** Reduzir `max_tokens` de 400 para 256 (min 50) melhora MRR@10 sem piorar recall@5 nem o recall com orçamento de 1.500 tokens. [P3-1]
5. **H5** Passar o overlap de 0 para ~15% (~60 tokens, alinhado a sentença) melhora recall@5 sem piorar o IoU por tokens em mais de 20% relativo nem o p95. [P3-2]
6. **H6** Prefixar "Título > Seção" na entrada do embedding, do `tsv` e do reranker melhora recall@5 sem piorar MRR@10 nem FAR. [P3-4, P4]
7. **H7** Trocar denso-só por denso + FTS `pt_unaccent` (OR, RRF k=60, 30 por ramo) melhora recall@5 e recall@30 do pool sem piorar MRR@10, FAR nem p95 (≤ +20 ms). [P1-H1, P1-H5]
8. **H8** No híbrido, o recall@5 sobe nas tags `sigla_nome_numero` e `termo_tecnico` sem perder caso em `parafrase`. Métrica: recall@5 por tag. [P1-H2]
9. **H9** No ramo FTS isolado, trocar `portuguese` por `pt_unaccent` melhora o recall@30 nas consultas `sem_acento` sem piorar as acentuadas. [P1-H3, P6-H3]
10. **H10** Trocar a tsquery AND (`websearch_to_tsquery`) por OR melhora o recall@5 do híbrido sem piorar MRR@10. Reportar a % de consultas com ramo FTS vazio. [P1-H4]
11. **H11** (só se o modelo for bge-m3) Somar o sparse do bge-m3 como 3º ramo do RRF, ou trocar o FTS por ele, melhora recall@5 sem piorar o p95 em mais de 20 ms. Abaixo do C-ret não justifica a coluna. [P1-H6, P6-H5]
12. **H12** Acrescentar o bge-reranker-v2-m3 sobre os 30 da fusão melhora MRR@10 (≥ +0,05) e recall@5 sem piorar o recall@30 nem o p95 (rerank ≤ 500 ms). [P4-H4.1]
13. **H13** Trocar o bge-reranker pelo Qwen3-Reranker-0.6B melhora MRR@10 sem p95 acima de 1,5× o do bge. C-ret. [P4-H4.4]
14. **H14** Trocar pelo gte-multilingual-reranker-base mantém ≥ 90% do ganho de MRR@10 do bge com ≤ 40% do p95. Se valer, vira o padrão quando a latência apertar. [P4-H4.5]
15. **H15** (só com autorização) Cohere rerank-v4.0-fast, ou Voyage rerank-2.5-lite com opt-out, melhora MRR@10 sobre o melhor local. C-API. [P4-H4.6]
16. **H16** Subir `k_cand` de 30 para 50 melhora recall@5 pós-rerank sem piorar o p95 em mais de 30%; descer para 20 reduz o p95 em ≥ 30% sem perder caso. [P4-H4.2, P5-H5.5]
17. **H17** Trocar o sinal do gate de cosseno top-1 (S1) para logit do reranker top-1 (S3) melhora o AUROC (≥ +0,10) e zera o FAR em `fora_vizinho` sem FRR > 1/12. C-gate. [P4-H4.3, P5-H5.1]
18. **H18** Exigir `n_sup ≥ 2` em vez de `≥ 1` (questão/flashcard) reduz o FAR em `fora_vizinho` sem aumentar o FRR em mais de 1 caso. [P5-H5.2]
19. **H19** Somar a margem top1−top5 ao logit (regressão logística) melhora o AUROC em ≥ 0,03 sem piorar o FRR. Expectativa: refutada. [P5-H5.3]
20. **H20** (sanidade) Reusar um τ calibrado num modelo em outro, sem recalibrar, piora FAR ou FRR em ≥ 20 p.p. Isso justifica recalibrar a cada troca. [P5-H5.4]
21. **H21** Buscar e pontuar o gate com o tema do `pedagogical_understand`, em vez do pedido bruto, melhora o AUROC em ≥ 0,05 sem piorar o recall@5. [P5-H5.6]
22. **H22** (só se sobrar FAR > 0 em `fora_vizinho` que nenhum τ resolva) Uma segunda verificação por NLI local (mDeBERTa) na faixa cinza zera o FAR sem aumentar o FRR em mais de 5 p.p.; LLM só com autorização. [P5-H5.7, H5.8]
23. **H23** (evals de geração) Dedupe por offsets, vizinhos ±1, seção inteira para aula ou MMR λ=0,7 aumentam os intervalos esperados distintos no contexto sem piorar a fidelidade nem passar de 2× os tokens. [P5-H5.9, H5.10, P3-3, P3-6]
24. **H24** (só com decisão do humano, ou LLM local) Contexto gerado por LLM por chunk reduz 1−recall@20 em ≥ 30% relativo sem piorar o FAR, a ≤ US$ 25 por ingestão de 10k. [P3-5]
25. **H25** (infra) Trocar `vector(1024)` por `halfvec(1024)` mantém o top-5 idêntico em ≥ 99% das consultas e o recall@5/MRR@10 iguais, reduzindo o tamanho em ~50% e o p95. [P2-H5, P6-H2]
26. **H26** (infra; só se o p95 exato passar de 100 ms) Trocar a busca exata por HNSW (m=16, ef_construction=64, `ef_search = max(40, k_cand)`) reduz o p95 denso sem piorar o recall@5 em mais de 0,01, com overlap do top-`k_cand` ≥ 0,99. [P6-H1]
27. **H27** (infra) Uma CTE só com `chunk_id` + distância, com JOIN do texto depois, reduz o p95 em ≥ 30% com resultado idêntico. [P6-H4]

Não priorizadas: MRL 512 no Qwen3 (P2-H4; economia irrelevante com 10k trechos), Voyage large + nano (P2-H7; só se o humano escolher a Voyage) e AUROC do e5 (P2-H6; e5 fora da 1ª rodada).

### 7. Impacto no schema

**A `0001` não muda.** Tudo abaixo é aditivo na `0002` (tarefa 008) e reversível no downgrade.

```sql
CREATE EXTENSION IF NOT EXISTS vector   WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;
CREATE TEXT SEARCH DICTIONARY public.pt_stop (TEMPLATE = pg_catalog.simple, STOPWORDS = portuguese, ACCEPT = false);
CREATE TEXT SEARCH CONFIGURATION public.pt_unaccent (COPY = pg_catalog.portuguese);
ALTER TEXT SEARCH CONFIGURATION public.pt_unaccent
  ALTER MAPPING FOR asciiword, asciihword, hword_asciipart, word, hword, hword_part
  WITH public.pt_stop, extensions.unaccent, pg_catalog.portuguese_stem;
ALTER TABLE chunks
  ADD COLUMN embedding extensions.vector(1024),
  ADD COLUMN embedding_model text,
  ADD CONSTRAINT chunks_embedding_par CHECK ((embedding IS NULL) = (embedding_model IS NULL)),
  ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('public.pt_unaccent'::regconfig, text)) STORED;
CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);
-- Sem índice HNSW/IVFFlat (§3a). A busca filtra WHERE embedding_model = :modelo_da_consulta.
```

- As colunas são nulas porque a 004 pode gravar chunks antes da 0002 existir. O CHECK garante que o vetor nunca fica sem o nome do modelo. Se `chunks` estiver vazia na 008, as duas colunas podem virar `NOT NULL`.
- `to_tsvector` com 2 argumentos (regconfig explícito) é imutável, o que é requisito para a coluna gerada. Mudar a config exige drop/add da coluna.
- Alembic: extensões e config via `op.execute`; colunas com `pgvector.sqlalchemy.VECTOR(1024)`, `sqlalchemy.Computed(persisted=True)` e `postgresql.TSVECTOR`; `import pgvector.sqlalchemy` no `script.py.mako`. Compilação offline verificada pela P6.

Condicionais, só se a 007 aprovar:

| Se ganhar | Coluna / índice |
| --- | --- |
| H11 (sparse, com bge-m3) | `chunks.sparse extensions.sparsevec(250002)`, busca exata |
| H6 (breadcrumb) | `chunks.heading_path text NULL`; o `tsv` passa a `to_tsvector(cfg, coalesce(heading_path,'') \|\| ' ' \|\| text)` |
| H23 (seção como pai) | `chunks.section_no integer NOT NULL` + índice `(doc_id, section_no)`. Vizinhos ±1 não precisam de coluna (usam `UNIQUE(doc_id, position)`) |
| H24 (contextual) | `chunks.context text NULL` |
| H25 / H26 | `halfvec(1024)`; `CREATE INDEX CONCURRENTLY ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)` |

**O que NÃO vira coluna:** cosseno, `ts_rank_cd`, score RRF, logit e sigmoid do reranker, `n_sup` e a decisão do gate (rastro JSONL, por consulta); `τ_rr`, `τ_cos`, `m`, `k_cand`, `k_ger` e o modelo/revisão/`max_length` do reranker (constantes em `backend/src/Memorix/config/`, chaveadas por (`embedding_model`, reranker)); `n_tokens` (recalculado com o tokenizer); versão do chunking (`estrutural-v1` + parâmetros) e da config FTS (`pt_unaccent@v1`), que vão no rastro. Não há coluna `index_version`.

### 8. Pontos de decisão

Humano:
- [ESCLARECER: onde fica o vetor na 0002 — coluna `chunks.embedding vector(1024)` + `chunks.embedding_model` (recomendado, forma já aprovada) ou tabela `chunk_embeddings(chunk_id, embedding_model, embedding)` com PK (`chunk_id`, `embedding_model`), que só compensa se dois modelos precisarem ficar vivos ao mesmo tempo?]
- [ESCLARECER: autoriza medir na 007 os desafiantes via API (OpenAI text-embedding-3-large dims=1024; Cohere rerank-v4.0-fast ou Voyage rerank-2.5-lite)? Na 007 saem só o acervo do admin e consultas sintéticas; em produção sairia a consulta do aluno (possível menor), com transferência internacional (LGPD arts. 14 e 33) e o §3.3(c) da OpenAI.]
- [ESCLARECER: contextual retrieval por LLM via API envia o acervo inteiro a terceiro (LGPD e direito autoral) — pode ser testado na 007, ou só a variante com LLM local?]
- [ESCLARECER: volume do acervo no MVP — confirma até ~10 mil trechos? Acima de ~100 mil, o HNSW volta à pauta.]
- [ESCLARECER: orçamento de latência p95 em regime quente para retrieval + rerank + gate — aceita ≤ 1,0 s?]
- [ESCLARECER — LGPD: o projeto Supabase está em **us-east-1** (EUA). O `.env` do humano aponta para o pooler `aws-0-us-east-1`, e o pooler fica na região do projeto [INFERÊNCIA forte]. Então guardar o acervo, e no futuro dados de aluno, já é transferência internacional (LGPD art. 33), independentemente de usar API de embedding. Mantém us-east-1 ou migra para `sa-east-1` (São Paulo) antes de existirem tabelas de aluno? Isso deve ser confirmado com a assessoria jurídica, como `produto.md` já prevê.]
- [ESCLARECER: confirma que o rastro registra `embedding_model` + versão do chunking (`estrutural-v1`) + versão da config FTS (`pt_unaccent@v1`), sem campo nem coluna `index_version`, mesmo com `rag-rastreabilidade.md` ainda citando `index_version`?]

`pedagogy-specialist` (via orquestrador):
- [ESCLARECER: texto da mensagem ao aluno quando o gate recusa ("não está no acervo").]
- [ESCLARECER: cobertura parcial — quando `n_sup` é menor que o pedido (ex.: 10 questões, 2 trechos), limitar os itens a `n_sup`, avisar o aluno ou recusar? Quantos itens um trecho sustenta (1–3)?]
- [ESCLARECER: `k_ger` da aula — 15 trechos é adequado? Ordem por relevância ou pela ordem do documento? A aula recebe a seção inteira?]
- [ESCLARECER: a unidade de chunk `estrutural-v1` (~250–300 tokens: um parágrafo ou uma lista com a frase que a introduz) é a unidade certa para sustentar uma questão ou um flashcard?]

### 9. Riscos principais

1. Tema vizinho aceito pelo gate (mitose × meiose): é o maior risco para o menor. FAR = 0 em 8 casos só garante FAR < ~37%; a validação pós-geração continua obrigatória.
2. Nada foi medido: latência e VRAM na 4050 vêm de conta de FLOPs (TGP de laptop e Windows sem flash-attn podem dobrar os tempos); a busca exata no Supabase (10–50 ms) e o ganho do híbrido com `ts_rank_cd` sem IDF também são estimativas.
3. Amostra pequena: 1 caso = 8,3 p.p.; decisões finas só com ≥ 40 respondíveis.
4. Dependência do extrator (005): títulos não detectados degradam o `estrutural-v1` para recursivo cego; trocar o extrator invalida os offsets dos casos (a âncora detecta).
5. Limiares não portáveis: trocar `embedding_model`, chunking ou reranker exige recalibrar τ, e o acervo crescendo muda a calibração.
6. Supabase: a 0.8.2 não tem as correções do HNSW. O projeto de dev tem `vector` 0.8.2 disponível e ainda não instalada (conferido na 002 com `pg_available_extensions`). DDL pelo session pooler funciona: a `0001` rodou `upgrade`/`downgrade` por ele na 002.
7. GPU compartilhada: embedding + reranker + mDeBERTa ocupam ~3,5–4,5 GB; um LLM local de geração não cabe junto.
8. Prompt injection: o acervo é do admin (risco baixo), mas o reranker instrucional (Qwen3) e a verificação por LLM leem o texto do trecho; o cross-encoder bge é menos suscetível [INFERÊNCIA].

## Baseline (IA)

Configuração: não há retrieval no código. | Casos: nenhum ainda (a 006 cria). | Resultado: Não se aplica. O baseline denso-só é definido aqui e medido na 007.

Hipóteses: H1–H27 em "Resultado da pesquisa" §6, com critérios C-ret, C-gate e C-API no §5. Baseline a medir: bge-m3 denso 1024 + `estrutural-v1` (400/80/0) + busca exata + `k_cand` 30 + gate S1 (cosseno top-1) + `k_ger` 8, sem lexical nem reranker.

## Teste primeiro (feature)

Não se aplica: é pesquisa, não feature.

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| GPU no venv: NVIDIA GeForce RTX 4050 Laptop, 6,0 GiB, `torch 2.11.0+cu128`, `cuda.is_available() = True`, 12 threads de CPU | `venv/Scripts/python.exe -c ...` (2026-09-24) | Passou |
| Critérios de aceitação 1–7 | O orquestrador conferiu cada critério contra as seções §2–§7 e os anexos: fontes com URL, [INFERÊNCIA] marcadas, local × API em §4, protocolo em §5, H1–H27 em §6, DDL da 0002 com a 0001 inalterada em §7. Nenhum código, migração ou download na 003 | Passou |
| Coerência entre pesquisadores | 8 divergências resolvidas pela consolidação (§3). O orquestrador confere que nenhuma decisão contraria o humano: `index_version` não aparece como coluna, o nome `embedding_model` é mantido e a API continua dependendo de decisão | Passou |

## Revisão pedagógica

Parecer consultivo do `pedagogy-specialist` (`Orch002.Ped003`) sobre os 4 pontos do §8. A 003 não gera nada para o aluno, então o parecer não é gate desta tarefa: orienta as tarefas 1.4/1.5. **Parcial:** limite de 2 min, sem ler os anexos, referências citadas de memória. Íntegra em `.omp/tasks/003-anexos/revisao-pedagogica.json`.

Veredito: **Aprovado com ressalvas**. Nenhum achado é Bloqueante como está escrito.

Achados, todos Importante:
1. **Recusa.** A mensagem:
   - repete o tema entendido;
   - diz "não encontrei material suficiente", não "não existe", porque o gate aceita FRR ≤ 1/12;
   - explica em uma frase que não vai inventar conteúdo;
   - oferece 2–3 próximos passos: reformular, escolher tema existente, pedir o material;
   - não culpa o aluno;
   - tem no máximo ~60 palavras;
   - nunca manda o aluno para a internet nem gera conteúdo "geral" como consolo.
2. **Cobertura parcial.** Entregar o que é sustentado e avisar na mesma resposta; recusar só com `n_sup = 0`. Nunca completar com item repetido ou trivial: um item por proposição distinta, ~1–3 questões e até ~4 flashcards por trecho (heurística a validar na 006/007).
3. **Aula.** Escolher os trechos por relevância e **apresentá-los na ordem do documento**; expandir para seção ou vizinhos quando preciso. `k_ger` = 15 é teto, não meta. Dividir em partes se não houver um objetivo único.
4. **Unidade `estrutural-v1`.** Adequada para recuperar e citar; o item testa uma proposição dentro do trecho. Ressalva 4a: os distratores de MC precisam de contexto vizinho e de checagem contra o acervo. **Vira Bloqueante se a validação pós-geração não conferir os distratores.**

Casos de regressão propostos: 8 (`ped-gate-01`…), no anexo. Entram nos evals quando a 006 existir.

Relação com o §1/§5 (ordem por escore) e divergência resolvida:
- **Não há conflito real.** Pela ordem de autoridade, a seleção por escore é do `ai-rag-specialist` (retrieval) e fica mantida. A ordem de apresentação na aula é fluxo de estudo, e fica a do `pedagogy-specialist` (ordem do documento).
- **Registro para a tarefa de geração (1.5):**
  - selecionar por escore e ordenar pela posição no documento;
  - validação pós-geração checa distratores contra o acervo;
  - dedupe por proposição.

## Decisões e conflitos

- Tarefa criada a partir da resposta 02 do humano no gate 1 da 002. Plano aprovado no gate 2 (resposta 7).
- Tempo: "b) para essa task, tempo indeterminado" (gate 2, resposta 4). O limite de 2 min por acionamento **não** vale nesta tarefa, e só nela.
- Hardware e API: "embedding e reranker vai depender do model, podemos tanto usar API Key como a 4050" (gate 2, resposta 5). Por isso a comparação é local × API. O envio de dados a terceiros continua em "Sempre com o humano".
- Autoridade: em decisão técnica de IA/RAG, o `ai-rag-specialist` prevalece sobre o orquestrador (gate 2, resposta 2; aplicado em `.omp/AGENTS.md`). O orquestrador confere critérios, coerência e sequência.
- Goal: fica no goal 6 (desenho, só planejamento). Na proposta de goals menores (`.omp/goals/README.md`, Sugestões), a 003 alimenta o goal proposto 1.3 (Retrieval medido).
- Achado: o venv hoje tem `torch 2.11.0+cu128` com CUDA. Isso contradiz o registro "cpu" da tarefa 001. `progresso.md` já foi corrigido.
- Parecer pedagógico (consultivo) registrado acima. O orquestrador aciona o `pedagogy-specialist` porque a consolidação pediu, com limite de 2 min, já que o "tempo indeterminado" vale só para a pesquisa de IA.

**Gate final (2026-09-24).** Resposta literal do humano, mapeada por conteúdo por `Main`:

> "1. sim, 2. sim 3. chunks 4. sim 5. variante com LLM local 6. sim, mas não existe atualmente 7. sim 8. ignore 9. não entendi. ok"

- Aceite da 003: sim. Estado: Concluída. A proposta de goals 1.1–1.5 é decisão separada (criar goal) e **não** foi tomada como aprovada; segue pendente.
- Onde fica o vetor na 0002: "chunks". Coluna `chunks.embedding vector(1024)` + `chunks.embedding_model`, sem tabela `chunk_embeddings`.
- API na 007: autorizado medir desafiantes via API (OpenAI 3-large dims=1024; Cohere/Voyage rerank). Não é autorização em branco: cada uso real que envie dados a terceiros ainda passa pelo humano ("Sempre com o humano") no momento de rodar.
- Contextual retrieval: só a variante com LLM local. O acervo não vai para API externa.
- Volume: até ~10 mil trechos confirmado como **teto de planejamento**. O acervo real ainda não existe (0 documentos); não é medida.
- Latência p95 (retrieval + rerank + gate) ≤ 1,0 s em regime quente: aceito, vale para C-ret.
- Região us-east-1 / LGPD art. 33: o humano mandou **ignorar por ora**. Não migrar a região. Fica como risco LGPD **adiado por decisão do humano, não resolvido**, a confirmar com a assessoria jurídica antes de existirem dados de aluno.
- Rastro: mantém `embedding_model` + versão do chunking + versão da config FTS, sem `index_version` ("ok", a mesma decisão do gate 2, resposta 11).
- Pontos pedagógicos para o humano (lista de temas na recusa, canal para pedir material, aviso vs pergunta na cobertura parcial, aula em partes, checagem de distratores): não respondidos. Voltam quando as tarefas 1.4/1.5 forem planejadas.
