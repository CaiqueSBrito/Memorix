# 015 — IA por objetivos e isolamento das avaliações

Goals: 1.3,1.5,5,6,7. Trilha: IA. Estado: Concluída no recorte abaixo; qualidade geral dos goals permanece em andamento.

## Pedido e limites

Continuar todos os goals de backend/IA; frontend/mobile posteriormente. Mantidas autorizações da013: sem perguntas/gates intermediários, subagentes nativos/pin dispensado e banco local isolado. Sem download novo, inferência externa, commit/push/deploy. Não ocultar falhas nem reclassificar temas por quarentena de uma âncora.

## Baseline e hipótese

Runtime estável grounded-pt-v5, Qwen2.5 7B Q4, BGE/reranker fixados. generation_final_013.json:8/12positivos aprovados,8/8fora recusados,29/38claims apoiadas, relevância local10/20. Experimentos de query inteira,schema evidence-first e juízes extras sem ganho foram rejeitados nas013/014.

Hipótese nova e limitada: decompor objetivos explícitos do pedido em expressões extraídas literalmente dele e recuperar evidências para cada parte reduz omissão de objetivos múltiplos sem inventar tema. Medir antes de incorporar; gate/labels/modelos não mudam por plausibilidade. Backend de avaliação também tem defeito independente reproduzido: substitui globalmente o provider para capturar amostras e não restaura após terminar/falhar, podendo registrar respostas privadas posteriores no mesmo processo.

## Critérios e ownership

- Main: medir decomposição e seleção por objetivo, testar fronteiras/trust boundaries antes de implementar se candidata tiver ganho; preservar os20casos originais e negativos. Recusar mudança que só melhore razão condicional excluindo entregas.
- EvalIsolationOwner(orchestrator): somente backend/evals/run.py, corrigir lifetime da captura de geração; CLI continua capturando apenas as saídas públicas da sua própria avaliação.
- EssayQualityAudit015(reviewer): revisão orientativa somente leitura de grade_answer→persistência→API; especialistas configurados IA/pedagogy indisponíveis429 já observados, sem fingir execução original.
- Main roda suíte no memorix_test, smoke com modelos reais e API no DEV, rastro sem resposta/pedido bruto. Ninguém além de Main usa GPU/inferência.

## Teste primeiro

`test_evals_capture_isolation.py`: RED2 observado, após término normal e após case_id inválido; chamada posterior ordinária de geração acrescentou resposta sintética privada no arquivo público .samples.jsonl. Não houve evidência de dado real de aluno vazado; a reprodução usa dados sintéticos. Teste cobre comportamento de privacidade, não identidade/wiring do provider.

`test_ai_grading_criteria.py::test_zero_credit_preserves_the_incorrect_passage_for_feedback`: RED1 observado antes do reparo. O modelo havia associado uma frase incorreta ao critério zerado, mas o servidor removia essa frase do feedback. A associação se perdia na API/histórico, que não persistem a lista estruturada de critérios.

## Implementação e decisões

- `backend/evals/run.py`: restauração do provider em `finally`, inclusive erro de caso/arquivo; filtro pela thread do benchmark e lock entre benchmarks. Substituição ainda global durante a avaliação; não autoriza concorrência de inferência na GPU.
- `pipeline/service.py`: preserva citação não vazia mesmo com nota zero, sob o rótulo neutro **Trecho avaliado da sua resposta**. Não muda pontuação, rubrica, prompt de correção, schema HTTP ou banco.
- Decomposição local nos mesmos20pedidos gerou20planos literais válidos; somente ret10 foi dividido em três objetivos. Busca independente recuperou fontes para cada termo, mas nenhuma sobrepôs a âncora rotulada. Prefixar o tema também não recuperou essa âncora e deixou pena de morte em -1,6514, abaixo do gate -1,0676. Não há evidência de melhora da relação específica pedida: candidato **não incorporado**. Fonte alternativa não é automaticamente errada só por não coincidir com a âncora.
- Nenhum caso/label/denominador/modelo/gate foi alterado. Não foi feita nova geração completa de20casos: candidato descartado antes de modificar runtime. Baseline geral permanece da013, não é resultado novo.

## Evidências

| O quê | Método e resultado | Status |
| --- | --- | --- |
| Regressões | PostgreSQL `memorix_test`:155passaram,1aviso TestClient/HTTPX,29,47s | Passou |
| Captura pública | Benchmark real ret01:statusok,âncora esperada,2/2claims;11registros públicos. Duas chamadas Qwen ordinárias posteriores, após sucesso e após caso inválido, não alteraram o arquivo | Passou |
| Concorrência de captura | Terceira variante permanente verifica que outra thread não grava saída privada durante benchmark | Passou na suíte; inferência concorrente real não executada |
| Feedback zero | API real201/10,125s,nota0 com frase incorreta preservada; histórico200 mantém o mesmo feedback; replay200 mantém o mesmo ID | Passou |
| Rastro e sessões | Rastro admin200 sem resposta nem tokens; duas sessões sintéticas revogadas e rejeitadas401 | Passou |
| Corpus/schema | DEV local:17documentos,7.158chunks,1exclusão,migração0005. API `memorix-api-015`,loopback8000,health200 | Passou |
| Objetivos explícitos | Extração20/20literal,sondagens de fontes sem ganho comprovado; sem alteração no produto | Falhou em demonstrar ganho |
| Qualidade geral da geração | Sem nova bateria completa;8/12positivos,29/38claims e relevância10/20 continuam baseline013 | Não executado na015 |

Comando da suíte, hashes finais e evidências: `backend/evals/results/verification_015.json`. Amostras em `capture_lifecycle_015.samples.jsonl`, `essay_zero_credit_http_015.json`, `essay_zero_credit_trace_015.json` e `objective_probe_decision_015.json`. Scripts descartáveis removidos após as provas. Hashes foram medidos ao final; não há hash pré-implementação para alegar comparação retrospectiva. O teste da captura foi ampliado de2para3variantes; o teste novo de feedback não mudou entre RED e GREEN.

## Revisão e limites

EssayQualityAudit015(reviewer) confirmou estaticamente os dois reparos, sem novos defeitos concretos; não executou testes/inferência independentemente. Fallback nativo autorizado, não revisão do especialista configurado nem aceite geral pedagógico. O modelo ainda pode julgar critérios incorretamente; ret10/ret11 e curadoria científica continuam limites abertos. Frontend/mobile, downloads e inferência externa não foram feitos. Sem commit/push/deploy ou alteração de autorização/status oficial dos goals.
