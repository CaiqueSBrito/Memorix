# 013 — Continuação de todos os goals: backend e IA

Goals: 1.3, 1.4, 1.5, 2, 3, 5, 6 e 7; API reutilizável pelo futuro frontend/mobile (4). Trilha: IA. Estado: Implementação e verificação local concluídas com ressalvas de qualidade; goals de qualidade não aceitos automaticamente.

## Pedido e decisões humanas — 2026-10-31

Pedido literal: "continue a implementação de todos os goals, implemente o backend e a IA, front vai ser feito posteriormente".

Respostas aos gates desta sessão:
- `Autorizar execução contínua nesta solicitação`: sequência retrieval/evals → recusa/geração com fontes → respostas/acurácia/planejamento → dissertativas/métricas E2E. Dispensa pausas intermediárias de plano/teste e uma tarefa por sessão; preserva teste primeiro, evals, revisões, privacidade e aceite final. Sem commit/push/deploy.
- `Dispensar somente o pin nesta solicitação`: especialistas podem ser acionados sem afinidade de conta confirmada.
- `PostgreSQL local com pgvector`: banco isolado de desenvolvimento/testes, preservando `.env` Supabase; não prova produção.
- `Usar subagentes nativos nesta solicitação`: exceção ao transporte Orca/worktrees para delegação, ownership exclusivo de arquivos.
- `Consentimento verificado pelo admin`: admin atesta verificação externa do responsável, emite convite de uso único vinculado ao menor; sem autoconsentimento nem documentos pessoais nos logs.
- `Acerto por item e revisão espaçada simples`: MC/V-F por gabarito; flashcards por autoavaliação e dissertativas por rubrica em indicadores separados; primeira tentativa distinta de revisões, erro reinicia sequência e acertos avançam intervalos fixos.
- `Autorizar limpeza pontual dos testes obsoletos`: remover exigência de ausência de vetores no head e varredura de texto-fonte por credenciais; preservar constraints, segurança comportamental e migração 0001; marcar testes de banco.
- `Corrigir testes novos e registrar novo baseline`: corrigir fronteiras de simulação erradas e eliminar verificações de mero encaminhamento, sem afrouxar autorização/isolamento/persistência; registrar novos hashes.
- Instrução posterior literal: `não pergunte, pode rodar sem perguntar nada pra mim, faça o que achar melhor`. Não abrir novas perguntas/gates nesta execução; escolher opções conservadoras e registrar decisões. Não enviar dados de aluno a terceiros nem efetuar deploy desnecessário.

## Escopo e critérios

- Backend/API sem frontend nem app mobile; autenticação e autorização aluno/admin, isolamento entre alunos e tratamento explícito de consentimento antes de guardar dados de menores.
- Retrieval real sobre os PDFs disponíveis, pgvector/FTS, embedding local, reranking e gate medidos em casos reais. Preservar migração 0001 e registrar métricas, inclusive resultados que não atingirem as metas.
- Laya integrado e avaliado; ambiguidade não gera conteúdo. Geração local estruturada de questões MC/V-F, flashcards e aulas com fontes e validação; tema ausente recusa. Dissertativas com rubrica e correção rastreável.
- Registro de respostas; acurácia por acerto por questão, histórico, plano de revisão e indicações justificadas por respostas e material do acervo.
- Rastro sem dados do aluno; evals de retrieval e geração separados, métricas E2E e revisão pedagógica. Nenhum resultado não medido será declarado aprovado.
- Provar via banco isolado e requisições reais da API, incluindo autorização, geração, resposta e plano.

## Plano e ownership

- Sessão principal: infraestrutura PostgreSQL local e modelos existentes; configuração SSL local compatível com Supabase; dependências; execução dos testes primeiro e verificação final; documentação compartilhada e integração.
- `orchestrator`: domínio backend, contas/sessões/consentimento, respostas/acurácia/revisões/indicações, migração 0003, HTTP API e testes novos do domínio/API. Revisar integração contra os critérios; encaminhar decisões não técnicas ao humano.
- `ai-rag-specialist`: migração 0002, embeddings/retrieval/reranking/gate, pipeline de geração e correção, Laya, evals, testes novos de IA e revisão técnica dos critérios IA.
- `pedagogy-specialist`: revisão somente leitura após os fluxos existirem; problemas bloqueantes corrigidos antes da entrega.

## Interfaces compartilhadas iniciais

A API usa `backend.src.Memorix.pipeline.service.StudyPipeline` com:
- `generate(request: dict, *, session, trace_id: str | None = None) -> dict`
- `grade_answer(content: dict, answer: str, *, trace_id: str | None = None) -> dict`
- `index_documents(session, doc_ids: list[int] | None = None, trace_id: str | None = None) -> dict`

Os detalhes de payload são definidos pelo especialista IA e comunicados ao owner da API antes da integração; não criar adaptadores duplicados. O serviço recebe `Session` SQLAlchemy para utilizar o mesmo banco/transação do backend. Conteúdo persistido possui identidade e ownership controlados pelo backend; conteúdo não validado não é entregue ao aluno. Migração 0003 depende de 0002. Mudanças de nomes/exportados exigem referências via LSP disponível. Sessão principal é única owner de `requirements.txt`, README, goals e progresso.

## Baseline observado

- `python -m pytest backend/api/tests -m "not banco" -q`: 56 passed, 14 deselected, 10 errors (40,71 s). Os dez casos de persistência não têm a marca `banco` e tentaram conectar no Supabase; falharam antes de migrar com `FATAL (ENOTFOUND) tenant/user … not found`. Nenhuma migração executada nessa tentativa. Não repetir contra o Supabase sem correção de configuração.
- `omp session --help`: só pack/unpack/moved; não permite pin nesta API.
- `orca skills get orchestration --json`: `command not found: orca`; exceção humana acima.
- Docker iniciado; container `memorix-dev-013` com PostgreSQL 17.11 e pgvector, vinculado só a `127.0.0.1:55432`. Bancos separados `memorix_dev` (corpus/smoke) e `memorix_test` (testes com downgrade). Conexão real confirmada por SQL. `.env` original preservado; `.env.local` ignorado selecionado por `MEMORIX_ENV_FILE`, `DB_SSLMODE=disable` somente local, padrão continua `require`.
- Ollama local tem `llama3:latest` (4,7 GB). Pesos BGE-M3 revisão `5617a9f61b028005a4858fdac845db406aefb181` e reranker revisão `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` baixados do Hugging Face sem enviar conteúdo do acervo.

## Teste primeiro e rastreabilidade

| Contrato | SHA-256 inicial | Falha antes |
| --- | --- | --- |
| Ambiente de banco isolado | `781c8000b5d026813c1a2e4726d874462fdbad372a05bfb84cbbfe03c20251d1` | Arquivo escolhido ignorado, URL ainda usava Supabase/SSL require |
| Pipeline IA | `28ade8f5e64ea6087bc688c70f48a1e0fd0d3f9f760e9d76b771075d845c1824` | 1 failed/3 errors: providers e pipeline.service ausentes |
| API/estudo | `c1a0e19b2f20d04b9a44199fd1b9d3db2b414a5b5a0d1c6f5af48ca7f8472d49` | 8 erros junto ao teste PDF: API ausente |
| API PDF | `4035129e89588e5e4b8a9142c8281fe43718524543f400b5fc873d32031cc172` | API ausente |
| Consentimento e separação das métricas | `2d9ea0e9c6792f165d90db94abfa7502a033f3b6808b0a1bca5b24d8cec79e53` | 3 erros: API ausente |
| Correlação de PDF | Não aferido antes; hash final no manifest abaixo | TypeError: parâmetro trace_id ausente |
| Rotas de material | `39511bbf399a58f8cbac4b45c0d92fdd6cac56f0d1879a9a8e74750ffb8e9fe6` | Primeira tentativa inválida: NameError na fixture compartilhada; corrigir antes de provar falha 404 |

Correções de testes autorizadas pelo humano acima; baseline final em `backend/evals/results/verification_013.json`, incluindo33arquivos de testes/fixtures. Migração0001 preservada: `eba47c8667c6d58aae774f8b41963abdadb1d81752088e5e019f50e6e3576562`. LSP consultado: nenhum servidor disponível; referências verificadas por busca literal antes das mudanças exportadas.

## Evidências / pendências

## Integração e provas reais — histórico intermediário

- PostgreSQL local confirmado por SQL: 17 documentos, 7.158 chunks, 7.158 vetores e um modelo de embedding. `0001` preservada. A `0003` tinha recebido edição desta própria sessão antes de se estabilizar; a primeira tentativa de reaplicá-la falhou porque o downgrade final esperava `login_limits`, ausente no schema intermediário. Reparo restrito ao schema de estudo comprovadamente vazio do banco DEV, sem apagar acervo/vetores; migração final reaplicada e coluna `sequence` confirmada. Não foi criado shim `IF EXISTS` em migração de produto para ocultar o desvio.
- Curadoria genérica adicionada após erro científico REAL: migração `0004`, intervalos por SHA-256 e offsets canônicos, ambos os ramos de busca excluem sobreposição. POST/GET/DELETE admin; conteúdo/fonte/reveal/answer já gerados ficam410, histórico preservado/sinalizado e tentativas contaminadas separadas da acurácia/plano/recomendações.
- Suíte integrada com `python-dotenv --override`, banco TESTE separado: **114 passed, 1 warning, 29,80 s**. Aviso existente do TestClient/HTTPX, não suprimido. Prova não equivale à qualidade pedagógica de inferência.
- HTTP real em loopback: health, cadastro adulto, login admin, papel aluno403, menor sem convite403, convite admin verificado fora do sistema/vinculado ao e-mail, replay403, logout204/revogação401, fonte autenticada200/anônimo401 e orçamento de login cinco401 seguido429.
- HTTP real de curadoria: span `id=1`, SHA `0e430047bf992ce0b3adc9d68463efec988b8ebd1d3e7dee9547a641eab92921`, offsets `[36518,36593)` aplicado por admin no DEV. Antes chunk `6:30`200 continha a afirmação problemática, depois410; chunk `6:90` não sobreposto continua200; aluno não cria exclusão403 e admin lista persistida. **Span mantido no DEV**, não removido para inflar métricas.
- Dois testes antigos de implementação foram removidos com autorização: ausência de vetores/lista única de migração e varredura de arquivos por strings de credenciais; constraints e contratos funcionais permanecem. Primeiro run completo104 passed/2 failed revelou ainda teste de migração única e classe errada no teste novo de rastro PDF; corrigidos, hashes finais registrados na prova.
- Fronteira de geração: teste novo `test_study_generation_errors.py`, SHA `9edab1a8e1f7a25ef4349df313e9a173bfec1fc1e34447fdb635ebdf66199511`, falhou antes por201 para prompt/tema em branco e500 para saída IA rejeitada. Validação Pydantic e resposta422 genérica com `trace_id` implementadas; erro inesperado permanece500, conteúdo rejeitado não é persistido.

## Revisões e correções

- Segurança: revisão somente leitura concluiu que raízes de login sem orçamento, upload antes da autorização/limite, cronologia por início da transação e campos extras IA públicos foram corrigidas. Main reproduziu as falhas e verificou as regressões; risco TLS remoto `require` sem validação de identidade continua explícito, sem atestar produção.
- `pedagogy-specialist` configurado foi bloqueado por429. Revisor nativo com as mesmas lentes fez revisão fallback, não execução do modelo original nem aceite humano. Achados reais: flashcard sem reveal, aviso parcial perdido, fonte incorreta, pergunta/rubrica dissertativa inadequada, desvio do objetivo e feedback contraditório. Correções e prova finita finais estão abaixo; limitações gerais dos evals continuam explícitas.
- A primeira fatia IA terminou parcial; `AiFinish` também encontrou limite do provider. A sessão principal integrou a geração/validação/correção final; owners exclusivos entregaram backend, curadoria, intenção e calibração. Nenhum stub ou inferência simulada foi entregue no runtime.
- Modelo local candidato Qwen3 4B Instruct 2507 Q4 baixado sem enviar acervo, licença Apache-2.0. Seleção do provider só deve mudar após comparação nos mesmos casos e rastro/documentação correspondente.

As pendências funcionais desta fase foram exercitadas na prova final abaixo. Não confundir implementação/provas locais com aceite integral de qualidade: fonte editorial, curadoria científica completa, região/identidade TLS Supabase, HTTPS e revisão jurídica não foram resolvidos pelo banco local.

## Baseline final de geração local (observado no artefato)

`backend/evals/results/generation_llama_final.json`: 20 casos, `llama3:latest`, temperatura0, contexto4096, embeddings/reranker fixados, gate0 e um span ativo. `valid_output_rate=0,70` (inclui recusas corretas, não significa 14 conteúdos estudáveis); 21 afirmações factuais examinadas, 12 apoiadas (`0,5714`); relevância juiz local+status `0,65`. Tipos com amostra: flashcards, aula e V/F; essay contém erro de validação, nenhum MC pedagógico adequado aprovado. Não é evidência de geração completa aceita.

A revisão orientativa conferiu exemplos reais: ret01 flashcard útil; ret04 V/F fiel com ressalva de explicitar o recorte do tropismo; aula ret07 só repetia conclusão sem explicar o “como”; fórmula V/F ret12 perdeu expoentes; MC ret11 desviou de atividades escravistas para teocracia. Esses casos viraram regressões/ajustes, não foram apagados para melhorar taxa. Métrica de sobreposição com a âncora não é sinônimo de relevância didática: fontes alternativas válidas precisam de revisão, sem inflar resultados.

Qwen3 4B nos mesmos20 casos, mudando só o modelo frente ao baseline Llama: formato/recusa válidos0,50, fidelidade11/14 e relevância0,50 (`generation_qwen20.json`); candidato reprovado. Pesos dele removidos para liberar disco. Qwen2.5 7B Q4 passou a ser a implementação local; sua comparação posterior inclui mudanças de prompt/validador/gate, portanto não atribuir o resultado só ao modelo. Llama preexistente preservado, nenhum download após a explicação pedida pelo humano.

Regressões posteriores ao baseline114 cobrem objetivo, fontes usadas, prompt/tema,422, aula, rubrica, calibração, afirmações atômicas e evidência de crédito. Verificação final: **151 passed,1 warning,33,58s**. Aviso TestClient/HTTPX conhecido, não suprimido; fronteiras de inferência simuladas nos contratos, modelos reais em provas separadas.

## Prova funcional final e decisões de integração

- `backend/evals/results/http_final_013.json`: API real, PostgreSQL DEV e modelos locais, sem mocks de inferência. Cinco gerações201 (MC,V/F,flashcard,aula,essay) e leitura persistida200; gabarito/rubrica/citação literal ocultos inicialmente. Uma outra aula foi rejeitada422 por suporte factual4/5; SQL nativo confirmou zero conteúdo associado ao seu trace_id. Não foi ocultada para fazer a prova parecer universal.
- Respostas: sete objetivas (cinco corretas), uma autoavaliação e duas dissertativas. Histórico10; acurácia sóMC/V-F, duas primeiras/cinco revisões. Replay200 sem duplicar, payload divergente409; outro aluno recebeu404 para conteúdo/answer/reveal.
- Plano real avançou por1/3/7/14dias; indicações apontaram às respostas que as motivaram e materiais acessíveis. Fonte6:30 continuou410,6:90 continuou200. SQL confirmou17PDFs/7.158chunks/7.158vetores e um span ativo. Três sessões sintéticas novas foram revogadas após a prova; dados apenas no DEV.
- Essay: rubrica JSON de dois critérios independentes e fatos esperados; referência composta no servidor, sem pedir ao modelo um segundo parágrafo redundante. Pergunta/objetivo são julgados separadamente de afirmações factuais; não se exige inventar chunk_id para uma pergunta neutra.
- Correção só recebe rubrica validada+resposta, não cópia redundante do livro. Schema limita evidência a frases literais da resposta; pontos sem evidência são rejeitados. Total e feedback derivam no servidor de pesos/pontos/esperado/evidência. Resolveu contradição real de crédito e linguagem que confundia resposta errada com omissão. `functional_samples_qwen25_v6.json` e HTTP: parcial0,5/1, errada0/1; rastro sem resposta bruta e prompt_hash estável entre respostas distintas.
- Revisão fallback conferiu MC,flashcard,aula,V/F e essay/duas correções: aprovadas com ressalvas **somente as amostras**. Não é aceite do humano, execução do especialista bloqueado ou prova de correção de todo o corpus.
- Modelo atual: `qwen2.5:7b-instruct-q4_K_M`, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`,4.683.087.332bytes; temperatura0/contexto4096. Hardware RTX4050/6GiB, um worker, sem inferência concorrente. Gerações HTTP positivas37,72–47,63s; p95 retrieval quente469ms não significa requisição completa em menos de1s.
- Gate: regressão do calibrador anterior demonstrou dependência inadequada do máximo negativo. Correção usa ambas as classes e margem, folds sem o próprio caso: FAR0/8,FRR0/12, limiar `-1.067626953125`; todos20 labels preservados. Evidência pequena e sem garantia externa.
- O run `generation_qwen25_verified.json` preserva uma falha do harness: quarentena da âncora mudava indevidamente o alvo positivo para recusa, excluía esse caso da relevância e nomeava bloqueios como número de spans ativos. Regressão nova falhou antes (`expected=not_found` em tema ainda respondível), depois passou. Harness corrigido: preserva o rótulo original, julga todos os casos, conta spans reais e marca revisão sem proibir o tema. Não alterar o baseline histórico nem o span para melhorar score.
- Hashes finais, comando/resultado da suíte e provas SQL/HTTP: `backend/evals/results/verification_013.json`. O script temporário de diagnóstico foi removido; JSONs e falhas reais foram mantidos como evidência. Sem frontend, commit,push ou deploy.

## Resultado final medido e limites de aceite

- `generation_final_013.json`: todos20casos julgados,1span ativo corretamente contado;8/12positivos entregues pelo validador,4rejeitados e8/8fora recusados. `valid_output_rate=0,80` inclui recusas, não16conteúdos estudáveis. Fidelidade do juiz local29/38 (`0,7632`), relevância combinada10/20 (`0,50`), overlap da âncora3/12 (`0,25`). Nenhum caso difícil foi removido do denominador.
- Falhas reais remanescentes: ret10 fala de direitos gerais sem abordar tortura/pena de morte; ret11 troca atividades econômicas escravistas por origem dos escravos. Juiz local não é garantia de alinhamento. Fonte alternativa6:29 no ret02 não contém o intervalo excluído, mas tabela agregada não comprova todos os detalhes sobre fotossíntese que o modelo escreveu; exige revisão científica.
- Diagnóstico da busca: substituir tema por pedido integral baixou recall@5 pós-curadoria de8/12 para7/12 e aumentou FRRleave-one-out0→1/12. Tema+objetivo ficou8/12, mas FAR1/8 eFRR2/12. Ambos rejeitados; a hipótese de que bastaria usar o pedido inteiro **não se confirmou**. Baselines anteriores à curadoria permanecem separados.
- Diagnóstico do juiz: mudar flags, explicitar objetivos ou usar Llama já instalado não eliminou todos os falsos aceites; comparação de relevância sem fontes rejeitou positivos MC/V/F. Experimentos rejeitados em `judge_objective_probes_013.json`; provider restaurado ao SHA medido `7571e202da5828765c86b6dbdcf552cf9dc61f5b67629da879e3055e7d9506dc`, sem complexidade de mais juízes/modelos no produto.
- Última suíte após restauração: **151 passed,1 warning,29,35s**. API final iniciada em loopback com um worker e sem access-log; `/health` respondeu `{"status":"ok"}`. Banco/corpus/modelos preservados; nenhuma operação de frontend, push ou deploy.
- Implementação executável de todas as fatias autorizadas entregue. **Não declarar todos os goals de IA aceitos**: qualidade geral insuficiente no conjunto medido, corpus parcialmente curado e condições de produção/jurídicas ainda não comprovadas. Autorização para executar não é autorização para esconder essas falhas.

