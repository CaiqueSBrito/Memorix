# 002 — Persistência base no Supabase: documentos e trechos (sem vetor)
Goal: 1.1 — Acervo persistido (subgoal do goal 1)        Trilha: IA        Estado: Concluída (aceite final do humano em 2026-09-24; teste alterado duas vezes depois do aceite, com autorização — sha256 atual `38ddb058…be828`)

## Objetivo

Levar o schema `Document`/`Chunk` (em `backend/src/Memorix/entities/`) até o banco de dev do Supabase. Nesta fatia entram as tabelas, as chaves estáveis e os campos de rastro, sem vetor. O que falta hoje:

1. Ajustar o schema:
   - adicionar `doc_sha256`;
   - trocar `chunk_id` para texto no formato `"{doc_id}:{position}"`;
   - adicionar offsets;
   - adicionar `CHECK` de `source_type`;
   - habilitar RLS;
   - tirar `embedding`/`embedding_model` de `Chunk`.
2. Criar engine e sessão a partir do `.env`.
3. Criar a migração Alembic `0001` com `upgrade` e `downgrade`, provada no banco de dev.

Vetor, `embedding_model`, índice HNSW, extensão `vector` e uma eventual coluna lexical entram na migração `0002`, na tarefa proposta 008. Essa tarefa vem depois da pesquisa 003 e da medição 007, porque a dimensão do vetor depende do modelo.

O humano autorizou a execução com o `ai-rag-specialist` construindo (gate 2, resposta 8).

## Critérios de aceitação

- [x] `alembic upgrade head` roda sem erro no banco de dev do `.env` e cria `documents` e `chunks`.
- [x] `alembic downgrade base` remove as duas tabelas sem erro. Em seguida, `upgrade head` roda de novo sem erro.
- [x] `documents.doc_sha256` é `char(64) NOT NULL UNIQUE`. Inserir o mesmo hash duas vezes falha com `IntegrityError`.
- [x] `documents.source_type` aceita só `pdf` e `texto` (`CHECK`). Qualquer outro valor falha.
- [x] `chunks.chunk_id` é a PK textual e sempre igual a `doc_id || ':' || position`, garantido pelo banco. Implementado como coluna `GENERATED ALWAYS ... STORED`, que o Postgres 17.6 aceita como PK.
- [x] `chunks` tem `UNIQUE(doc_id, position)`. Inserir a mesma posição duas vezes no mesmo doc falha.
- [x] `chunks.offset_start`/`offset_end` são `NOT NULL` com `CHECK (offset_end > offset_start)`. Um offset invertido falha.
- [x] `chunks` não tem as colunas `embedding` nem `embedding_model` nesta fatia.
- [x] Apagar um `Document` apaga os chunks dele (`ON DELETE CASCADE`).
- [x] RLS habilitada em `documents` e `chunks` (`pg_class.relrowsecurity = true`), sem policies.
- [x] A URL do banco vem só do `.env`, agora como variáveis separadas `DB_*` (ver Decisões). Nenhuma credencial em código, migração, teste ou log.

## Fora do escopo

- Coluna de embedding, `embedding_model`, índice vetorial e extensão `vector`: vão para a 008.
- Ingestão, chunking e reingestão: vão para a 004. Lá entram o apagar-e-reinserir dos chunks numa única transação e o rastro com `doc_sha256` junto de cada `chunk_id`.
- Texto integral do documento, página do PDF e contagem de tokens.
- Role própria do backend e policies de RLS: entram com as tabelas de aluno e a decisão de LGPD.
- Rastro JSONL: Não se aplica, porque nenhuma etapa do pipeline RAG é implementada aqui.
- Trocar ORM, driver ou provedor.

## Esclarecer

Nenhum aberto. Os Esclarecer de IPv6 e do driver foram resolvidos no gate 3. A origem da URL no teste foi resolvida na correção pós-aceite (ver Decisões): o teste agora importa `DATABASE_URL` e tem sha256 `022d4fc6…52ed7`.

## Plano

| Passo | Quem | Arquivos | Status |
| --- | --- | --- | --- |
| 1. Gate humano: plano | humano | — | Concluído ("sim", gate 2) |
| 2. Teste de conexão só-leitura | `ai-rag-specialist` | nenhum | Concluído: PostgreSQL 17.6 via Supavisor em modo session; banco limpo antes do upgrade; `vector` disponível (0.8.2), não instalada |
| 3. `requirements.txt` de UTF-16 para UTF-8, sem mudar versões | `orchestrator` | `requirements.txt` | Concluído (58 linhas, sem BOM) |
| 4. Teste primeiro + gate humano | `ai-rag-specialist`, humano | `backend/api/tests/test_persistence.py` | Concluído (gate aprovado: "continue a task") |
| 5. Schema | `ai-rag-specialist` | `backend/src/Memorix/entities/documents.py` | Concluído |
| 6. Engine e sessão: `URL.create("postgresql+psycopg2", DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, sslmode=require)`, `create_engine(pool_pre_ping=True)` com o QueuePool padrão, `SessionLocal`. `load_dotenv` no `ConfigDB` | `ai-rag-specialist` | `backend/src/Memorix/providers/database.py`, `backend/api/config/config.py` (só `load_dotenv`) | Concluído |
| 7. Alembic | `ai-rag-specialist` | `backend/api/alembic.ini`, `backend/api/migrations/{env.py, script.py.mako, versions/0001_documents_chunks.py}` | Concluído |
| 8. Provar | `ai-rag-specialist`; conferido pelo `orchestrator` | esta tarefa | Concluído (ver Evidências) |
| 9. Revisar: orquestrador confere critério × evidência (feito). Revisão pedagógica: Não se aplica. **Aceite final do humano** | `orchestrator`, humano | esta tarefa | Aguardando o humano |
| 10. Registrar: tarefa e `progresso.md` | `orchestrator` | — | Feito na tarefa; `progresso.md` depois do aceite |

## Baseline (IA)

Não se aplica nesta fatia, porque não há retrieval. Vetor, índice e caso-semente de top-k passaram para a 008, que terá baseline próprio.

## Teste primeiro (feature)

Arquivo: `backend/api/tests/test_persistence.py`, com 11 testes e `sha256` `973ba3f500ce141e21012c5bed1c00ae50f6692f0f75219d3e26f97d7eb6c745`. Rodar da raiz com `./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py -q`.

Como o teste funciona:
- Usa SQL cru (`text()`) contra o banco. O Alembic entra via API numa fixture de sessão: `upgrade head` no setup e `downgrade base` no teardown.
- Cada teste roda numa transação desfeita no fim; os casos de erro usam savepoint.
- A fixture falha sem apagar nada se já existirem `documents`/`chunks` sem `alembic_version`.
- O engine do teste força `postgresql+psycopg2`.

| Critério | Teste | Falhou antes (motivo) | sha256 |
| --- | --- | --- | --- |
| upgrade cria `documents` e `chunks` | `test_upgrade_head_cria_documents_e_chunks` | ERROR no setup: `backend/api/alembic.ini não existe: migração 0001 ainda não implementada` | arquivo acima |
| downgrade remove e upgrade roda de novo | `test_downgrade_base_remove_tabelas_e_upgrade_roda_de_novo` | idem | idem |
| `doc_sha256` char(64) NOT NULL UNIQUE | `test_doc_sha256_char64_not_null_unique` | idem | idem |
| `source_type` só `pdf`/`texto` | `test_source_type_aceita_so_pdf_e_texto` | idem | idem |
| `chunk_id` = `doc_id:position` (GENERATED ou CHECK) | `test_chunk_id_textual_pk_igual_doc_id_dois_pontos_position` | idem | idem |
| `UNIQUE(doc_id, position)` | `test_chunks_unique_doc_id_position` | idem | idem |
| offsets NOT NULL e `end > start` | `test_offsets_not_null_e_end_maior_que_start` | idem | idem |
| sem `embedding`/`embedding_model` | `test_chunks_sem_embedding_nem_embedding_model` | idem | idem |
| ON DELETE CASCADE | `test_apagar_document_apaga_chunks_on_delete_cascade` | idem | idem |
| RLS habilitada, sem policies | `test_rls_habilitada_sem_policies` | idem | idem |
| URL só do `.env`, sem credencial em código | `test_url_do_banco_so_no_env_sem_credencial_em_codigo` | FAILED: arquivos da implementação ausentes (`backend/api/alembic.ini`, `backend/src/Memorix/providers/database.py`) | idem |

Saída: `1 failed, 10 errors in 0.44s`. Todos falham porque a feature não existe; nenhum falha por sintaxe, import, driver ou rede. Os 10 aparecem como ERROR, e não FAILED, porque param no setup da fixture, antes de qualquer conexão.

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| Pacotes no venv: SQLAlchemy 2.1.0, alembic 1.20.0, pgvector 0.5.0, psycopg2 2.9.13, pytest 9.1.1, python-dotenv 1.2.3 | `pip list` (2026-09-24) | Passou |
| `requirements.txt` convertido de UTF-16 LE com BOM para UTF-8 sem BOM, 58 linhas, versões inalteradas | reescrita via `python` e leitura dos primeiros bytes (`accelerate==`) | Passou |
| `.env` no momento da prova | leitura só de nomes/formato: `DB_HOST` = Supavisor `aws-0-us-east-1.pooler.supabase.com`, `DB_PORT` 5432, `DB_USER` = `postgres.<ref>`, `DB_PASSWORD`, `DB_DATABASE`; `DB_CONNECTTION_STRING` removida pelo humano | Passou |
| Implementação offline: `configure_mappers`; DDL do modelo igual ao de `alembic upgrade head --sql` | `ai-rag-specialist` | Passou |
| Prova do construtor: pre-check (PG 17.6, tabelas ausentes) → `upgrade head` → pytest `11 passed in 21.01s` → `upgrade head` → `downgrade base` → `upgrade head` → `current = 0001 (head)`, 0 linhas nas duas tabelas | `ai-rag-specialist` (Supavisor session) | Passou |
| Verificação independente: `sha256` do teste = `973ba3f5…c745` (igual ao aprovado); `alembic current` = `0001 (head)`; pytest `11 passed in 19.47s`; `upgrade head` depois do teardown; `current` = `0001 (head)` | `orchestrator`, script com `DB_CONNECTTION_STRING` injetada só no processo filho e saída mascarada | Passou |
| Estado final do banco de dev | `alembic current` | `0001 (head)`, tabelas vazias, RLS ligada |
| Revisão de código pelo orquestrador: `entities/documents.py`, migração `0001` e `providers/database.py` batem com os critérios; sem credencial em código | leitura | Passou |

## Revisão pedagógica

Veredito: Não se aplica. É infraestrutura de armazenamento e nada chega ao aluno. | Achados: —

## Decisões e conflitos

**Aprovadas pelo humano antes (2026-09-24, fora do pipeline):**
- SQLAlchemy 2.x + Alembic + `pgvector.sqlalchemy`.
- Conexão direta na porta 5432; `supabase-py` descartado.
- `Base` em `entities/__init__.py`; `Document`/`Chunk` em `entities/documents.py`; `metadata` no atributo `extra`.
- Embedding só no chunk.
- FK com `ON DELETE CASCADE`.

**Gate 1 do plano (2026-09-24).** Respostas literais do humano, repassadas por `Main`. A numeração é a dos Esclarecer bloqueantes 1–5 apresentados a ele: 1 autorização/autoria, 2 modelo, 3 banco, 4 chave do chunk, 5 layout.

> "01. o goal 1 é amplo demais para fazermos de forma one-shot e precisamos mitigar em menores antes
> 02. precisamos de uma pesquisa ampla considerando como vai ser feito o retrieval, precisamos pensar primeiro como faremos o retrieval antes de decidir o modelo
> 03. sim, pode
> 04. ai-rag-specialist é prioridade em assunto IA
> 05. sim"

Consequências:
- **01:** esclarecido no gate 2. A leitura correta é "dividir em goals menores antes do goal 1".
- **02:** vetor, índice e extensão saíram desta tarefa. A pesquisa de retrieval virou a tarefa 003, que vem antes da escolha do modelo.
- **03:** o banco do `.env` é de dev. `upgrade`/`downgrade` e os testes estão autorizados nele.
- **04:** a divergência da chave do chunk foi resolvida a favor do `ai-rag-specialist`: `chunk_id` textual `"{doc_id}:{position}"` como PK, com os chunks substituídos na reingestão (mesmo `doc_id`). A posição do orquestrador que perdeu era documento imutável + `chunk_id` SERIAL + `UNIQUE(doc_id, position)`. Motivo: decisão do humano.
- **05:** layout `backend/api/` aprovado para config, migrações e testes: `ConfigDB` em `backend/api/config/config.py`, `backend/api/migrations/`, `backend/api/tests/`.

**Gate 2 (2026-09-24).** Respostas literais do humano, repassadas por `Main`. A numeração segue as 16 perguntas do relatório anterior:

1. [01] leitura de "mitigar";
2. [04] regra geral e texto proposto;
3. decomposição;
4. [003-1] tempo;
5. [003-2] hardware;
6. [003-3] volume;
7. [003-plano];
8. [002-1] autorização e autoria;
9. [002-2] plano;
10. [002-3] tirar vetor;
11. [002-4] `index_version`;
12. [002-5] RLS;
13. [002-6] `uploaded_by`/`source_type`;
14. [002-7] `DATABASE_URL`;
15. [002-8] `backend/api/database.py` vs `src/Memorix/providers/database.py`;
16. [006] material real.

> "1. dividir em goals menores antes do goal 1
> 2. sim
> 3. sim
> 4. b) para essa task, tempo indeterminado
> 5. embedding e reranker vai depender do model, podemos tanto usar API Key como a 4050
> 7. sim
> 8. sim, o ai_specialist
> 9. sim
> 10. sim
> 11. nao
> 12. sim
> 13. sim, sim
> 14. nao
> 15. nao
> 16. iremos fazer um scrap pra isso posteriormente"

A resposta 6 não veio. A 003 usa o default declarado (~10 mil trechos), marcado como suposição.

Consequências nesta tarefa:
- **8 e 9:** execução autorizada, com o `ai-rag-specialist` construindo. O teste primeiro para no gate humano do teste.
- **10:** `embedding` e `embedding_model` saem de `Chunk` e voltam na 008.
- **11:** `index_version` **não** entra. Mantém-se o nome `embedding_model`, que vai para a 008.
  - Conflito registrado com `rag-rastreabilidade.md`, que pede `index_version`. Pela ordem de autoridade, vale a decisão do humano.
  - Proposta para a 004/008: o rastro deriva `index_version` de `embedding_model` + parâmetros de chunking, sem coluna própria. A confirmar com o humano quando a 008 for planejada.
- **12:** RLS sem policies na `0001`.
- **13:** `uploaded_by` como id opaco do admin; `source_type` com `CHECK ('pdf','texto')`.
- **14:** o nome `DB_CONNECTTION_STRING` fica.
- **15:** engine e sessão ficam em `src/Memorix/providers/database.py`. O `ConfigDB` continua em `backend/api/config/config.py` (resposta 05 do gate 1).
- **2:** a regra de autoridade foi aplicada em `.omp/AGENTS.md` e nas 3 definições de agentes. O caminho do pipeline também foi corrigido para `.omp/pipeline/pipeline.md`.
- **1:** o humano pediu goals menores antes do goal 1. A proposta está em `.omp/goals/README.md`, seção Sugestões, marcada como não aprovada. Esta tarefa vai para o goal proposto 1.1.
  - Não há conflito com a resposta 8: a execução da 002 foi autorizada explicitamente.
  - Criar o goal é decisão do humano.

**2ª rodada do `ai-rag-specialist` (`Orch002.RagSchema002`):**
- Seguir já com a `0001` sem vetor, porque nada nela depende do retrieval. Tsvector, sparsevec, vetor denso e `parent_id` entram como colunas novas na `0002`.
- Consequências da chave textual:
  - Depois de uma reingestão, "7:3" aponta para outro texto. Todo log ou citação grava `doc_sha256` junto do `chunk_id` (004/008).
  - A reingestão acontece numa única transação (004).
  - Ordenar sempre por `position`, porque na ordem textual "7:10" vem antes de "7:2".
  - Nada de FK rígida para `chunk_id` em logs e citações.
- Divergência de sequência:
  - O especialista juntava pesquisa e medição depois dos evals.
  - O orquestrador separou a pesquisa de mesa (003, primeiro) da medição (007, depois dos evals), para atender o "pensar primeiro" do humano.
  - É sequenciamento, que continua com o orquestrador mesmo com a nova regra de autoridade.

**1ª rodada (etapa 2 original):**
- HNSW `vector_cosine_ops` m=16/ef_construction=64. **Superado pela 003 (P6):** a 0002 usa busca exata, sem índice (ver 003).
- Mínimo de rastro: `doc_sha256`, offsets e `index_version`. `index_version` foi recusado depois pelo humano (gate 2, resposta 11).
- RLS sem policies agora.
- Riscos: IPv6 do host direto, extensão no schema `extensions` (008) e `import pgvector.sqlalchemy` no `script.py.mako` (008).

**Achados do orquestrador:**
- `progresso.md` estava desatualizado e foi corrigido.
- `ConfigDB` não chamava `load_dotenv`. Resolvido no passo 6: o `load_dotenv` agora está no `config.py`.

**Gate 3 (2026-09-24), repassado por `Main`:**
- Gate do teste: "continue a task", aprovado. O teste de `sha256` `973ba3f5…c745` segue inalterado.
- Conexão: o humano escolheu o Supavisor em modo **session**, porta 5432, e não o transaction pooler. Motivo dele: o backend é um processo persistente, e o transaction pooler não suporta prepared statements nem LISTEN/NOTIFY/advisory locks. Host `aws-0-<região>.pooler.supabase.com`, user `postgres.<ref>`, IPv4. Isso resolve o Esclarecer de IPv6. Pool: QueuePool padrão (NullPool só faria sentido no transaction pooler).
- Driver: `postgresql+psycopg2` forçado na URL, seguindo o snippet oficial do painel Supabase que o humano colou. Resolve o Esclarecer do driver.
- Formato do `.env`: o humano respondeu "RESOLVIDO" e trocou o `.env` sozinho. Tirou `DB_CONNECTTION_STRING` e ficou com variáveis separadas `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_DATABASE`. O `ConfigDB` dele lê `DB_NAME = os.getenv("DB_DATABASE")`. Com isso fica superada a resposta 14 do gate 2 ("manter `DB_CONNECTTION_STRING`"); vale o que o humano de fato configurou.
- Consequência: o teste aprovado ainda lê `DB_CONNECTTION_STRING` (Esclarecer 1 desta seção).
- Observação do construtor: `sslmode=require` criptografa mas não valida o certificado. `verify-full` com a CA do Supabase seria mais forte. Não foi mudado porque o snippet do humano usa `require`; fica registrado.
- A região do pooler foi confirmada pelo `.env` do humano (`aws-0-us-east-1`). Antes disso, o orquestrador tentou descobri-la testando os poolers com senha **falsa** (a senha real nunca foi enviada). A tentativa não serviu, porque o ref do projeto foi lido errado de um `.env` que estava mudando, e foi descartada.

**Gate final (2026-09-24), mapeado por conteúdo por `Main`:**
- "1. sim": aceite final da 002. Estado: Concluída.
- Troca da origem da URL no teste (Esclarecer 1 desta tarefa): **sem resposta explícita, tratada como não aprovada.** O teste continua como foi aprovado (`973ba3f5…c745`), e rodá-lo exige injetar `DB_CONNECTTION_STRING` no processo. Pendência aberta.
- Commit: não houve. É item de "Sempre com o humano" e a pergunta foi devolvida a ele.

**Correção pontual pós-aceite (2026-09-24).** O humano respondeu "2. sim" à troca da origem da URL no teste. Reabri a tarefa só para isso e fechei de novo.
- Mudou em `backend/api/tests/test_persistence.py`:
  - a URL agora vem de `backend.src.Memorix.providers.database.DATABASE_URL`, por import tardio em `_db_url()`, em vez de `os.getenv("DB_CONNECTTION_STRING")`;
  - saíram `load_dotenv`, `make_url`, `urlsplit` e a troca de driver no teste (o driver já vem na URL da implementação);
  - `_secrets()` usa a URL renderizada, a senha, o host e `DB_PASSWORD`;
  - a docstring foi atualizada.
- Asserções: todas as de comportamento continuam iguais. As duas de presença de URL (`assert DB_URL, "DB_CONNECTTION_STRING ausente no .env"`, na fixture `engine` e em `test_url_do_banco_so_no_env_sem_credencial_em_codigo`) trocaram só a origem: agora são `assert _db_url(), "URL do banco ausente no .env"`, e verificam a mesma coisa.
- Prova: `./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py -q`, **sem** injetar variável nenhuma, deu `11 passed in 18.72s`. Depois, `alembic upgrade head` e `current` = `0001 (head)`. Status: Passou.
- **Novo sha256 do teste: `022d4fc638c1131d0e1ee4ac4c15d854f5dfa82d542a3e2c1e1ba85575352ed7`**, que substitui o `973ba3f5…c745`.
- Estado: Concluída.

**Código commitado em `develop` (2026-10-01).** O commit era a última pendência da 002 e foi autorizado pelo humano ("7 commits atômicos, em develop"), executado por `Main`: `5e68204` gitignore (`backend/logs/`), `6f2f9aa` deps, `bfb9599` entities, `f67ad14` config, `b41cdad` providers, `a115037` migrations, `82fe97f` test. No mesmo lote saiu `02d579d`, removendo o `providers/tokenizer.py` órfão (BERTimbau, sem importador) — fora do escopo da 002, autorizado à parte. Com isso o goal 1.1 fica fechado de ponta a ponta.

**2ª alteração pós-aceite no teste (2026-10-01), autorizada pelo humano.** Resposta literal, no gate de fixtures da tarefa 004: **"Mover para o conftest.py, escopo session"**.
- O que mudou: as fixtures de banco e os helpers de segredo (`ROOT`, `ALEMBIC_INI`, `_db_url`, `_secrets`, `_no_secrets_in_errors`, `_alembic`, `engine`, `migrated`, `conn`) saíram deste arquivo e foram para `backend/api/tests/conftest.py`, com escopo `session`. `test_persistence.py` passou a importá-los (`from conftest import ...`) e perdeu os imports que só serviam ao código movido.
- O que **não** mudou: nenhuma asserção, nenhum nome de teste, nenhum comportamento. São os mesmos 11 testes.
- Motivo material: duas cópias da fixture fazendo `downgrade base` no teardown contra o **mesmo** banco de dev podiam derrubar o schema no meio do outro arquivo durante a suíte completa. A alternativa (duplicar as fixtures na 004) foi recusada pelo humano por isso.
- **Novo sha256: `38ddb0586eed33f86b0cdca4a2fddae09c4d6fe62a6e245c499cf7df401be828`**, que substitui o `022d4fc6…52ed7`.
- Prova: `./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py -q` → `11 passed`. Na pasta inteira, `pytest backend/api/tests/ -q` → `55 failed, 13 passed`, em que os 13 são os 11 desta tarefa mais os 2 testes estáticos da 004, e as 55 falhas são todas da 004 por código ainda não implementado. Status: Passou.
