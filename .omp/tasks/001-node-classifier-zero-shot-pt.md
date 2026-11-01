# 001 — Calibração do classificador zero-shot em português
Goal: 1 — MVP RAG funcional        Trilha: IA        Estado: Cancelada

## Objetivo

Corrigir a má calibração do classificador zero-shot (`backend/src/Memorix/providers/bgem3_provider.py`) para texto e rótulos em português. Hoje `CLASSIFIER_MODEL` nunca é setado, então `transformers.pipeline(task="zero-shot-classification", model=None)` cai no default do Hugging Face, `facebook/bart-large-mnli` — treinado só em inglês — e erra a maioria das frases em PT-BR. Este arquivo é o protótipo/base do "node classifier (zero-shot)" do `pedagogical_understand` descrito em `.omp/context/produto.md`.

## Critérios de aceitação

- [x] Baseline documentado: configuração atual (modelo, device, labels) e resultado exato nos 9 casos principais + 3 casos-limite, medido antes de qualquer mudança (ver seção Baseline).
- [x] Hipótese testável registrada e aprovada pelo humano ("ok" no plano, via `Main`) antes da etapa 3.
- [x] Após a mudança (etapa 3/4): acurácia top-1 nos 9 casos principais ≥ 7/9 (vs 4/9 do baseline) — **atingido: 8/9** (ver Resultado pós-mudança).
- [ ] Nenhuma regressão nos casos-limite hoje corretos (`edge_2`, `edge_3`): continuam corretos — **parcial, NÃO totalmente atingido**: `edge_3` continua correto, `edge_2` regrediu (ver Resultado pós-mudança).
- [x] `CLASSIFIER_MODEL` deixa de depender silenciosamente do fallback em inglês do Hugging Face: `config/config.py` tem um default explícito, documentado (env var renomeada para `MODEL_CLASSIFIER` pelo humano durante esta sessão — default aplicado ao nome atual).
- [x] Rastro mínimo por execução — rótulos, pontuação por rótulo, id e revisão do modelo, `hypothesis_template` — conforme `.omp/instructions/rag-rastreabilidade.md` e o desenho já descrito em produto.md.
- [x] Nenhum dado de aluno enviado a terceiros; modelo continua local/self-hosted (sem provider pago), conforme requisito transversal de LGPD do produto.
- [x] Resultado antes×depois documentado nesta tarefa com os mesmos 12 casos (etapa 4).

## Fora do escopo

- Construir o `pedagogical_understand` completo (retrieval, reranking, `generation_adapter`) — só o node classifier zero-shot.
- Trocar os rótulos de demonstração (`saudação`/`despedida`/`informação`) pelos rótulos reais do produto (`flashcard`/`questionario`/`aula`) — depende de decisão do humano (ver Esclarecer).
- Fine-tuning de qualquer modelo (produto.md já descartou fine-tuning para este classifier).
- Multi-rótulo, subtipo (`multipla_escolha`/`verdadeiro_falso`) e o fluxo "perguntar ao aluno em caso de ambiguidade" — ficam para quando o node classifier real for construído dentro do goal 1.
- Qualquer trabalho de ingestão, índice ou geração.

## Esclarecer

Resolvido pelo humano (via `Main`):
1. Goal 1: "está sendo implementado, mas estou codando na mão já" — goal 1 já em andamento manual pelo humano; correção pontual autorizada a prosseguir, não é bloqueio ativo.
2. Modelo: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` autorizado — pode baixar do Hugging Face Hub.
3. Labels: manter `saudação`/`despedida`/`informação` — não trocar para os rótulos reais de produto agora.

## Plano

| Passo | Quem | Arquivos |
| --- | --- | --- |
| 1. Baseline no modelo/config atual (fallback `facebook/bart-large-mnli`) nos 9 casos + 3 casos-limite | `orchestrator` (concluído nesta tarefa) | nenhum — medição em memória, sem tocar `src/` |
| 2. Gate humano: "ok" no plano + respostas ao Esclarecer acima | humano (via `Main`) | — | **Concluído** |
| 3. Carregar modelo candidato prioritário (`mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, ou `bge-m3-zeroshot-v2.0` se rede não autorizada) e rodar os mesmos 12 casos | `ai-rag-specialist` | leitura/medição, sem editar `src/` ainda |
| 4. Se acurácia ≥ 7/9: aplicar no código — default explícito de `CLASSIFIER_MODEL` + doc da env var; `hypothesis_template` em português (ex. "Este texto é um exemplo de {}.") | `ai-rag-specialist` | `backend/src/Memorix/config/config.py`, `backend/src/Memorix/providers/bgem3_provider.py` |
| 5. Rastro mínimo (log estruturado por execução), conforme `.omp/instructions/rag-rastreabilidade.md` | `ai-rag-specialist` | `backend/src/Memorix/providers/bgem3_provider.py` |
| 6. Registrar os 12 casos como início de `backend/evals/` (produto.md já prevê isso para o node classifier) | `ai-rag-specialist` | `backend/evals/` (novo) |
| 7. Provar: rodar os mesmos 12 casos pós-mudança, comparar com baseline, registrar nesta tarefa | quem construiu (`ai-rag-specialist`) | atualização desta tarefa |
| 8. Revisão pedagógica: registrar "Não se aplica" com motivo (classifier ainda não entrega conteúdo ao aluno) | `orchestrator` | atualização desta tarefa |
| 9. Aceite final do humano | humano (via `Main`) | — |

## Baseline (IA)

Configuração: `transformers.pipeline(task="zero-shot-classification", model=os.getenv("CLASSIFIER_MODEL"))`, `CLASSIFIER_MODEL` não setado → default do Hugging Face para a task, `facebook/bart-large-mnli` (revisão `d7645e1`); `device=-1` (CPU, `USE_CUDA` não setado). Labels: `["saudação", "despedida", "informação"]`.

Casos (12 — 3 por rótulo nos principais, + 3 casos-limite):

| id | texto | esperado | top-1 obtido | scores (saudação / despedida / informação) | resultado |
| --- | --- | --- | --- | --- | --- |
| saud_1 | Olá, como você está? | saudação | informação | 0.1414 / 0.0543 / 0.8043 | ERRO (caso relatado pelo humano — reproduzido exatamente) |
| saud_2 | Oi, tudo bem com você? | saudação | informação | 0.4054 / 0.0957 / 0.4989 | ERRO |
| saud_3 | Bom dia! Que bom te ver por aqui. | saudação | informação | 0.3587 / 0.1404 / 0.5009 | ERRO |
| desp_1 | Tchau, até mais! | despedida | despedida | 0.2877 / 0.4580 / 0.2543 | OK |
| desp_2 | Até logo, um grande abraço. | despedida | informação | 0.3348 / 0.0456 / 0.6196 | ERRO |
| desp_3 | Preciso ir agora, nos falamos depois. Tchau! | despedida | despedida | 0.0213 / 0.8938 / 0.0849 | OK |
| info_1 | A capital do Brasil é Brasília. | informação | saudação | 0.4901 / 0.1972 / 0.3127 | ERRO |
| info_2 | O prazo de entrega é até sexta-feira. | informação | informação | 0.2686 / 0.1874 / 0.5440 | OK |
| info_3 | Preciso de mais informações sobre o produto. | informação | informação | 0.0306 / 0.0131 / 0.9563 | OK |
| edge_1 | Olá! Só passando para avisar que a reunião foi cancelada. | saudação (ambíguo) | despedida | 0.0444 / 0.6009 / 0.3547 | ERRO |
| edge_2 | Até a próxima, pessoal! | despedida | despedida | 0.1658 / 0.6201 / 0.2142 | OK |
| edge_3 | Qual é a previsão do tempo para amanhã? | informação | informação | 0.0514 / 0.0287 / 0.9199 | OK |

Resultado: **4/9 (44,4%)** de acurácia top-1 nos casos principais; 2/3 nos casos-limite. Confirma o defeito relatado: falha sistemática em saudações (0/3), instável em despedidas (2/3), 1 falso positivo grave em informação (`info_1`: frase factual classificada como saudação).

Hipótese: o problema é calibração de idioma do modelo NLI, não falha do método zero-shot em si (`ai-rag-specialist` concorda — ver Decisões). `facebook/bart-large-mnli` só foi treinado em inglês; a relação de entailment entre hipótese (rótulo) e premissa (texto) em português não é confiável nesse modelo. Trocar para um NLI multilíngue treinado com português, mantendo `zero-shot-classification`, deve elevar a acurácia sem precisar de fine-tuning nem trocar para embeddings+similaridade.

Candidatos, em ordem de prioridade (definida com `ai-rag-specialist`):
1. `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` — já é a decisão do humano em produto.md para o node classifier real; evita duas configs de modelo divergentes no repo. Não está em cache local (precisa baixar).
2. `MoritzLaurer/bge-m3-zeroshot-v2.0` — já em cache local (zero custo de rede), mesma família de autor, também multilíngue. Usar como fallback se o download do (1) não for autorizado ou falhar.

Critério de sucesso proposto: acurácia top-1 ≥ 7/9 nos casos principais + margem clara entre top-1 e segundo colocado nos casos-limite (não só acertar, evitar quase-empate); usar `hypothesis_template` em português (ex.: "Este texto é um exemplo de {}.") em vez do template padrão em inglês. Sem gate de latência — é um spike, não caminho de produção crítico ainda.

## Resultado pós-mudança (etapa 3/4)

Configuração: `transformers.pipeline(task="zero-shot-classification", model="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")` (revisão `b5113eb`), `device=-1` (CPU). Labels iguais ao baseline. `hypothesis_template="Este exemplo é {}."` — escolhida entre 6 variações testadas (ver Decisões) por maximizar a acurácia principal com as margens mais claras nos casos-limite corretos.

| id | texto | esperado | top-1 obtido | margem (top1−top2) | scores (saudação / despedida / informação) | resultado |
| --- | --- | --- | --- | --- | --- | --- |
| saud_1 | Olá, como você está? | saudação | saudação | 0.4923 | 0.7038 / 0.0848 / 0.2114 | OK |
| saud_2 | Oi, tudo bem com você? | saudação | saudação | 0.8091 | 0.8795 / 0.0501 / 0.0704 | OK |
| saud_3 | Bom dia! Que bom te ver por aqui. | saudação | saudação | 0.0731 | 0.5115 / 0.0501 / 0.4384 | OK |
| desp_1 | Tchau, até mais! | despedida | despedida | 0.0931 | 0.4155 / 0.5086 / 0.0759 | OK |
| desp_2 | Até logo, um grande abraço. | despedida | saudação | 0.3073 | 0.5564 / 0.2491 / 0.1945 | ERRO |
| desp_3 | Preciso ir agora, nos falamos depois. Tchau! | despedida | despedida | 0.4631 | 0.1264 / 0.6683 / 0.2052 | OK |
| info_1 | A capital do Brasil é Brasília. | informação | informação | 0.2622 | 0.2184 / 0.2597 / 0.5219 | OK |
| info_2 | O prazo de entrega é até sexta-feira. | informação | informação | 0.5044 | 0.1867 / 0.1223 / 0.6910 | OK |
| info_3 | Preciso de mais informações sobre o produto. | informação | informação | 0.5346 | 0.0825 / 0.1914 / 0.7260 | OK |
| edge_1 | Olá! Só passando para avisar que a reunião foi cancelada. | saudação (ambíguo) | saudação | 0.2468 | 0.5956 / 0.0556 / 0.3488 | OK |
| edge_2 | Até a próxima, pessoal! | despedida | saudação | 0.3686 | 0.5850 / 0.1985 / 0.2165 | ERRO |
| edge_3 | Qual é a previsão do tempo para amanhã? | informação | informação | 0.6607 | 0.0681 / 0.1356 / 0.7963 | OK |

**Resultado: 8/9 (88,9%) nos casos principais** (baseline: 4/9, 44,4%) — critério primário de sucesso (≥7/9) **atingido**.
**Casos-limite: 2/3** (baseline: 2/3) — mas não é o mesmo par: `edge_1` (antes ERRO) passou a acertar; `edge_2` (antes OK) passou a errar. `edge_3` segue correto com margem clara (0.66). O critério "nenhuma regressão em `edge_2`/`edge_3`" **não foi totalmente atingido** — `edge_2` regrediu.

Causa raiz de `desp_2`/`edge_2`: viés sistemático do modelo candidato para frases iniciadas por "Até" ("Até logo", "Até a próxima"), classificadas como `saudação` independentemente do `hypothesis_template`. Testadas 6 variações (`Este texto é um exemplo de {}.`, `Este exemplo é {}.`, `O texto a seguir expressa uma {}.`, `A frase acima é uma {}.`, `O texto contém uma {}.`, `Isto é {}.`) — todas as 6 erram exatamente `desp_2` e `edge_2` da mesma forma. Não é ajustável por template; é limitação do modelo candidato. Registrado em `backend/evals/node_classifier_pt.md` como candidato a caso de regressão futuro.

## Teste primeiro (feature)

Não se aplica como pytest formal — mudança de calibração/config, não feature nova com contrato de API. A suíte de 12 casos é o teste determinístico de calibração, formalizada em `backend/evals/node_classifier_pt.md` (etapa 3, antes da troca de modelo), seguindo o espírito de `.omp/instructions/teste-primeiro.md` (medição reprodutível antes/depois, mesmos casos, mesma ordem).

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| Baseline reproduz o bug relatado pelo humano | Execução real do pipeline atual (`facebook/bart-large-mnli`) nos 12 casos, nesta sessão | Passou (reproduzido) |
| Modelo candidato testado nos mesmos casos | Execução real de `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` nos 12 casos, 6 variações de `hypothesis_template` | Passou (8/9 principais, ver Resultado pós-mudança) |
| Nenhuma regressão nos casos-limite | Mesmos 12 casos, comparação direta com baseline | Falhou (`edge_2` regrediu; `edge_3` mantido) |
| Rastro emitido por execução | `python -m Memorix.providers.bgem3_provider`, 1 execução real, log conferido em `backend/logs/node_classifier.jsonl` | Passou |

## Revisão pedagógica

Veredito: Não se aplica nesta etapa — classifier ainda não entrega conteúdo ao aluno (spike interno). Será avaliado quando o node classifier real (rótulos `flashcard`/`questionario`/`aula`) estiver ligado ao `pedagogical_understand`.

## Decisões e conflitos

- `ai-rag-specialist` consultado via hub (respondeu dentro do orçamento de 2 min): confirmou a hipótese de calibração de idioma; priorizou `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` sobre `bge-m3-zeroshot-v2.0` por consistência com a decisão já registrada em produto.md; propôs critério de aceitação (≥7/9 + margem nos casos-limite, sem gate de latência); levantou o mesmo `[ESCLARECER]` de acesso à rede para baixar o modelo.
- Sem conflito de autoridade nesta etapa. Achado adicional do `orchestrator` (fora do pedido original): Goal 1 está com execução bloqueada, o que impede a etapa 3 sem decisão explícita do humano — levado ao Esclarecer acima, não decidido unilateralmente.
- `ai-rag-specialist` (etapa 3/4): durante a construção, o humano renomeou a env var `CLASSIFIER_MODEL` → `MODEL_CLASSIFIER` em `config/config.py` concorrentemente (trabalho manual do Goal 1 em andamento) — adaptado o default explícito para o nome atual, sem reverter a mudança do humano.
- Observação (não é bloqueio): o `.env` local do humano (não versionado) tem `MODEL_CLASSIFIER=MoritzLaurer/bge-m3-zeroshot-v2.0` e `USE_CUDA=True` no momento desta sessão — isso sobrepõe o novo default do código em tempo de execução local (comportamento esperado: env sempre vence default). O rastro real gerado nesta sessão via `python -m Memorix.providers.bgem3_provider` reflete portanto `bge-m3-zeroshot-v2.0`, não `mDeBERTa`; a medição formal dos 12 casos (Resultado pós-mudança) foi feita chamando o modelo `mDeBERTa` diretamente para isolar a variável, conforme decisão do humano no gate.
- Observação técnica: `USE_CUDA=True` está setado localmente mas `torch.cuda.is_available()` é `False` neste torch `2.14.0+cpu` (build sem CUDA) — o pipeline não falhou (fallback silencioso do transformers), mas o device solicitado não corresponde ao hardware disponível. Fora do escopo desta tarefa (lógica de `DEVICE` não foi tocada); sinalizado para o humano revisar sua própria config local.
- **Colisão ao vivo (pós-etapa 4):** ao verificar (etapa 5), o `orchestrator` constatou que um processo concorrente — provavelmente o próprio humano, que informou estar "codando na mão" o goal 1 — alterou os mesmos arquivos depois da entrega do `ai-rag-specialist`: `bgem3_provider.py` voltou de 54 para 30 linhas (perdeu `hypothesis_template`, `classify()` e o rastro JSONL), o diretório `backend/evals/` (com `node_classifier_pt.md`) desapareceu inteiro, e `backend/logs/node_classifier.jsonl` foi apagado e recriado vazio só pelo smoke test de verificação do `orchestrator`. `config.py` sobreviveu intacto. Nenhuma tentativa de reescrever foi feita para não entrar em edit war. Reportado a `Main`/humano via hub; tarefa bloqueada até confirmação: descartar a versão da etapa 3 (o humano está reescrevendo à mão) ou reaplicar o diff (conteúdo exato preservado nesta tarefa e no rastro da sessão).
- **Decisão final do humano (via `Main`):** descartar o trabalho desta tarefa. O humano está reescrevendo `bgem3_provider.py` à mão e removeu `backend/evals/` de propósito, assumindo a implementação manual do goal 1. Não reaplicar o diff, não recriar `backend/evals/`. Tarefa encerrada como **Cancelada** (não por falha de execução — os critérios primários foram batidos: baseline 4/9 → 8/9 com `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` — mas por decisão de escopo do humano de assumir o código manualmente). Nenhuma mudança desta tarefa está aplicada no código atual; os números e o diff acima ficam só como referência histórica caso o humano queira consultá-los ao implementar a própria versão.
- Achado (etapa 4): critério "nenhuma regressão em `edge_2`/`edge_3`" **não foi atingido** — `edge_2` ("Até a próxima, pessoal!") passou de correto para incorreto em todas as 6 variações de `hypothesis_template` testadas; é um viés sistemático do modelo candidato para frases iniciadas por "Até", não resolvível por ajuste de template. Critério primário (≥7/9 principais) foi atingido (8/9). Reportado explicitamente, não maquiado — decisão de prosseguir com o modelo autorizado cabe ao humano à luz deste trade-off.

## Continuação manual: node classifier com Laya (2026-09-24)

Fora do pipeline formal desta tarefa (que segue **Cancelada**): o humano substituiu o zero-shot NLI pelo `Router` da Laya com um checkpoint **fine-tuned** próprio. Isso contraria o item de Fora do escopo "Fine-tuning de qualquer modelo (produto.md já descartou...)" — decisão do humano; `produto.md` não foi atualizado.

Código atual (commits `a7ac7bc`, `5eb2d27`, `856c39f`, `ce55022`):
- `config/config.py`: `ConfigLaya.language = "multilingual"`, `ConfigLaya.model = {"multilingual": "Riupul/laya-multilingual-finetuning-memorix"}`.
- `contracts/questions.py`: `LayaChoiceQuestion` (`TypedDict`: `type: Literal["choice"]`, `instructions`, `criteria: dict[str, str]`) e `CONTENT_TYPE` com os rótulos reais de produto (`flashcards` / `exercicios` / `aula` / `outro`) — resolve o item de Fora do escopo sobre trocar rótulos de demonstração.
- `providers/laya_provider.py`: só constrói o `Router` (`preload=False`, `device="cuda"`); sem `predict` no import. Nenhum código chama `predict` com `CONTENT_TYPE` ainda.
- Notebook Colab de fine-tuning (`backend/notebooks/laya_finetune_colab.ipynb`) removido do repo.

Contrato Laya `choice`: `questions: dict[str, LayaChoiceQuestion]`; `criteria` como dict `rótulo → descrição` ou lista (set é rejeitado); `instructions` obrigatório. Retorno: `answers[qid] = {type, choice, probabilities, confidence, action}`. `confidence` é `1 - H(p)/log k` (entropia normalizada), **não** a probabilidade da escolha; checkpoint avisa temperaturas inválidas → confidence não calibrada. Decidir por `probabilities[choice]` com limiar.

| Execução | Método | Status |
| --- | --- | --- |
| Pergunta sem `instructions` | `python -m backend.src.Memorix.providers.laya_provider` | Falhou: `ValueError ... no 'instructions'` |
| `criteria` como set + `preload=True` | idem, `-X faulthandler` | Falhou: `access violation` ao carregar safetensors no preload de 3 checkpoints (provável memória, não isolado) |
| `criteria` lista, `preload=False`, state "Queria criar umas aulas sobre Python" | idem | Passou: `aulas` p=0,659 (exercicios 0,203, flashcards 0,125, outro 0,013), confidence 0,34, rota `multilingual` |

Pendências (trilha IA): baseline de ~20 casos reais para `CONTENT_TYPE` (só rótulos vs. com descrições), medindo acurácia e `probabilities[choice]`; nenhuma medição antes × depois feita ainda. Device efetivo (CUDA vs CPU) não confirmado. Revisão pedagógica: Não se aplica (output ainda não chega ao aluno).
