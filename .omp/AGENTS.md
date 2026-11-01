# Memorix — instruções para agentes

Ordem de autoridade: humano > pipeline (`.omp/pipeline/pipeline.md`) > `orchestrator` > `ai-rag-specialist` > `pedagogy-specialist`. Exceção: em decisão técnica de IA/RAG (retrieval, chunking, embeddings, modelo, prompt, avaliação), `ai-rag-specialist` prevalece sobre o `orchestrator`. Escopo, sequência de tarefas, roteamento e gates continuam com o `orchestrator`; a posição vencida vai para o relatório.

Todo trabalho segue `.omp/pipeline/pipeline.md`: comece pela etapa 0 (ler `.omp/progress/progresso.md`). Tarefas ficam em `.omp/tasks/`. Trilha Rápida dispensa especialistas; Padrão e IA passam pelo `orchestrator` (`.omp/agents/`).

Ao terminar uma tarefa, siga a etapa 6: atualize os arquivos correspondentes ao resultado (tarefa, progresso e, quando afetados, goal/índice, contexto, README e instruções) **antes** de informar conclusão; em worktree, respeite a sincronização no checkout principal após o merge.

Convenção de código: funções, variáveis, parâmetros, constantes e atributos internos próprios, inclusive em helpers, fixtures e testes, têm nomes em inglês (`snake_case`; `UPPER_SNAKE_CASE` para constantes; `test_` nos testes). Preserve nomes exigidos por ferramentas e não traduza contratos externos, dados persistidos nem conteúdo em português do produto.

Antes de acionar `orchestrator` ou `ai-rag-specialist`, a sessão principal em `openai-codex` deve executar `/session pin caique.ds.brito@gmail.com`; os subagentes herdam a afinidade da sessão. O pin prefere essa conta, mas não impede fallback em caso de indisponibilidade/limite. Modelos dos especialistas estão em `.omp/agents/`.

Só a sessão principal fala com o humano: quando o `orchestrator` devolver um gate ou `[ESCLARECER]`, pergunte ao humano usando a ferramenta de pergunta com opções (`ask`) — nunca só texto corrido — com as alternativas e a recomendação do `orchestrator`/especialista; repasse a resposta literal ao `orchestrator` (via hub) para ele continuar. Nunca aprove um gate em nome do humano.
