# Goal 3 — Acompanhamento por acurácia

Acompanhar a evolução por acerto por questão e indicar material do acervo com o motivo e as respostas que o sustentam.

Execução backend autorizada em 2026-10-31, tarefa [013](../tasks/013-backend-ia-todos-goals.md); frontend adiado.

Regras aprovadas: acurácia objetiva somente MC/V-F; flashcards são autoavaliação e dissertativas são rubrica assistida, em indicadores separados. Histórico distingue primeira tentativa e revisões. Tentativas de fontes em revisão continuam no histórico com `source_in_review`, mas são separadas como `excluded_attempts`, sem inflar o indicador válido.

Implementação em `services/study.py`: `/study/history`, `/study/accuracy`, `/study/recommendations`; aluno autenticado, respostas idempotentes e indicações de doc/chunk/offset por erro. Suíte151 testes. HTTP real:10respostas, só7MC/V-F entram na acurácia (5certas),2primeiras/5revisões;1autoavaliação e2notas dissertativas ficam separadas. Recomendações apontaram às respostas e a materiais acessíveis, sem fontes em quarentena.

Status: backend implementado e verificado localmente na013; gráficos/frontend adiados, qualidade de conteúdo não inferida dos testes de autorização/persistência.
