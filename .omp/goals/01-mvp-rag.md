# Goal 1 — MVP RAG funcional

A partir do acervo, gerar **questões** (múltipla escolha e V/F), **flashcards** e **aulas**, fiéis ao material e rastreáveis.

Dividido em subgoals (criados pelo humano em 2026-09-24): [1.1 Acervo persistido](01.1-acervo-persistido.md), [1.2 Ingestão](01.2-ingestao-acervo.md), [1.3 Retrieval medido](01.3-retrieval-medido.md), [1.4 Recusa fora do acervo](01.4-recusa-fora-do-acervo.md), [1.5 Geração fiel por tipo](01.5-geracao-fiel-por-tipo.md). O goal 1 está concluído quando os cinco estiverem.

Critérios do backend/API (frontend adiado pelo humano em 2026-10-31):
- Admin envia PDF e texto; material é ingerido, dividido em trechos e indexado.
- Aluno pede questões, flashcards ou aula sobre um tema e recebe conteúdo sustentado por trechos do acervo.
- Nada sem fonte é entregue como fato; tema sem material → resposta "não está no acervo".
- Rastro completo por etapa (`.omp/instructions/rag-rastreabilidade.md`).
- Suíte de evals com ~20 casos reais, retrieval e geração medidos separados.
- Revisão pedagógica aprovada para os três tipos de conteúdo.

Execução atual: [013 — backend e IA de todos os goals](../tasks/013-backend-ia-todos-goals.md). O MVP inclui backend/API e registra respostas; web/mobile ficam para depois. Implementação em verificação, com métricas e revisão pedagógica reais antes de declarar aceite.
