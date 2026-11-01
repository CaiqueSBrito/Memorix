# Pipeline de trabalho — Memorix

Nível 2 da ordem de autoridade: abaixo do humano, acima do `orchestrator`. Só muda com aprovação do humano.

## Princípios

1. **Explorar → planejar → construir → provar.** Sem plano quando a mudança cabe numa frase.
2. **Uma tarefa por sessão**, estado limpo ao final, progresso registrado para a próxima sessão. Tarefas em paralelo só em worktrees separados (ver Worktrees).
3. **O quê e por quê antes do como.** Ambiguidade vira `[ESCLARECER: pergunta]`, nunca palpite.
4. **IA só muda com medição.** Baseline antes, mesmos casos depois, retrieval e geração medidos separados, uma variável por vez. LLM-como-juiz nunca é a única prova.
5. **Evidência, não afirmação.** Status exatos: Passou, Falhou, Não executado, Bloqueado, Não se aplica (com motivo).
6. **Erro vira revisão.** Toda falha encontrada (bug, alucinação, item pedagogicamente ruim) vira caso de regressão permanente — o Memorix revisa os próprios erros como o aluno revisa os dele.

## Trilhas

| Trilha | Quando | Etapas | Gate humano |
| --- | --- | --- | --- |
| **Rápida** | cabe numa frase; não é feature; sem IA; sem efeito no aprendizado | 3 → 4 → 6 | nenhum; só relatório |
| **Padrão** | vários arquivos, abordagem incerta ou comportamento muda | 0 → 6 | plano + teste (se feature) + aceite final |
| **IA** | retrieval, chunking, embeddings, prompt, modelo ou geração | 0 → 6 + baseline/eval + rastro; revisão pedagógica se o aluno vê o output | plano + teste (se feature) + aceite final |

Na dúvida, a trilha mais pesada. A trilha pode subir durante o trabalho; nunca desce em silêncio.

## Etapas

**0. Retomar** (início de toda sessão) — ler `.omp/progress/progresso.md` e `git log --oneline -10`; rodar a verificação básica do projeto quando existir. Projeto quebrado → consertar antes de trabalho novo.

**1. Entender** — `orchestrator`, só leitura. Ler `.omp/context/produto.md`; pedido fora do escopo registrado lá → confirmar com o humano e registrar no histórico de escopo.
Saída: `.omp/tasks/NNN-slug.md` com goal (`.omp/goals/`), objetivo, critérios de aceitação verificáveis, fora do escopo e `[ESCLARECER]`.
Gate: goal com execução autorizada (bloqueado → só discovery/planejamento, sem código de produto); nenhum `[ESCLARECER]` bloqueante aberto (pergunte ao humano só o que arquivos não respondem).

**2. Planejar** — `orchestrator` + especialista líder.
Saída: arquivos afetados, passos, quem faz o quê, como será provado.
Trilha IA: baseline registrado (configuração atual + resultado nos casos) e hipótese testável ("mudar X melhora a métrica Y sem piorar Z").
Gate humano: "ok" no plano. **Mudança pequena** (≤3 arquivos afetados, sem dependência nova): funde com o gate de teste da etapa 3 — leve plano + teste falhando (pelo motivo certo) num só pedido de "ok"; não abra dois gates sequenciais para isso.

**3. Construir** — IA → `ai-rag-specialist`; demais → `orchestrator`.
- **Feature:** teste primeiro, conforme `.omp/instructions/teste-primeiro.md` (teste → falha pelo motivo certo → gate humano → implementação sem tocar no teste). Mudança pequena: esse gate é o mesmo da etapa 2 (ver acima), não um segundo.
- **RAG:** toda etapa tocada emite o rastro de `.omp/instructions/rag-rastreabilidade.md`.
- Menor mudança que cumpre os critérios. Descoberta que muda escopo → volta para 2.

**4. Provar** — quem construiu executa.
Testes e scripts reais; `sha256` dos testes igual ao registrado antes da implementação. Trilha IA: mesmos casos do baseline, antes × depois, com exemplos representativos (não só os favoráveis); rastro conferido em ao menos uma execução real.

**5. Revisar**
- `pedagogy-specialist` quando o output chega ao aluno (veredito + achados).
- `orchestrator` confere cada critério de aceitação contra a evidência.
- Gate humano: aceite final.

**6. Registrar** — antes de declarar a tarefa encerrada, atualizar os arquivos afetados **pelo resultado real**, não só o código: tarefa em `.omp/tasks/` (estado, evidências, decisões, pendências), `.omp/progress/progresso.md` e, quando correspondentes, `.omp/goals/` (índice/status), `.omp/context/produto.md` (escopo/decisões), `README.md` (estado técnico/uso) e instruções cujo contrato mudou. Conferir que nenhum desses arquivos afirma que algo implementado não existe, ou que uma decisão substituída ainda vigora. Registrar cada falha encontrada como caso de regressão. Não mudar status de goal nem autorização sem decisão do humano. Em worktree, aplicar a divisão abaixo.

Estados da tarefa: Entender, Planejar, Construir, Provar, Revisar, Concluída, Bloqueada (com condição de desbloqueio), Cancelada.

## Worktrees (tarefas em paralelo, Orca)

- Uma tarefa = um worktree, criado por `powershell -File .omp/scripts/worktrees.ps1 [-Agent omp]` no checkout principal. O script pula tarefas Concluída/Cancelada e as que já têm worktree. O worktree parte de `develop`.
- `.omp/` e `venv/` são junction para o checkout principal (um estado só); `.env` é copiado. Remover o worktree pelo Orca não apaga o alvo da junction.
- Tarefa nova (etapa 1, número NNN) só é criada no checkout principal: evita número duplicado.
- No worktree, a etapa 6 atualiza o arquivo da própria tarefa e identifica os demais documentos correspondentes; o checkout principal sincroniza `.omp/progress/progresso.md`, goals, contexto e README depois do merge, antes de declarar a integração concluída. Não editar documentos compartilhados pela junction a partir do worktree.
- O worktree só vê código commitado em `develop`. Tarefa que depende de outra (ou de trabalho não commitado) espera o commit/merge, que continua sendo gate humano.
- Duas tarefas que mexem nos mesmos arquivos não rodam em paralelo.

## Casos de avaliação (trilha IA)

- Local: `backend/evals/` — pertence ao produto; criado na primeira tarefa de IA.
- Começar com ~20 casos reais; crescer a cada falha encontrada.
- Balanceados: casos em que deve responder e casos em que deve dizer "não está no material".
- Cada caso: entrada, trecho-fonte esperado, critério de resposta aceitável.
- Duas suítes: **capacidade** (pode falhar; é a meta) e **regressão** (~100%; não pode cair). Caso de capacidade estável gradua para regressão.

## Colaboração entre agentes

**Tempo:** sem limite por acionamento (removido pelo humano em 2026-10-01: "tire o limite de tempo"; antes eram 2 minutos). Entregar completo vale mais que entregar rápido. Pesquisa na internet: poucas buscas curtas, fontes primárias, parar quando tiver o suficiente.

**Conversa** (via `hub`, uma rodada, antes do trabalho principal) — **só quando 2 ou mais especialistas são acionados na mesma tarefa**; um único especialista acionado não tem divergência a resolver, pula direto para o trabalho:
1. **Entendimento** — cada especialista acionado manda aos outros acionados e ao `orchestrator`: o que entendeu do pedido (1–3 linhas) e sua opinião inicial (riscos, o que faria).
2. **Resposta** — lê a mensagem do outro e responde uma vez: concorda, discorda (com motivo) ou complementa.
3. **Seguir** — trabalha com o entendimento combinado. Divergência não resolvida vai no relatório para o `orchestrator` decidir pela ordem de autoridade.

Não esperar resposta indefinidamente: sem retorno do outro em ~30 s, seguir e registrar.

## Sempre com o humano

- Commit, push, deploy, operação destrutiva.
- Provider/modelo pago ou envio de dados a terceiros.
- Aceitar regressão ou evidência Falhou.
- Alterar teste já aprovado.
- Adotar ferramenta dedicada de observabilidade/rastreio.
- Criar goal, mudar status ou autorizar execução de goal.
- Mudar este pipeline ou a ordem de autoridade.

## Modelo de tarefa

```md
# NNN — título
Goal: N — nome        Trilha: Rápida | Padrão | IA        Estado: Entender

## Objetivo

## Critérios de aceitação
- [ ] verificável 1

## Fora do escopo

## Esclarecer
- [ESCLARECER: ...]

## Plano
| Passo | Quem | Arquivos |

## Baseline (IA)
Configuração: … | Casos: … | Resultado: …
Hipótese: …

## Teste primeiro (feature)
| Critério | Teste | Falhou antes (motivo) | sha256 |

## Evidências
| O quê | Método | Status |

## Revisão pedagógica
Veredito: … | Achados: …

## Decisões e conflitos
```
