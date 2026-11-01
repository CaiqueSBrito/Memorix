# Goals — Memorix

Um arquivo por goal nesta pasta; este índice é a fonte do status e da execução.

Goal = resultado de produto de médio prazo. Tarefa = unidade executável do pipeline; toda tarefa aponta para um goal.
Só o humano cria goal, muda status ou autoriza execução. Execução **Bloqueada** → só tarefas de discovery/planejamento, sem código de produto.

| # | Goal | Status | Execução |
| --- | --- | --- | --- |
| 1 | [MVP RAG funcional](01-mvp-rag.md) | Em andamento. É a soma dos subgoals 1.1–1.5 | Por subgoal (abaixo) |
| 1.1 | [Acervo persistido](01.1-acervo-persistido.md) | Concluído (002) | 002 foi autorizada e concluída |
| 1.2 | [Ingestão do acervo](01.2-ingestao-acervo.md) | Concluído (004 e 005 aceitas) | **Autorizada e aceita** (humano, 2026-10-01); 005 executada em worktree e integrada em `develop` |
| 1.3 | [Retrieval medido](01.3-retrieval-medido.md) | Implementado/medido;014isolou contribuição lexical comreranker fixo | **Autorizada**; corpus local,17PDFs/7.158vetores, métricas/limites separados do aceite |
| 1.4 | [Recusa fora do acervo](01.4-recusa-fora-do-acervo.md) | Gate implementado e medido, sem garantia externa | **Autorizada**; calibração leave-one-out com labels preservados e recusa HTTP real |
| 1.5 | [Geração fiel por tipo](01.5-geracao-fiel-por-tipo.md) | Cinco tipos provados;014garante ordem dos flashcards; qualidade geral limitada | **Autorizada**; IA local/validação/revisão, candidatos semganho rejeitados; semfrontend |
| 2 | [Planejamento de estudo](02-planejamento-estudo.md) | Backend implementado/testado e verificado por HTTP | **Autorizada**; intervalos1/3/7/14 e vínculos às respostas provados |
| 3 | [Acompanhamento por acurácia](03-acompanhamento-acuracia.md) | Backend implementado/testado e verificado por HTTP | **Autorizada**; primeiras/revisões e indicadores separados por tipo |
| 4 | [App mobile](04-app-mobile.md) | Futuro | Frontend/mobile adiados pelo humano; API compartilhável no backend da013 |
| 5 | [Questões dissertativas](05-questoes-dissertativas.md) | Geração/correção reais;015preserva trecho incorreto no feedback de nota zero | **Autorizada**; rubrica/fonte/rastro, nota fora da acurácia objetiva; julgamento semântico ainda limitado |
| 6 | [Pipeline RAG](06-pipeline-rag.md) | Backend implementado e verificado, sem aceite de qualidade presumido | **Autorizada**; fluxo local com gate/validação, sem multiagente especulativo |
| 7 | [Observabilidade ponta a ponta](07-observabilidade-ponta-a-ponta.md) | Rastros/métricas;015corrige isolamento da captura pública de evals | **Autorizada**; corpusreal, quatro variantes e limites preservados; sem aceite geral presumido |

## Sugestões (não aprovadas)

| Sugestão | Por quê |
| --- | --- |
| Contas, papéis e consentimento LGPD | Goals 2 e 3 guardam dados por aluno, e há menores de idade: login, papel aluno/admin e consentimento dos responsáveis precisam existir antes. |
| Gestão do acervo pelo admin | Atualizar, versionar e remover material; material removido não pode continuar gerando conteúdo nem indicações. |
| Lembretes de revisão | Repetição espaçada só funciona se o aluno volta na hora certa; o plano (goal 2) precisa de um gatilho. |
| Painel do responsável/professor | Com público menor de idade, responsáveis tendem a precisar ver o progresso. |
| Novos formatos de material | Slides e vídeo (via transcrição) ampliam o acervo sem mudar o pipeline de RAG. |

## Histórico

- 2026-09-24: goals 1.1–1.5 criados pelo humano. Ele pediu "dividir em goals menores antes do goal 1" no gate 2 da 002 e aprovou a proposta do `orchestrator` com "1. sim". Na mesma aprovação entrou a fila de tarefas 004–008, registrada em cada goal.
- 2026-10-01: execução do goal **1.2 autorizada pelo humano**, resposta literal: "Autorizar o goal 1.2 inteiro (004 e 005/PDF)". Cobre as duas tarefas da fila — 004 (texto) e 005 (PDF). Status do goal passa de Planejado para Em andamento. Os goals 1.3, 1.4 e 1.5 continuam bloqueados.
- 2026-10-01: tarefa 004 aceita pelo humano após revisão do chunking; H-004 permanece **Falhou** nas seis fixtures (25% de chunks curtos, pelo menos 6,25% fallback). Código e testes em commits atômicos no `develop`; 005 em outra worktree autorizada pelo humano.
- 2026-10-01: tarefa 005 (PDF selecionável e OCR local `por` em PDFs digitalizados/mistos) e goal 1.2 aceitos pelo humano: "Aceitar 005 e concluir goal 1.2". H-005 passou nas seis páginas de fixture; H-004 permanece Falhou e aceita. Cinco commits atômicos da 005 integrados por fast-forward em `develop` com autorização explícita; sem push/deploy.
- 2026-10-01: após a conclusão de 1.1/1.2, o humano escolheu **"Manter 1.3 bloqueado"** no gate sobre o próximo goal. Tarefas 006–008 não recebem autorização de código; material real da 006 ainda depende do scraping.
- 2026-10-13: goal 7 (Observabilidade ponta a ponta) criado pelo humano: observabilidade básica do pipeline de RAG/IA (rastro por `trace_id` consultável e agregado: p95 por etapa, taxa de erro, tokens/custo) mais as métricas E2E **Context Precision, Context Recall, Faithfulness e Answer Relevancy** sobre o conjunto de evals. Status Planejado, execução bloqueada; fila 009/010 é sugestão não aprovada.
- 2026-10-14: humano autorizou logger básico da ingestão como tarefa 009 e aceitou com ressalva: 54 testes offline passaram; 14 casos com banco não executados. Goal 7 passa a Em andamento, sem desbloquear os goals 1.3/1.5 nem a 010; métricas E2E dependem da consulta, geração e evals.
- 2026-10-14: o humano pediu implementar o goal 1.3, forneceu 17 PDFs em `C:\Users\gamer\Documents\Docs Memorix` e aprovou a sequência ingestão no schema 0001 → 006 → 007 → 008. A conexão TCP 5432 ao pooler Supabase expirou em todos os IPs; a execução aguarda acesso. A revisão por `orchestrator`/especialista foi dispensada somente para esta tarefa, pois esta API não oferece `/session pin caique.ds.brito@gmail.com`.
- 2026-10-31: pedido literal `continue a implementação de todos os goals, implemente o backend e a IA, front vai ser feito posteriormente`. Autoriza fatias de backend/IA dos goals existentes, mantém web/mobile adiados. Sequência aprovada: retrieval/evals → recusa/geração → respostas/acurácia/planejamento → dissertativas/métricas E2E. Tarefa [013](../tasks/013-backend-ia-todos-goals.md) registra exceções locais de execução contínua, pin e transporte nativo, PostgreSQL local isolado, consentimento por convite admin após verificação externa e regras iniciais de revisão. Instrução posterior: `não pergunte, pode rodar sem perguntar nada pra mim, faça o que achar melhor`; sem novas pausas de gate nesta execução. Autorização não equivale a metas de qualidade atingidas nem aceite final de goals.
