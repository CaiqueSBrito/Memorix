# Goal 2 — Planejamento de estudo

Plano do que revisar e quando, derivado do desempenho e ligado às respostas que o motivaram.

Execução backend autorizada em 2026-10-31, tarefa [013](../tasks/013-backend-ia-todos-goals.md); frontend adiado.

Implementação: `services/study.py` e `GET /study/plan`. Regra inicial aprovada: intervalos de 1/3/7/14 dias por acertos consecutivos, erro reinicia; questões MC/V-F e autoavaliação de flashcards preservam seus tipos. Não é algoritmo adaptativo cientificamente validado. Cada item aponta aos IDs de respostas; fontes em revisão são retiradas do plano, mantendo o histórico sinalizado.

Dependências implementadas: contas/sessões, respostas idempotentes e histórico por aluno. Suíte final151 testes em PostgreSQL isolado. HTTP real exerceu erro→acertos consecutivos e mediu intervalos1/3/7/14, com IDs das respostas no plano; flashcard e V/F mantêm indicadores próprios. Evidência em `backend/evals/results/http_final_013.json`.

Status: backend implementado e verificado localmente na013; frontend adiado, sem declarar validação científica do algoritmo nem aceite humano automático.
