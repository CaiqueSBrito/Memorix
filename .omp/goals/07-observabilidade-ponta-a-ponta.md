# Goal 7 — Observabilidade ponta a ponta

Criado pelo humano em 2026-10-13. Não é subgoal do MVP: é a camada de medição que atravessa retrieval (goal 1.3) e geração (goal 1.5) e torna o desenho do goal 6 observável. O princípio 4 do pipeline ("IA só muda com medição") precisa de números de ponta a ponta.

## Resultado observável

- **Observabilidade básica do pipeline de RAG/IA:** rastro por `trace_id` ligando todas as etapas de uma consulta (latência, tokens, custo estimado, status por etapa — o que `.omp/instructions/rag-rastreabilidade.md` já exige por etapa), agora **consultável e agregado**: p95 de latência por etapa, taxa de erro, tokens/custo por geração.
- **Métricas de qualidade ponta a ponta** sobre o conjunto de evals (~20 casos reais, tarefa 006):
  - **Context Precision** — trecho-fonte esperado ranqueado acima dos irrelevantes (retrieval + reranking);
  - **Context Recall** — o trecho-fonte esperado foi recuperado (retrieval);
  - **Faithfulness** — cada afirmação da resposta é sustentada pelos trechos recuperados (geração);
  - **Answer Relevancy** — a resposta atende ao pedido do aluno (geração).

  Equivalentes às quatro métricas do RAGAS; retrieval e geração medidos separados (princípio 4 do pipeline). Complementam — não substituem — as checagens determinísticas (recall@k, MRR/nDCG, hit rate, formato válido; `.omp/agents/ai-rag-specialist.md`).

## Critérios (rascunho)

- Rastro consultável por `trace_id` de ponta a ponta, com agregação mínima: p95 por etapa, taxa de erro, tokens/custo por geração.
- As quatro métricas calculadas sobre o conjunto de evals — o formato de caso da 006 (entrada + trecho-fonte esperado + critério de resposta) já fornece o que elas precisam — nos moldes da 007: baseline antes, uma variável por vez, casos representativos (não só os favoráveis).
- LLM-as-judge nunca como evidência única: combinado com checagem determinística e revisão humana.
- Juiz LLM local; execução via API externa não foi escolhida para a 013, que mantém dados locais.
- Métricas rodam no conjunto de evals (offline); scoring por requisição real só se o humano pedir.
- Sem segredos e sem conteúdo do aluno nos registros (regras do rastro).

## Tarefas

006 (conjunto de eval) e 007 (medição, protocolo) pertencem ao goal 1.3 e alimentam este goal — a mesma relação que a 003 tem com o 1.3 e o 6. A 009 foi autorizada para a ingestão existente e aceita com ressalva em 2026-10-14; a ponta a ponta da consulta depende da implementação dos outros goals:

| Tarefa | Depende de | Estado |
| --- | --- | --- |
| [009 — observabilidade básica da ingestão](../tasks/009-observabilidade-ingestao.md): rastro consultável por `trace_id` + agregação (p95 por etapa, taxa de erro; tokens/custo quando uma geração emitir esses campos) | 008 (busca com rastro) e geração (goal 1.5) para a ponta a ponta completa | Concluída com ressalva (testes com banco não executados); extensão por etapa futura |
| 010 — métricas E2E (Context Precision, Context Recall, Faithfulness, Answer Relevancy) sobre o conjunto de evals | 006, 007, 009 e geração | Implementação consolidada na013, autorizada no pedido de todos os goals/backend/IA |

## Decisões que valem aqui (já registradas)

- Ferramenta dedicada de observabilidade (OpenTelemetry, Langfuse etc.): stdlib primeiro; só quando a stdlib não bastar, e é decisão do humano (`rag-rastreabilidade.md`; pipeline, "Sempre com o humano").
- Dados do aluno nunca a terceiros sem decisão do humano; conteúdo por referência nos logs (LGPD, menores).
- Até ~10 mil trechos como teto de planejamento.

## Em aberto

- Harness local em `backend/evals/`, provas em `backend/evals/results/`. Context Precision é AP@10 de âncoras rotuladas; Context Recall mede cobertura@30. São proxies por SHA/offset, não julgamento completo de fontes alternativas. Baseline anterior à curadoria:0,4653/0,75. Medição014 com um span ativo:0,3819/0,6667 no híbrido/reranker; quatro variantes agora isolam o componente lexical, sem misturar corpora.
- Faithfulness usa afirmações verificadas no rastro e Answer Relevancy combina juiz local com status; rejeições e casos editoriais não podem sumir dos denominadores. Quarentena não altera o rótulo positivo nem proíbe o tema inteiro; contador de spans vem do banco. Regressão falhou antes e passou na suíte151.
- Tokens/custos são valores observados do provider local, não preços fictícios de APIs. HTTP comprovou rastros por tipo/correção e métricas admin; respostas/pedidos brutos e segredos ausentes, inclusive hash de template independente da resposta.

Status: Em andamento; backend, consulta/agregação e harness verificados nas013/014. A014 preserva resultados negativos de geração e prova rastro de novo flashcard (2/2claims apoiadas, pedido bruto ausente); formatos, fundamentação e relevância continuam distintos. Evidência em `verification_014.json`, sem aceite geral pelo próprio modelo.

Continuação015 corrige lifetime da captura pública: provider restaurado em `finally`, apenas a thread do benchmark grava amostras e benchmarks são serializados. RED2 observado; suíte155passou, incluindo outra thread. Smoke real ret01 capturou11registros públicos/2claims apoiadas; duas gerações Qwen ordinárias após sucesso/erro não alteraram o arquivo. Rastro real da correção zero sem resposta/tokens, duas sessões sintéticas revogadas. Provas/hashes em `verification_015.json`. Substituição ainda global durante eval; não é autorização de inferência GPU concorrente nem nova métrica de qualidade geral.
