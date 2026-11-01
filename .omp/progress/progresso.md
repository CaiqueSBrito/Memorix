# Progresso — Memorix

Lido na etapa 0 de toda sessão; atualizado na etapa 6.

## Estado atual

- Continuação **015 concluída no recorte implementado**: benchmark restaura/isola captura de amostras e feedback dissertativo preserva trechos incorretos mesmo com critério zerado. Provas reais no Qwen/API e regressões passaram. Decomposição de objetivos sem ganho comprovado não foi incorporada; sem downloads/frontend/perguntas. Qualidade geral dos goals continua em andamento.
- Backend implementado: API HTTP (`backend/api/main.py`), contas/sessões, convite administrativo para menor, conteúdo por aluno, respostas idempotentes, acurácia/revisão/indicações, vetores/FTS e pipeline IA local. Contratos e fluxos reais verificados; qualidade geral dos modelos tem limitações medidas, não aceite automático.
- Banco local `memorix-dev-013`, PostgreSQL 17.11/pgvector em `127.0.0.1:55432`: `memorix_dev` tem **17 PDFs, 7.158 chunks e 7.158 vetores**; `memorix_test` separado para fixtures que fazem downgrade. `.env` Supabase original preservado; conexão remota agora responde `tenant/user … not found`, não timeout de rede.
- Configuração: `.env.local`/`.env.test` ignorados; `MEMORIX_ENV_FILE` não sobrepõe variáveis de processo existentes. Um serviço herdou `DB_*` Supabase e falhou500; corrigido o isolamento do processo com valores locais explícitos. Preferir CLI `python -m dotenv -f .env.local run --override -- ...` para não herdar conexão remota sem perceber.
- Última suíte: **155 testes passaram,1warning,29,47s**, PostgreSQLTESTE isolado. Na015, API real retornou201/nota0 preservando a frase incorreta no feedback e no histórico; replay200 sem nova correção. Benchmark público real capturou11registros; chamadas Qwen ordinárias posteriores, após sucesso e erro, não alteraram suas amostras. API `memorix-api-015` em `127.0.0.1:8000`,um worker,health200. Evidências/hashes em `verification_015.json`; provas013/014 preservadas.
- IA medida: dense/hybrid/hybrid+reranker recall@5 **4/12 → 5/12 → 9/12**, p95 quente do último **469 ms**. Laya **17/20**. O calibrador antigo `max(negativos)+epsilon` não usava positivos nem margem e tinha FAR leave-one-out1/8. Calibração corrigida usa ambas as classes, máximo de margem com prioridade de FAR, e cada fold treina só nos outros19: **FAR0/8, FRR0/12**, todos20 labels preservados. Limiar runtime `-1.067626953125`; resultado empírico, sem garantia externa. Artifact `backend/evals/results/gate_calibration.json`; baseline natural0 com FRR2/12 preservado.
- Curadoria DEV: intervalo ret02 por SHA/offset em quarentena (`id=1`); chunk6:30 passou200→410,6:90 permanece200. SQL nativo confirmou1span e zero conteúdos da aula rejeitada422. Uma exclusão não proíbe o tema inteiro: fontes alternativas podem ser usadas, mas exigem revisão. Amostras reais dos cinco tipos e correção receberam revisão orientativa com ressalvas; feedback livre contraditório foi substituído por composição de critério/nota/evidência/esperado no servidor. Corpus não integralmente auditado; erro editorial original permanece.
- Modelos locais: BGE-M3 `5617a9f61b028005a4858fdac845db406aefb181`, reranker `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, Laya `a200a32c9c4859d9ec5ed84a8a160465ec2dcb5b`. Geração `qwen2.5:7b-instruct-q4_K_M`, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e` (4.683.087.332bytes). Llama3 preexistente preservado; Qwen3 4B reprovado foi removido para liberar espaço. **Nenhum novo download após a explicação ao humano.** RTX4050/6GiB, dados de aluno sem inferência remota.
- Evals finais `generation_final_013.json`:20/20casos julgados,1span ativo;8/12positivos aprovados pelo validador,4rejeitados,8/8fora recusados. Fidelidade local29/38 e relevância combinada0,50. O validador local ainda aceita alguns objetivos errados (ret10/ret11); **goals de qualidade de IA continuam em andamento**, apesar da implementação/prova dos cinco formatos. Reescrita da busca por pedido integral e prompts alternativos do juiz foram medidos e rejeitados, não incorporados sem ganho. Evidências/hashes em `verification_013.json`; detalhes/limites na tarefa013 e README.
- Backend014: migração0005aplicada, PKrevelação(content_id,item_id). HTTP confirma rejeição semgabarito/history, outroaluno404,GET405,POST200idempotente semtentativa,rating201/replay200; replay legado sem inventar estado testado. Quatro sessões sintéticas novas revogadas. Rastro da geração nova tem2/2claims apoiadas,gate0ms observado e pedido bruto ausente.
- Medição014 separou dense+reranker de hybrid+reranker:6/12→8/12, ganhosret05/ret06 sem perdas, FARleave-one-out0 nos dois, p95quente454→468ms,100consultas/variante. Evidência isolada agora sustenta manter componente lexical segundoC-ret; sem trocar gate/query nem confundir com baseline pré-curadoria9/12. Experimentos extras de seleção não corrigiram ret10 e não foram adotados.
- Candidato schema evidence-first nosmesmos20casos piorou entregaspositivas8→6/12e relevância10→9/20; razão claims29/38→29/36não prova ganho geral. Rejeitado, `grounded-pt-v5` e código de geração anterior restaurados. Evidências/limites/hashes em `verification_014.json`, `generation_evidence_first_014.json` e tarefa014; nenhum experimento deixou comportamento parcial no runtime.
- Na015, a falha de captura foi reproduzida com dados sintéticos em dois caminhos; `finally`, filtro por thread e lock corrigem o lifetime sem mudar casos/métricas. Teste adicional cobre outra thread. Não houve evidência de vazamento de dados reais. Substituição do provider continua global durante o benchmark; GPU segue sem inferência concorrente.
- Decomposição015:20/20planos literais,ret10com três objetivos. Fontes independentes/contextuais não sobrepõem a âncora esperada; com tema prefixado, pena de morte fica abaixo do gate. Candidato rejeitado antes de alterar runtime, sem nova métrica geral de geração. Feedback zero foi revisto estaticamente e provado por HTTP/rastro; duas sessões sintéticas revogadas. Goal de qualidade não recebeu aceite fictício.
- Persistência: a tarefa 002 está **Concluída** (aceite final do humano em 2026-09-24; 11/11 critérios provados no banco de dev):
  - Supabase Postgres 17.6 via SQLAlchemy 2.1 + Alembic + psycopg2, pelo Supavisor em **modo session** (IPv4, `aws-0-us-east-1.pooler.supabase.com:5432`, user `postgres.<ref>`, `sslmode=require`, QueuePool + `pool_pre_ping`). A conexão direta `db.<ref>` só tem IPv6 e não resolve nesta máquina. `supabase-py` descartado.
  - `.env`: variáveis separadas `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_DATABASE`. `DB_CONNECTTION_STRING` foi removida pelo humano. `backend/api/config/config.py` (`ConfigDB` + `load_dotenv`); `backend/src/Memorix/providers/database.py` (`URL.create("postgresql+psycopg2", ...)`, `engine`, `SessionLocal`).
  - Schema `entities/documents.py` = migração `backend/api/migrations/versions/0001_documents_chunks.py`: `documents` (`doc_sha256` char(64) UNIQUE, `source_type` pdf|texto) e `chunks` (`chunk_id` text PK GENERATED `doc_id:position`, UNIQUE(doc_id, position), offsets com CHECK, sem vetor), RLS sem policies. O banco de dev está em `0001 (head)`, vazio.
  - Teste 002: `backend/api/tests/test_persistence.py` agora usa fixtures de sessão em `conftest.py` por decisão do humano; sha256 novo `38ddb0586eed33f86b0cdca4a2fddae09c4d6fe62a6e245c499cf7df401be828`, com 11/11 ainda passando. O sha anterior `022d4fc6…52ed7` foi substituído com autorização explícita. O banco foi devolvido a `0001 (head)`.
  - Risco aberto: a conexão como `postgres` ignora a RLS. A autorização por aluno fica no backend ou num role próprio (menores + LGPD).
  - **Risco LGPD adiado por decisão do humano ("ignore", gate final da 003):** o projeto Supabase está em us-east-1, então guardar o acervo, e no futuro dados de aluno, é transferência internacional (art. 33). Não vamos migrar agora. Isso não está resolvido; tem de ser confirmado com a assessoria jurídica antes de existirem tabelas de aluno.

## Contrato Laya (choice)

- `questions`: `dict[str, LayaChoiceQuestion]`; chave = id da pergunta (usar snake_case, sem espaço).
- Obrigatórios: `type`, `instructions`, `criteria` (dict `rótulo → descrição` ou lista de rótulos; **set é rejeitado**).
- Retorno de `router.predict`: `{"model", "answers": {qid: {"type", "choice", "probabilities", "confidence", "action"}}, "usage", "routing"}`. `choice` é uma chave de `criteria`.
- `confidence` = `1 - H(p)/log k` (entropia normalizada, `laya/common.py:261`), **não** é a probabilidade da escolha. Ex.: `aulas` com p=0,659 em 4 opções → confidence 0,34. Para decidir, usar `probabilities[choice]` com limiar.
- Checkpoint emite aviso de temperaturas inválidas (clamp para 0,5) → confidence não calibrada.

## Execuções registradas (2026-09-24)

| Execução | Resultado |
| --- | --- |
| Pergunta sem `instructions` | Falhou: `ValueError ... no 'instructions'` |
| `criteria` como set, `preload=True` | Falhou: `access violation` (exit 5) ao carregar safetensors no preload de 3 checkpoints — provável falta de memória, não isolado |
| `criteria` lista, `preload=False`, state "Queria criar umas aulas sobre Python" | Passou: `aulas` p=0,659 (exercicios 0,203, flashcards 0,125, outro 0,013), confidence 0,34, rota `multilingual` |

Descrições em `criteria` foram adicionadas depois (`CONTENT_TYPE`), ainda **sem medição** antes × depois.

## Pipeline (2026-09-24) — corte moderado de ceremônia

A pedido do humano (custo/tempo do pipeline). Alterado com aprovação do humano nesta sessão (`.omp/pipeline/pipeline.md`, `.omp/instructions/teste-primeiro.md`, `.omp/agents/orchestrator.md`, `.omp/agents/ai-rag-specialist.md`, `.omp/agents/pedagogy-specialist.md`):

- Rodada de handshake via `hub` ("Colaboração entre agentes") só roda com 2+ especialistas acionados na mesma tarefa; especialista único delega/trabalha direto, sem rodada.
- Mudança pequena (≤3 arquivos afetados, sem dependência nova): gate de plano (etapa 2) e gate de teste (etapa 3, `teste-primeiro.md`) se fundem num único "ok"; mudança maior mantém os dois separados.
- Sem mudança em: baseline/eval de IA, rastreabilidade, aceite final, revisão pedagógica quando o output chega ao aluno, ordem de autoridade.

## Pipeline (2026-10-01) — worktrees no Orca

A pedido do humano: seção "Worktrees" em `pipeline.md`, princípio 2 vira "uma tarefa por sessão" e a etapa 6 ganhou a regra para worktrees. Script `.omp/scripts/worktrees.ps1`: cria um worktree Orca por tarefa aberta (`orca worktree create --base-branch develop`), com junction de `.omp`/`venv` e cópia do `.env`. Testado com a tarefa descartável 999; venv via junction funcionou e a remoção não tocou os alvos. O código da 002 e da 004 agora está commitado em `develop`, então a 005 pode partir dessa base em uma worktree separada.

## Ingestão de texto 004 (2026-10-01)

- Goal 1.2 autorizado integralmente ("Autorizar o goal 1.2 inteiro (004 e 005/PDF)"). A 004 foi aceita após revisão de chunking ("Aceitar a 004; H-004 continua Falhou nas fixtures"). `canonical.py` aplica oito passos antes dos offsets e do SHA; `chunking.py` usa XLM-R do `BAAI/bge-m3` na revisão `5617a9f…`, `estrutural-v1` 400/80/0; `ingest.py` grava `documents`/`chunks` em transação com NO-OP por SHA idêntico; `rastro.py` emite JSONL sem conteúdo.
- Teste primeiro congelado: `test_ingestao.py` sha256 `310973ef9dc9b8bc1a4d602eca5cb37d43091d35cc6696b2156dea02e287ae0c`, `conftest.py` sha256 `851774e14e581c85ea5da90d3d6f825ec0b1d9f370e3da1974568574467fc3b7`. Suíte completa 68/68; seis fixtures ingeridas em transação externa com rollback, 12 linhas de rastro lidas, banco devolvido a `0001 (head)`.
- Perfil nas seis fixtures: 16 chunks, quatro <80 tokens (25%) e pelo menos um fallback (6,25%). H-004 **Falhou** nos alvos <20% e <5%, com aceite explícito do humano. A revisão deslocou a fronteira de uma sobra de 20 tokens para 190/227 sem cruzar título. Quatro seções inteiras seguem curtas por limite rígido de título; o bloco sem espaços exige fallback. Não inflar denominador para maquiar o resultado; medir no corpus real na 007.
- Commits atômicos da 004 em `develop`: `0976dd9` fixtures compartilhadas, `52b0eb7` canonicalização, `fa1fdb0` chunking/config, `4057c04` rastro, `b136196` ingestão transacional, `5383c8d` testes/fixtures. O tokenizer BERTimbau órfão saiu em `02d579d`; `backend/logs/` é ignorado desde `5e68204`.
- O humano removeu o limite de 2 minutos por agente ("tire o limite de tempo"). `orchestrator` e especialista ficaram indisponíveis por 429 no desenho da 005; plano e teste primeiro foram aprovados pelo humano e o `orchestrator` revisou os seis critérios antes do aceite final, sem bloqueio. A 005 foi executada **em outra worktree** e integrada em `develop`.

## Ingestão PDF 005 (2026-10-01)

- Goal 1.2 e tarefa 005 aceitos pelo humano ("Aceitar 005 e concluir goal 1.2"). `pdf.py` extrai texto selecionável com `pypdf` por página e aplica PDFium + Tesseract local `por` somente nas páginas sem camada textual; compartilha trace e ingestão atômica da 004. `requirements.txt` fixa `pypdf==6.19.0`, `pypdfium2==5.13.0`, `Pillow==12.3.0`; cada ambiente ainda precisa instalar Tesseract e dados `por` (ou configurar `TESSERACT_CMD`). Nenhum conteúdo privado sai a terceiros.
- Contrato congelado: `test_pdf.py` SHA-256 `3084a3bd4ef593899b0bdc96c2e9843e76f8b678acea6ccfbd09761f67d700be`, seis PDFs com bytes preservados por `.gitattributes`; migração `0001` mantém SHA `eba47c8667c6d58aae774f8b41963abdadb1d81752088e5e019f50e6e3576562`. Dez testes novos falharam antes por ausência do módulo e passaram depois; suíte completa 77/77. OCR e texto nativo pontuaram 1,0 nas seis páginas de referência (alvo ≥0,90); PDF inválido/protegido e página digitalizada em branco falham sem alterar chunks e deixam rastro de erro. H-005 **Passou nas fixtures**; H-004 segue **Falhou**, aceita, e medição no corpus real é da 007.
- Autorização Git: "Commits atômicos e integrar em develop". Cinco commits `3ac43dc`, `a3fb26d`, `b9ffe71`, `6f68345`, `e70f44a`; merge fast-forward local em `develop`, **sem push/deploy**. Após o merge, `test_pdf.py` → 10/10; SHA dos seis PDFs, teste e migração preservados; banco em `0001 (head)`.

## Próximo

- Trilha IA: baseline de ~20 casos reais para `CONTENT_TYPE` (descrições vs. só rótulos), medindo `probabilities[choice]` e acurácia.
- Decidir onde a chamada `router.predict(..., questions=CONTENT_TYPE)` passa a viver (hoje nenhum código chama).
- Goals 1.1–1.5 criados (`.omp/goals/01.1-…` a `01.5-…`), com a fila de tarefas registrada em cada um:
  - 1.1 ← 002 (concluída);
  - 1.2 ← 004 (texto), 005 (PDF);
  - 1.3 ← 003 (concluída, desenho), 006 (evals; depende do scraping do material), 007 (medição), 008 (`0002` + busca);
  - 1.4 e 1.5: tarefas a detalhar.
- Goal 7 — Observabilidade ponta a ponta criado pelo humano (2026-10-13, `.omp/goals/07-observabilidade-ponta-a-ponta.md`): tarefa 009 (logger básico da ingestão) autorizada e aceita com ressalva em 2026-10-14. `read_trace(trace_id)` consulta o JSONL, `summarize_traces()` agrega p95 nearest-rank, taxa de erro e, quando presentes, tokens/custo por geração. Falhas de chunking geram evento no mesmo `trace_id` da ingestão; PDF já propaga o mesmo ID da extração à ingestão. Goal 7 **Em andamento**, não concluído: consulta RAG/geração não existem; 006–008 e 010 continuam bloqueadas, e juiz via API depende de decisão humana. Teste novo SHA-256 `3b50c1d175a8aadcf590352892d26719f81cad820691344338df1b542deb098e`; 2/2 novos e 54 offline passaram, 14 com banco não executados (timeout Supabase já registrado na 012); PDF ausente produziu rastro `extracao`/erro com taxa 1,0. Sem commit/push/deploy.
- Histórico dos gates da 002 e da 003: literal nas próprias tarefas, na seção Decisões.
- 003 (pesquisa de retrieval) está **Concluída** (aceite em 2026-09-24). O que o humano decidiu:
  - vetor na 0002 como coluna em `chunks` (`vector(1024)` + `embedding_model`);
  - desafiantes via API **autorizados para medição na 007**, mas cada uso real que envie dados a terceiros ainda passa pelo humano;
  - contextual retrieval só com LLM local;
  - volume de até ~10 mil trechos como teto de planejamento (o acervo real ainda não existe);
  - p95 ≤ 1,0 s aceito;
  - rastro sem `index_version`.

  Recomendações que valem para as próximas tarefas:
  - `bge-m3` denso 1024 local;
  - busca exata híbrida com FTS `pt_unaccent` e RRF k=60;
  - `bge-reranker-v2-m3` com `k_cand` 30;
  - gate por logit + `n_sup`;
  - chunking `estrutural-v1` (400/80/0) para a 004.

  O protocolo da 007 e as hipóteses H1–H27 estão na tarefa; os anexos ficam em `.omp/tasks/003-anexos/`.
- Pendências com o humano:
  - commits das tarefas 002, 004 e 005 **autorizados pelo humano e executados por `Main`** em 2026-10-01; a 005 foi integrada por fast-forward local em `develop`. Nada foi enviado por push/deploy.
  - pontos pedagógicos da 003 ficam **em espera** ("4. espere"): lista de temas na recusa, canal para pedir material, cobertura parcial, aula em partes, checagem de distratores. Bloqueiam o 1.4 e o 1.5 até o humano retomar.

- Goals 1.1 e 1.2 **Concluídos**. Em resposta ao pedido de continuar, o humano escolheu **"Manter 1.3 bloqueado"**; não iniciar 006/007/008 sem nova autorização. O acervo real da 006 segue pendente do scraping.

## Documentação de estado (2026-10-13)

- `README.md`, `.omp/context/produto.md` e goal 6 alinhados ao código e aos goals concluídos: persistência/ingestão/testes existem; retrieval/geração não; Laya está configurada, mas sem chamada no fluxo. A indicação de mDeBERTa como escolha vigente foi corrigida pela decisão posterior do humano (abaixo). Nenhum status de goal ou autorização foi alterado.
- **Decisão do humano (2026-10-13):** "o código vai usar o Laya mesmo". Laya substitui mDeBERTa como classificador previsto do `pedagogical_understand`; configuração e contrato já existem, integração e medição de `CONTENT_TYPE` continuam pendentes. A escolha anterior fica somente no histórico.
- **Regra de encerramento aprovada pelo humano (2026-10-13):** agentes atualizam os arquivos correspondentes ao resultado de cada tarefa antes de comunicar conclusão; em worktree, documentação compartilhada é sincronizada no checkout principal após o merge. Pipeline etapa 6 e `.omp/AGENTS.md` atualizados.
- **Modelos dos agentes (2026-10-13, decisão do humano):** `orchestrator` e `ai-rag-specialist` usam `openai-codex/gpt-6-sol` (escolhido pelo humano pois GPT-6.1 Sol não está disponível nesse provider); `ai-rag-specialist` usa esforço médio e `hi` limitado a `high` para decisões difíceis. `pedagogy-specialist` usa `opencode-go/gpt-6-luna`. Há duas contas Codex locais: antes de delegar, a sessão principal deve usar `/session pin caique.ds.brito@gmail.com` com modelo Codex ativo. O pin é afinidade preferencial, não isolamento estrito contra fallback.

## Convenção de funções (2026-10-14) — tarefa 011

- Humano aprovou plano e renomeação dos testes 002/004/005. Todas as funções Python próprias de código e testes usam nomes em inglês `snake_case`; chamadas, imports e fixtures foram atualizados sem alterar os dados persistidos. Regra para mudanças futuras em `README.md` e `.omp/AGENTS.md`.
- A edição local pré-existente `chunkar → chunking` estava sem atualização de teste e causava erro de coleta; a referência no teste foi alinhada a `chunking`. Outras alterações locais pré-existentes preservadas.
- Verificação: compilação do backend **Passou**; 52 testes de ingestão/PDF sem banco **Passaram**; teste isolado de URL sem banco **Passou**. Suíte com banco **Bloqueada** por timeout de conexão Supabase. Os 77 testes da suíte completa são registro anterior a esta renomeação, não resultado atual. Hashes de testes novos e evidências detalhadas na tarefa 011. Humano concluiu a tarefa com resposta literal `Aceitar com ressalvas`, aceitando a falta de teste com banco nesta sessão.
- Sem `orchestrator`: `/session pin caique.ds.brito@gmail.com` exigido antes do acionamento não tem controle de execução nesta API; não há afinidade confirmada nem revisão por agente. Humano dispensou explicitamente essa revisão apenas para a tarefa 011.

## Convenção de variáveis (2026-10-14) — tarefa 012

- Plano e edição nominal de testes aprovados autorizados pelo humano. Parâmetros, locais, constantes e atributos internos Python em inglês; `Resultado.status`, `ConfigIngestao.strategy/extractor/trace_path`, kwargs, fixtures e `parametrize` migrados. Chaves de SQL, env e rastro, valores persistidos e migração 0001 permaneceram iguais. Convenção estendida em `README.md` e `.omp/AGENTS.md`. Alteração local do provider para `observabilitiy.py` preservada.
- Compilação **Passou**. 52 testes de ingestão/PDF sem banco e um de configuração **Passaram**. A suíte completa teve 53 passed e 24 erros de setup por timeout Supabase: contrato com banco **Bloqueado**, não validado após as renomeações. Smoke da API de ingestão para caminho inválido e rastro JSONL **Passou**; strings de contrato preservadas conforme comparação AST. Hashes novos na tarefa 012. Aceite final literal do humano: `Aceitar com ressalvas`, mantendo explícita a falta de validação com banco.
- Revisão do `orchestrator` dispensada nesta tarefa por decisão explícita do humano (`Dispensar nesta tarefa`); a dispensa não altera o pipeline geral.

## Goal 1.3 — acervo e desbloqueio (2026-10-14)

- Pedido do humano: implementar o goal 1.3; acervo real em `C:\Users\gamer\Documents\Docs Memorix` (17 PDFs, 4.297 páginas, 267.408.978 bytes). Sequência aprovada: ingestão no schema 0001 sem vetor → 006 (~20 casos) → 007 (baseline/medição local) → 008 (migração 0002 pgvector/FTS e busca). Banco escolhido: Supabase com pgvector. Revisão do `orchestrator`/especialista dispensada só para esta tarefa pelo humano devido à indisponibilidade de `/session pin` nesta API.
- Diagnóstico do banco: DNS do pooler em modo session resolveu três IPs, mas TCP 5432 expirou nos três e `alembic current` expirou após 35 s. Nenhum dos PDFs foi gravado no banco; o humano escolheu liberar o acesso à porta. Não assumir migração 0002 nem índice vetorial existente.
- Pré-extração completa dos 17 PDFs confirmou três com páginas realmente sem texto após OCR: Línguas (p. 8), Sociologia (p. 16 e outras) e Redação (p. 6 e outras). O humano aprovou omitir essas páginas, mantendo erro para documento inteiramente vazio e rastro da página omitida. Teste adicionado a `test_pdf.py` falhou antes pelo motivo esperado, foi aprovado pelo humano com SHA-256 `8f51d859a1418abe820162f5191aa761821c1939be9eb78005afa583f9aaea44`, e passou após a alteração em `pdf.py`; hash inalterado. **Seis testes PDF offline passaram** (cinco com banco não executados). Smoke dos três livros: 1, 12 e 6 páginas omitidas, respectivamente, com texto extraído dos 17 documentos. Chunking de um livro real produziu 381 trechos em 22,2 s, com teto de 400 tokens. A ingestão real e a medição seguem pendentes do acesso ao banco.
- Pedido posterior do humano: liberar o acesso nesta máquina. O firewall Windows (perfil Público) está `BlockInbound,AllowOutbound`, sem regra ativa de saída `Block`; há rota IPv4, sem rota IPv6 padrão e sem proxy WinHTTP. TCP 443 funciona no pooler e em `portquiz.net`, enquanto 5432 e 6543 expiram em ambos. Portanto, criar regra local de permissão não corrigiria o bloqueio de saída; nenhuma configuração de segurança foi afrouxada. O `.env` só traz credenciais de banco, não chave HTTP do Supabase. É necessário liberar portas SQL na rede/VPN upstream ou fornecer conectividade equivalente, sem expor credenciais no chat.

## Jev como julgador do OMP (2026-10-14)

- Credencial TypeSafe em `~/.omp/agent/.env` (fora do repositório); `modelRoles.judge: typesafe/jev-latest` em `~/.omp/agent/config.yml`. `modelRoles.default` continua `openai-codex/gpt-6-sol`: Jev auxilia decisões tipadas, sem substituir o LLM de conversa nem integrar a geração do Memorix. Nenhum plugin adicional instalado.
- Verificação **Passou**: `GET /v1/models` retornou `jev-latest` e `jev-preview` (HTTP 200); `omp models --kind judge --no-extensions` listou ambos; decisão sintética em `POST /v1/systemone` retornou HTTP 200 e `noul=0,99`. Nenhum dado do projeto foi enviado.

## Aprendizados e erros recorrentes

- Laya `choice`: `criteria` nunca como set; sempre `instructions`.
- Não usar `preload=True` com vários checkpoints nesta máquina (crash nativo sem traceback).
- Não ler `confidence` da Laya como probabilidade.
- `from pgvector import Vector` é a classe de valor; o tipo de coluna é `from pgvector.sqlalchemy import Vector`.
- `metadata` é reservado no Declarative do SQLAlchemy: usar outro nome de atributo.
- Pasta `backend/src/Memorix/multi-agent/` não é importável (hífen) → renomear para `multi_agent/` antes de ter código. `bgem3_provider.py` não existe mais (só `.pyc`), mas a tarefa 001 ainda o cita.
- `pipeline.md` já usava `.omp/progresso.md`/`.omp/tarefas/` (caminhos errados); corrigido em 2026-09-24 para `.omp/progress/progresso.md`/`.omp/tasks/` nas 3 ocorrências (etapas 0, 1, 6). `AGENTS.md` já tinha sido corrigido antes.

## Commits e integração (2026-11-01)

- Pedido do humano: criar commits atômicos e enviar à `develop`; inclusão de documentação e fixtures JSON necessárias autorizada nesta sessão. Resultados experimentais não exigidos pelos testes ficam locais.
- Verificação antes dos commits: `pytest backend/api/tests -q` com `.env.test` → **162 passaram, 1 aviso de depreciação**; compilação do backend passou; smoke HTTP via TestClient confirmou `/health` 200 e histórico anônimo 401.
- Integração diretamente na `develop`, sem reescrever histórico. Antes desta sessão, a branch local já tinha 23 commits além de `origin/develop`; o envio inclui esse histórico.
