# Goal 5 — Questões dissertativas

Geração e correção local assistida por IA, com rubrica analítica, fonte, pontuação justificada, incerteza e rastro; revisão pedagógica obrigatória.

Execução backend/IA autorizada em 2026-10-31, tarefa [013](../tasks/013-backend-ia-todos-goals.md). API aceita `type: essay`; gabarito/rubrica privados antes da resposta, conteúdo isolado por aluno e nota fora da acurácia objetiva MC/V-F.

Correções: rubrica JSON analítica com dois fatos distintos, resposta de referência composta no servidor; juiz pedagógico separado do factual; crédito só com citação literal do aluno, total somado pelo servidor. Feedback livre que contradizia nota/evidência foi removido; status e explicação derivam dos critérios, sem confundir erro com ausência de abordagem.

Prova real: parcial0,5/1 e errada0/1 no provider e pela API201, feedback/incerteza/fontes/rastro presentes, nenhuma entrada na acurácia objetiva. Revisão orientativa aprovou essas amostras com ressalvas. Status: implementação e prova local concluídas na013; avaliação automática pode errar, sem aceite humano ou garantia geral.

Continuação015: trecho literal associado pelo modelo a critério zerado não é mais descartado do feedback; rótulo neutro “Trecho avaliado da sua resposta”. Regressão falhou antes; suíte155passou. API real201/nota0 preservou a frase incorreta e o histórico/replay mantiveram o feedback; rastro sem resposta/tokens. Revisão estática focal confirmou o reparo. Isso corrige perda de informação, não a possibilidade de erro semântico na atribuição dos pontos; evidência em `verification_015.json`.
