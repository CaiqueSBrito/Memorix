# 004 — Ingestão de texto: canônico, chunking `estrutural-v1`, reingestão atômica e rastro
Goal: 1.2 — Ingestão do acervo        Trilha: IA        Estado: Concluída

> Execução do goal 1.2 autorizada pelo humano em 2026-10-01 ("Autorizar o goal 1.2 inteiro (004 e 005/PDF)"). Plano ("Aprovar como está"), teste ("Aprovar — congela os testes e libera a implementação (passos 4 a 7)") e aceite final da 004 ("Aceitar a 004; H-004 continua Falhou nas fixtures") registrados abaixo. H-004 permanece Falhou, sem mascarar a evidência.

## Objetivo

Fazer um texto em português virar trechos recuperáveis no acervo: normalizar para um texto canônico determinístico, calcular `doc_sha256`, quebrar em chunks pela estratégia `estrutural-v1` (400/80/0, tokenizer XLM-R do `BAAI/bge-m3`), gravar em `documents`/`chunks` (migração `0001`, já pronta na 002) numa única transação, e emitir o rastro JSONL das etapas Ingestão e Chunking.

O núcleo é duas funções puras (canonicalizar, chunkar) mais uma de persistência. A entrada é `str`; ler um `.txt` é `Path.read_text` na borda. A 005 (PDF) acrescenta outra borda que entrega `str` ao mesmo núcleo — por isso nada de abstração de "loader" aqui.

Nenhuma dependência nova: `transformers==5.17.0`, `tokenizers==0.23.2`, `sentencepiece==0.2.2` e `huggingface_hub` já estão no `requirements.txt`; o resto é stdlib (`hashlib`, `unicodedata`, `re`, `json`, `logging`, `uuid`).

### Texto canônico (ordem fixa, obrigatória)

1. `bytes` → `decode("utf-8", errors="strict")` (erro → ingestão falha e vira registro `status="erro"`; nunca `errors="replace"`).
2. Remover todo U+FEFF (BOM e ZWNBSP de concatenação).
3. Remover `\x00` e demais controles C0, exceto `\n`, `\t` **e `\r`** (o Postgres rejeita NUL em `text`).
4. `\r\n` → `\n`; `\r` isolado → `\n`.
5. `unicodedata.normalize("NFC", s)`.
6. Remover espaços/tabs no fim de cada linha.
7. `\n{3,}` → `\n\n`.
8. `strip()` do documento inteiro.

> **Decisão do humano (2026-10-01):** CR solto "Vira quebra de linha". O passo 3 preserva `\r` para o passo 4 o converter em `\n`; o teste congelado de `sujeira.bin` verifica esse comportamento.

`doc_sha256 = sha256(canonico.encode("utf-8")).hexdigest()` — sobre os bytes do **canônico**, nunca do arquivo cru. Assim `hash igual ⇒ espaço de offsets igual`, que é o que a regra de acerto da 007 (003 §5) exige.

**Regra dura:** offset nenhum existe antes do passo 8 terminar. NFC muda a contagem de code points (`e`+U+0301 = 2 → `é` = 1) e os passos 6–8 deslocam tudo; qualquer offset calculado antes fica inválido. É proibido aplicar `strip`/colapso depois, no chunk ou no `text` gravado. Offsets são `[s, e)` em **code points** (divergem de UTF-16 — contrato explícito para quem consumir).

### `estrutural-v1`

- **Título** (limite rígido): linha que casa `^#{1,6}\s+\S` ou `^\d+(\.\d+)*\.?\s+\S`, com `len(linha) <= 80` e sem pontuação final (`.`, `:`, `;`, `,`). Nenhum chunk atravessa o início de uma linha de título; o título abre a seção dele.
- **Descida recursiva**, só enquanto o pedaço passar de 400: (1) linha em branco; (2) `\n` (preserva item de lista e linha de tabela); (3) fim de sentença `[.!?…]\s+` com exceções PT (`Sr.`, `Sra.`, `Dr.`, `art.`, `p.`, `pág.`, `ex.`, `fig.`, `nº`, `cf.`, inicial maiúscula isolada); (4) `[;:]\s+`; (5) espaço.
- **Bloco > 400 sem onde quebrar:** fallback terminal obrigatório — cortar na fronteira de token mais próxima de 400 via `offset_mapping` do tokenizer fast do bge-m3, repetindo até caber. Único uso de `offset_mapping`. Consequência: **`max_tokens` = 400 é invariante dura**, não melhor esforço.
- **`min_tokens` = 80 é piso de melhor esforço.** Empacotamento guloso dentro da seção; depois, **uma** passada: chunk com `n_tokens < 80` funde com o **anterior** da mesma seção se o span fundido ≤ 400; senão com o **seguinte** da mesma seção se ≤ 400. Se nenhum couber, tenta redistribuir com o anterior numa fronteira de sentença, mantendo os dois spans entre 80 e 400 tokens. Se não houver fronteira válida, permanece curto. Nunca funde entre seções. Chunk que é só a linha de título funde com o seguinte se couber. **Seção inteira abaixo de 80 tokens vira um chunk e é mantida.**
- **Único descarte:** span sem nenhum caractere alfanumérico (resto de numeração de página).
- `s` avança e `e` recua sobre `str.isspace()`; `text = canonico[s:e]`; `position` começa em **0**; `chunk_id` é GENERATED pelo banco — a aplicação nunca escreve essa coluna.

### Reingestão atômica

Canonicalizar/chunkar fora da transação (puro, sem I/O de banco). Depois: `BEGIN` → `SELECT ... FOR UPDATE` → se o `doc_sha256` é idêntico ao persistido do mesmo `doc_id`, **NO-OP** (`resultado="sem_mudanca"`, commit vazio: o chunking é determinístico e apagar-e-reinserir destruiria os `embedding` que a 008 vai gravar nas mesmas linhas) → se mudou, `UPDATE documents` + `DELETE FROM chunks WHERE doc_id` + `INSERT` dos novos → `COMMIT` único. Um `session.begin()`, zero commit intermediário, zero autocommit. Exceção → `ROLLBACK` e os chunks antigos ficam intactos. Se o novo sha já pertence a outro `doc_id`, `uq_documents_doc_sha256` levanta `IntegrityError` — comportamento correto da `0001`, e é caso de teste.

**Origem do documento (decisão do humano, gate 3 de 2026-10-01).** O `INSERT`/`UPDATE` de `documents` grava o **caminho relativo do arquivo fonte** em `documents.metadata` (atributo `extra`, JSONB que já existe na `0001`). O texto canônico integral **não** é persistido: o canônico não é reconstruível pelo banco, e o `doc_sha256` é reverificado re-extraindo o arquivo de origem — que é o que o harness da 007 já faz (003 §5). Zero mudança de schema, zero migração nova.

### Rastro

`backend/logs/rag-rastro.jsonl`, append-only, sobrescrevível por `MEMORIX_RASTRO_PATH` (`logging` da stdlib com formatter JSON). Comuns: `trace_id` (uuid4, um por ingestão, nas duas etapas), `etapa`, `timestamp`, `duracao_ms`, `status`, `erro`. Ingestão: `doc_id`, `doc_sha256`, `origem` (tipo + nome do arquivo, nunca conteúdo), `tamanho`, `extrator="texto-bruto@v1"`, `resultado` (`criado`|`reingerido`|`sem_mudanca`). Chunking: `doc_id`, `doc_sha256`, `estrategia="estrutural-v1"`, `parametros` (tokenizer + `revision`, 400/80/0), `chunks: [{chunk_id, offset_start, offset_end, n_tokens}]` — o `doc_sha256` fica no mesmo registro que a lista de `chunk_id`. Sem `index_version` (decisão do humano). Sem segredo e sem texto do documento.

## Critérios de aceitação

Cada item é provável por execução. "Memória" = teste de função pura sobre as fixtures; "banco" = banco de dev, mesmo padrão de `backend/api/tests/test_persistence.py`.

- [x] **I1 — determinismo do chunking.** `chunk(t) == chunk(t)` (listas de `(position, offset_start, offset_end, text)` idênticas) nas 6 fixtures. *Memória.*
- [x] **I2 — canônico idempotente.** `canonicalizar(canonicalizar(t)) == canonicalizar(t)`, e `sujeira.bin` (BOM, CRLF, CR solto, `\x00`, NFD) produz o mesmo canônico e o mesmo `doc_sha256` da versão limpa equivalente. *Memória.*
- [x] **I3 — offsets válidos.** Todo chunk satisfaz `0 <= offset_start < offset_end <= len(canonico)`. *Memória + `ck_chunks_offsets` no banco.*
- [x] **I4 — recorte exato.** `canonico[offset_start:offset_end] == text` para todo chunk, em memória **e** relendo do banco. *Memória + banco.*
- [x] **I5 — disjunção (overlap 0).** Ordenados por `position`, `chunks[i].offset_end <= chunks[i+1].offset_start`: cada code point pertence a no máximo um chunk. *Memória.*
- [x] **I6 — cobertura alfanumérica.** `[c for c in canonico if c.isalnum()] == [c for ch in chunks for c in ch.text if c.isalnum()]`. Os únicos buracos permitidos são espaços entre chunks e spans sem nenhum alfanumérico; nenhum caractere alfanumérico some ou troca de ordem. *Memória.*
- [x] **I7 — teto duro de 400.** `len(tok(text, add_special_tokens=False).input_ids) <= 400` em todo chunk, inclusive na fixture do bloco gigante sem separador. *Memória, tokenizer real do bge-m3.*
- [x] **I8 — piso de melhor esforço.** Todo chunk com `n_tokens < 80` é (a) o único da sua seção, OU (b) fundi-lo com o anterior e com o seguinte da mesma seção passaria de 400. Não existe terceiro caso. *Memória, `resto-curto.txt`.*
- [x] **I9 — título é limite rígido.** Nenhuma posição de início de linha de título cai estritamente dentro de `(offset_start, offset_end)` de algum chunk. *Memória, `basico.txt` e `numerado.txt`.*
- [x] **I10 — `position` contígua e `chunk_id` coerente.** `SELECT position ORDER BY position` devolve exatamente `0..n-1`, e `chunk_id == f"{doc_id}:{position}"` em toda linha. *Banco.*
- [x] **I11 — reingestão com sha idêntico é NO-OP.** Reingerir texto idêntico não altera `chunks.created_at` de nenhuma linha nem a contagem; o rastro grava `resultado="sem_mudanca"`. *Banco.*
- [x] **I12 — reingestão produz os mesmos spans.** Ingerir A, reingerir B (≠A), reingerir A: o resultado final é idêntico ao da primeira ingestão de A em `(position, offset_start, offset_end, text)`. *Banco.*
- [x] **I13 — falha no meio preserva os chunks antigos.** Reingestão que levanta exceção depois do `DELETE` e no meio dos `INSERT` deixa os N chunks antigos intactos (mesmos `chunk_id`, offsets e `text`). Falha injetada por violação de constraint real, sem monkeypatch de ORM. *Banco.*
- [x] **I14 — rastro completo.** Uma ingestão bem-sucedida acrescenta exatamente 2 linhas ao JSONL, com o mesmo `trace_id`, `etapa` em `{ingestao, chunking}`; todo `chunk_id` persistido aparece na lista do registro de chunking, cujo `doc_sha256` é igual ao de `documents`. *Banco + arquivo em `tmp_path`.*
- [x] **I15 — rastro de erro.** Ingestão que falha grava registro com `status="erro"`, `erro` não vazio e o mesmo `trace_id`. Erro silencioso é proibido. *Banco + arquivo.*
- [x] **I16 — rastro sem vazamento.** Nenhuma linha do JSONL contém substring de 20+ caracteres do texto das fixtures, nem `HF_TOKEN`, `password` ou `DB_`. *Varredura do arquivo.*
- [x] **I17 — origem registrada em `metadata`.** Depois de ingerir a partir de um arquivo, `documents.metadata` contém o caminho **relativo** do fonte, e esse caminho basta para reler o arquivo, recalcular o canônico e obter o mesmo `doc_sha256` gravado. Nenhum caminho absoluto e nenhum texto do documento na coluna. *Banco.*
- [x] **Nenhuma dependência nova** em `requirements.txt`; a migração `0001` não muda e nenhuma migração nova é criada. *Leitura do diff da tarefa + `alembic heads` continua em `0001`.*

### Material de entrada

O acervo real não existe (o humano fará scraping depois) e **isso não trava a 004**: as invariantes I1–I17 são estruturais, valem para qualquer texto. Fixtures próprias em `backend/api/tests/fixtures/ingestao/`, teste em `backend/api/tests/test_ingestao.py`:

| Fixture | Para quê |
| --- | --- |
| `basico.txt` | títulos `#`/`##`, 3 seções, acentuação PT em NFC — I1, I3–I6, I9 |
| `numerado.txt` | títulos `1.`/`1.1`, lista com marcadores, tabela de 4 linhas — descida por `\n` |
| `bloco-gigante.txt` | parágrafo único > 400 tokens, com sentença > 400 tokens sem pontuação — I7 |
| `resto-curto.txt` | parágrafo final de ~20 tokens e seção inteira < 80 tokens — I8 |
| `sujeira.bin` | bytes com BOM, CRLF, CR solto, `\x00`, NBSP, `é` em NFD, 5 linhas em branco, espaços no fim — I2 |
| `abreviacoes.txt` | `Sr.`, `art.`, `p. 12` em frases longas — separador de sentença não corta em abreviação |

Sem golden file de spans: `.esperado.json` pinga a implementação e quebra em qualquer ajuste legítimo da heurística. O único "esperado" é o resultado da execução anterior, dentro do teste de determinismo.

## Fora do escopo

- Embedding, vetor, `embedding_model`, coluna `embedding`: migração `0002`, tarefa 008.
- PDF e qualquer extrator binário: tarefa 005.
- API HTTP de upload. O `requirements.txt` não tem `fastapi`, `uvicorn`, `starlette` nem `python-multipart`; expor upload exigiria dependência nova e nenhum critério do goal 1.2 precisa disso.
- FTS/`tsv`, retrieval, reranking, gate de suficiência: 006–008.
- Índice ANN, `heading_path`/breadcrumb (vira a hipótese H6 da 007).
- Alterar a migração `0001` ou criar migração nova.
- O tokenizer BERTimbau órfão saiu em commit separado `02d579d`; a 004 não o recria nem o reaproveita.
- Autenticação: `uploaded_by` é parâmetro obrigatório, não se inventa login.

## Esclarecer

**Nenhum aberto.** O único que podia virar bloqueio foi fechado pelo humano em 2026-10-01; os demais seguem com o default adotado.

- ~~Reconstrução do texto canônico a partir do banco.~~ **Fechado pelo humano:** "Não — guardar só o caminho do fonte em documents.metadata". A `0001` **não muda** e nenhuma migração nova entra na 004. O caminho relativo do arquivo fonte vai em `documents.metadata` (coluna JSONB `extra`, que já existe). O `doc_sha256` continua reverificável só com o arquivo de origem — é exatamente o que o harness da 007 já faz (003 §5).
- Caminho do rastro: nenhum arquivo do repo define. Default adotado: `backend/logs/rag-rastro.jsonl`, sobrescrevível por `MEMORIX_RASTRO_PATH` (testes usam `tmp_path`). `backend/logs/` passa a ser ignorado pelo git.
- `uploaded_by` sem autenticação: parâmetro obrigatório da função; nos testes, id opaco fixo.
- **Corrigido na etapa 2:** o tokenizer não é usado só para verificar I7 — `chunkar` conta tokens para decidir **cada** corte, então todo teste que chama `chunkar` depende dele. O grupo offline de verdade é só canonicalização (I2) e os 2 estáticos. Default mantido: `revision` fixada, carga preguiçosa (`functools.lru_cache`), `local_files_only=True` com skip acionável se o tokenizer não estiver no cache (a suíte nunca baixa sozinha). São ~17 MB de arquivos de tokenizer, não os 2,2 GB de pesos.
- Herdado da 003 §8, **não bloqueia a 004** (as invariantes são estruturais): a unidade `estrutural-v1` (~250–300 tokens) é a certa para sustentar questão/flashcard? Pergunta do `pedagogy-specialist`, viva para as tarefas 1.4/1.5.

## Plano

Fixado na etapa 2 pelo `ai-rag-specialist` (`OrchGoals1112.RagPlan004`) como especialista líder, **aprovado pelo humano** ("Aprovar como está"). **12 arquivos novos + 2 tocados em `backend/`** (`config/config.py` e `test_persistence.py`).

### Arquivos afetados (lista fechada)

| Caminho | O que entra |
| --- | --- |
| `backend/src/Memorix/ingestion/canonical.py` | novo. `canonicalizar(texto) -> str` (8 passos) e `doc_sha256(canonico) -> str`. Só `unicodedata`, `re`, `hashlib`; zero I/O, zero `transformers`. |
| `backend/src/Memorix/ingestion/chunking.py` | novo. `Trecho` (dataclass frozen), `tokenizer()` com `lru_cache`, `n_tokens(span)`, `chunkar(canonico) -> list[Trecho]`. **É o arquivo difícil.** |
| `backend/src/Memorix/ingestion/ingest.py` | novo. `ingerir(texto, *, doc_id=None, title, source_type, uploaded_by, origem, fonte, session=None) -> Resultado`. Canonicaliza e chunka fora da transação; `SELECT ... FOR UPDATE` → NO-OP / `UPDATE`+`DELETE`+`INSERT` → commit único. Grava o caminho relativo do fonte em `Document.extra`. Emite os 2 registros de rastro. |
| `backend/src/Memorix/providers/rastro.py` | novo, ~20 linhas. `registrar(trace_id, etapa, **campos)` → 1 linha JSONL append-only via `logging` + `FileHandler`. Resolve o caminho **na chamada**, nunca no import. |
| `backend/src/Memorix/config/config.py` | **tocado.** Acrescenta `ConfigIngestao`. Nada removido. Único arquivo de produto editado, não criado. |
| `backend/api/tests/conftest.py` | novo. Recebe as fixtures de banco da 002 (escopo `session`), mais `tokenizer` (com skip), `rastro` (`monkeypatch.setenv` + `tmp_path`), helper `_sessao(conn)` e os markers `banco`/`hf` via `pytest_configure`. |
| `backend/api/tests/test_persistence.py` | **tocado, autorizado pelo humano.** Deixa de declarar as fixtures de banco e passa a consumi-las do conftest. Mesmos 11 testes, mesmas asserções. O `sha256` registrado na 002 muda por causa disso. |
| `backend/api/tests/test_ingestao.py` | novo. As 21 funções do mapa abaixo. |
| `backend/api/tests/fixtures/ingestao/*` | novos: as 6 fixtures. Sem `.esperado.json`. |

`ConfigIngestao` em `backend/src/Memorix/config/config.py`, no padrão do `ConfigLaya` (atributos de classe, sem env): `estrategia="estrutural-v1"`, `extrator="texto-bruto@v1"`, `max_tokens=400`, `min_tokens=80`, `overlap=0`, `tokenizer="BAAI/bge-m3"`, `revision=<sha de 40 hex fixado na etapa 3>`, `rastro_path="backend/logs/rag-rastro.jsonl"`. `revision="main"` é **proibido**: destrói o determinismo que I1 promete. Parâmetros de chunking são de algoritmo, não de ambiente — pertencem ao código versionado, não ao `.env`.

**Por que esse corte:** 3 responsabilidades → 3 módulos, separados por *dependência*, não por camada — `canonical.py` não depende de nada, `chunking.py` depende do tokenizer HF, `ingest.py` depende do banco. Essa fronteira é exatamente a fronteira dos 3 grupos de teste. `ingestion/` já existe e está vazio no repo: o plano preenche, não cria estrutura. `rastro.py` fica em `providers/` porque a 006/007 vão emitir rastro sem importar ingestão. Nada de `Ingestor`/`BaseExtractor`/`ChunkerStrategy` (uma implementação só), nada de `repository.py` (SQLAlchemy já é a camada de dados), nada de `schemas.py`. A 005 acrescenta **um** arquivo (`ingestion/pdf.py`, `extrair(caminho) -> str`) e os três módulos de hoje ficam intocados — a extensibilidade está no tipo do parâmetro (`str`), não numa classe base.

### Passos

| Passo | Quem | Arquivos | Como será provado |
| --- | --- | --- | --- |
| 1. Gate humano do **plano** | humano | esta tarefa | Resposta literal registrada. Sem ela, nenhuma linha de produto. |
| 2. Fixtures + `conftest.py` + `test_ingestao.py` completo; **nenhum arquivo de produto** | `ai-rag-specialist` | fixtures (6), `conftest.py`, `test_ingestao.py` | `python -m pytest backend/api/tests/test_ingestao.py -q` da raiz: todos os testes de ingestão falham com `ModuleNotFoundError: ...ingestion.canonical` — motivo certo. Saída + sha256 colados aqui. Os 2 testes estáticos passam já aqui: é o pin inicial, esperado. |
| 3. Gate humano do **teste** | humano | — | Resposta literal registrada. Depois dele, teste e fixtures não são mais editados. |
| 4. `canonical.py` | `ai-rag-specialist` | `ingestion/canonical.py` | `pytest -q -k "canonic or sha"` → I2 verde; resto ainda em `ModuleNotFoundError`. Offline, < 1 s. |
| 5. `ConfigIngestao` + `chunking.py` | `ai-rag-specialist` | `config/config.py`, `ingestion/chunking.py` | `pytest -q -m "not banco"` → I1, I3(mem), I4(mem), I5–I9 verdes. É o passo de mais iterações. |
| 6. `providers/rastro.py` | `ai-rag-specialist` | `providers/rastro.py` | Prova isolada: escreve 1 linha em `tmp` e relê com `json.loads` — JSON válido, só as chaves declaradas. |
| 7. `ingest.py` | `ai-rag-specialist` | `ingestion/ingest.py` | `pytest -q backend/api/tests/test_ingestao.py` → I10–I17 verdes; suíte inteira verde. |
| 8. Perfil estrutural de referência | `ai-rag-specialist` | esta tarefa | Números extraídos do próprio `rag-rastro.jsonl` de uma execução real sobre as 6 fixtures. H-004 confirmada ou refutada. |
| 9. Prova final e conferência | `ai-rag-specialist`; conferido pelo `orchestrator` | esta tarefa | `python -m pytest backend/api/tests -q` da raiz, **incluindo `test_persistence.py`** (a 002 não pode regredir). Saída completa colada. |
| 10. Revisão e aceite final | `orchestrator`, humano | esta tarefa | Os 17 critérios marcados com o nome do teste correspondente. |

Cada passo de 4 a 7 fecha exatamente um módulo e um subconjunto nomeado de testes muda de vermelho para verde — nunca "melhora um pouco".

### Grupos de teste

| Grupo | Quantos | Marker | Custo |
| --- | --- | --- | --- |
| A — puro, offline | 4 (I2 ×2, estáticos ×2) | nenhum | < 1 s |
| B — puro + tokenizer HF | 10 (I1, I3mem, I4mem, I5–I9) | `hf` | ~2 s de carga, 1× por sessão (`lru_cache`) |
| C — banco de dev + tokenizer HF | 7 (I3banco/I4banco, I10–I17) | `banco`, `hf` | `upgrade head`/`downgrade base` 1× por sessão + 1 transação revertida por teste |

Quem mexe só em chunking roda `-m "not banco"` (A+B, ~3 s, zero conexão). Markers em `conftest.py` via `addinivalue_line` — o repo não tem `pytest.ini` nem `pyproject.toml`, e criar um para 2 markers é arquivo a mais por zero ganho.

`conftest.py` **recebe as fixtures de banco da 002**, por decisão do humano no gate de fixtures (2026-10-01, resposta literal: "Mover para o conftest.py, escopo session"). Saem de `test_persistence.py` e passam a viver no `conftest.py`, com escopo `session`: `ROOT`/`ALEMBIC_INI`, `_db_url()` com import tardio de `providers.database.DATABASE_URL`, `_secrets()`/`_no_secrets_in_errors()`, `engine` com `pool_pre_ping`, `migrated` com `to_regclass` antes e `upgrade head`/`downgrade base`, `conn` com transação revertida, savepoint no caso de erro. `test_persistence.py` passa a **consumir** o conftest, com os mesmos 11 testes e as mesmas asserções — é refactor de localização, não de comportamento. **Motivo material que fechou a decisão:** duas cópias da fixture fazendo `downgrade base` no teardown contra o **mesmo** banco de dev podem derrubar o schema no meio do outro arquivo durante a suíte completa. Não há mais duplicação, e o `# ponytail:` previsto na etapa 2 deixa de existir. **Acrescenta:** fixture `tokenizer` com skip, fixture `rastro`, e `_sessao(conn)` → `Session(bind=conn, join_transaction_mode="create_savepoint")`, que faz o `commit()` da aplicação virar release de savepoint dentro da transação revertida do teste. É esse helper que permite provar I10–I15 sem commitar nada no banco de dev — e é a razão de `ingerir(..., session=None)` existir.

Mudança maior que 3 arquivos → gate de plano e gate de teste ficam **separados**.

### Onde vai doer (previsto na etapa 2)

1. **Fronteira de token no fallback.** No SentencePiece do XLM-R o marcador `▁` faz o span do token incluir o espaço anterior. Saída prevista: I7 falha com chunks de 401–404 tokens, por `add_special_tokens` não desligado (`<s>`/`</s>` somam 2) e por escolher o corte na contagem do mapping global em vez de re-tokenizar o span cortado. Conserto: `add_special_tokens=False` sempre, maior `k` tal que o span re-tokenizado **isoladamente** dê ≤ 400, e recuar `e` por `isspace()` **antes** de medir.
2. **Fusão do chunk curto.** O risco não é quebrar, é **I8 passar por acidente**: se o teste avaliar fundibilidade contra a lista original em vez da final, a cláusula (b) vira tautologia. A varredura avalia sempre contra o estado corrente; I8 é computado só sobre o resultado final. Empate fixado já no passo 5: tentar o **anterior** primeiro, sempre — determinismo (I1) vale mais que distribuição bonita.
3. **Injetar falha no meio da transação (I13).** `ALTER TABLE chunks ADD CONSTRAINT ck_tmp CHECK (position <> 2) NOT VALID` dentro da transação do teste — DDL é transacional no Postgres e some no rollback, sem monkeypatch de ORM. Armadilha: se `ingerir` abrir a própria `SessionLocal()`, é outra conexão, não enxerga a constraint não commitada, os INSERTs passam e **I13 fica verde sem provar nada**. Sinal de que está certo: `IntegrityError` mencionando `ck_tmp` e, após o rollback, os `chunk_id`/`text` antigos intactos.
4. **Menor:** contagem O(n²) em `bloco-gigante.txt`. Previsão: < 2 s. Se passar, a saída **não** é bisect (deriva de ±1–2 tokens enfraquece o teto duro) — é memoizar por `(s, e)` num dict local, com `# ponytail:`.

## Baseline (IA)

Configuração: não há ingestão nem retrieval no código. | Casos: nenhum (a 006 cria `backend/evals/`). | Resultado: **Não se aplica nesta fatia** — confirmado pelo `ai-rag-specialist` na etapa 2.

Motivo: a 004 não altera recall@k, MRR nem fidelidade. Não existe retrieval no código e `backend/evals/` não está populado; comparar "antes × depois" de algo que não existia seria número inventado. O baseline que envolve `estrutural-v1` está declarado na 003 (bge-m3 denso 1024 + `estrutural-v1` 400/80/0 + busca exata + `k_cand` 30 + gate S1 + `k_ger` 8) e é medido na 007. As hipóteses de chunking (H5 overlap, H23 parent/child, H6 breadcrumb) pertencem à 007.

**O que substitui o baseline: perfil estrutural de referência.** Medido na primeira execução real sobre as 6 fixtures e colado aqui como tabela — nunca como `.esperado.json`, porque assertar esses números pingaria a heurística. Os dados saem do próprio `rag-rastro.jsonl`, que já carrega `n_tokens` por chunk: zero código de medição extra.

| Medida | Forma |
| --- | --- |
| nº de chunks | por fixture + agregado |
| `n_tokens`: mediana, p05, p95, máximo | 4 inteiros |
| nº e % de chunks com `n_tokens < 80` | depois da passada de fusão |
| nº e % de chunks que terminam em fronteira do fallback | `n_tokens` ≥ 395 e fim que não coincide com separador estrutural |
| nº de spans descartados por não ter alfanumérico | inteiro |
| % de code points do canônico cobertos por algum chunk | float |
| `duracao_ms` de Ingestão e de Chunking | do rastro |
| tamanho do canônico (code points) e `doc_sha256` | identidade da medição |

Serve a dois usos: a 007 compara o corpus real contra este perfil para saber se a heurística se comporta igual fora das fixtures; e qualquer mexida futura em `estrutural-v1` tem um número anterior para mostrar regressão em vez de "parece igual".

**Hipótese H-004 (testável, falsificável na primeira execução):** nas 6 fixtures, a descida recursiva por estrutura resolve o corte praticamente sozinha — **menos de 5%** dos chunks terminam em fronteira de token do fallback, e **menos de 20%** ficam abaixo de 80 tokens depois da passada única de fusão.

Se refutada, nenhum teste muda. A pedido do humano, a 004 experimentou agora redistribuir uma sobra curta dentro da mesma seção, mantendo as invariantes; o impacto em recuperação ainda pertence à 007.

**Perfil estrutural medido (2026-10-01; 6 fixtures; ingestão real no banco de dev com rollback da transação externa; rastro JSONL relido):**

| Fixture | SHA-256 do canônico | Chunks | `n_tokens` | Cobertura de code points |
| --- | --- | ---: | --- | ---: |
| basico.txt | `e6399125a055fa45bfa200bbd9d4a470f8b33936e1d4e06e7d493467816c46de` | 3 | 102, 105, 95 | 99,68% |
| numerado.txt | `ffa195d015e5003e8c83d870bd3e0ba4a8b8437478341730ad5d7ef4dd68dea2` | 3 | 55, 84, 128 | 99,59% |
| bloco-gigante.txt | `2940372dd5f78935e1f12d50894ef4682458ec56b5057c08ea7d5d44e695aa6a` | 4 | 400, 114, 400, 164 | 99,94% |
| resto-curto.txt | `476b1f448e404756106276607afed02a38edfb6d410c5f053601f410b815fb3b` | 3 | 190, 227, 15 | 99,83% |
| sujeira.bin | `96d776c182efe5bee31afef75421e5c800585e1ef4d88e8ae12b08d3ac073d52` | 2 | 44, 34 | 99,38% |
| abreviacoes.txt | `c1057f06728a961aa2470ac9bbad9db24477b0b28f3ec87a5a6d180931fa7e2d` | 1 | 186 | 100% |

Total 16 chunks; mínimo 15, mediana 109,5, p05 15, p95 400, máximo 400; **4/16 (25%)** abaixo de 80 (antes da revisão: 5/16, 31,25%). Pelo menos 1/16 (6,25%) termina em fronteira não estrutural dentro de texto alfanumérico (estimativa conservadora do fallback), contra alvo <5%. O JSONL tinha 12 registros (2 por documento), todos `status=ok`, `doc_sha256` e `chunk_id` presentes no registro de chunking; durações de ingestão 422–985 ms, chunking <1–235 ms. Descarte alfanumérico: 0; só espaços entre chunks ficam descobertos.

**H-004: Falhou nos dois limiares, mesmo após revisão** (25% ≥ 20%; pelo menos 6,25% ≥ 5%). Quatro chunks curtos são seções inteiras delimitadas por títulos (55, 15, 44 e 34 tokens): não podem ser fundidos sem violar I9. O bloco de 1.200 caracteres sem espaços obriga o fallback para cumprir I6/I7. Para atingir ambas as proporções nestas seis fixtures seria preciso ao menos 21 chunks (denominador artificial), quebrar limite de título/teto/cobertura ou avaliar num corpus representativo. Não fragmentar artificialmente para maquiar porcentagens. Nenhuma asserção estrutural falhou; decisão humana pendente.

## Teste primeiro (feature)

Escrito no passo 2 da etapa 3 pelo `ai-rag-specialist` (`OrchGoals1112.RagTest004`). 17 critérios → **21 funções** (55 casos com as parametrizações), sem buraco: nenhum critério sem teste, nenhum teste sem critério.

| Arquivo | sha256 |
| --- | --- |
| `backend/api/tests/test_ingestao.py` | `310973ef9dc9b8bc1a4d602eca5cb37d43091d35cc6696b2156dea02e287ae0c` |
| `backend/api/tests/conftest.py` | `851774e14e581c85ea5da90d3d6f825ec0b1d9f370e3da1974568574467fc3b7` |
| `backend/api/tests/test_persistence.py` (novo, após mover as fixtures) | `38ddb0586eed33f86b0cdca4a2fddae09c4d6fe62a6e245c499cf7df401be828` — substitui `022d4fc6…52ed7` |

**Falha pelo motivo certo, conferida pelo `orchestrator` em execução própria:**

```
./venv/Scripts/python.exe -m pytest backend/api/tests/test_ingestao.py -q
...
FAILED backend/api/tests/test_ingestao.py::test_metadata_guarda_caminho_relativo_do_fonte_que_reproduz_o_sha - ModuleNotFoundError: No module named 'backend.src.Memorix.ingestion.canonical'
55 failed, 2 passed in 17.78s
```

As 55 falham com `ModuleNotFoundError: No module named 'backend.src.Memorix.ingestion.canonical'` — código ausente. Nenhuma falha por erro de coleta, sintaxe, fixture ou dependência. Os 2 que passam são os estáticos (`test_requirements_sem_dependencia_nova`, `test_migracao_0001_inalterada`): é o pin inicial, esperado.

**A 002 não regrediu:**

```
./venv/Scripts/python.exe -m pytest backend/api/tests/ -q
55 failed, 13 passed in 33.18s
```

13 passed = 2 estáticos + os 11 de `test_persistence.py`, agora consumindo as fixtures do `conftest.py`. Nenhuma linha `FAILED` vem de `test_persistence.py`. Banco devolvido a `0001 (head)` depois da execução.

`revision` do tokenizer: **`5617a9f61b028005a4858fdac845db406aefb181`**, obtido de `HfApi().model_info("BAAI/bge-m3").sha` — 40 hex reais, nunca `"main"`. Fica como constante `TOKENIZER_REVISION` no `conftest.py`, **não** lida de `ConfigIngestao`: se o passo 5 escrever outra revisão no produto, as contagens divergem e o teste acusa. O passo 5 copia este literal para `ConfigIngestao.revision`.

| Critério | Função de teste | Marker |
| --- | --- | --- |
| I1 determinismo | `test_chunking_e_deterministico_em_duas_execucoes` (parametrizado nas 6 fixtures) | `hf` |
| I2 canônico idempotente | `test_canonicalizar_e_idempotente` + `test_sujeira_produz_o_mesmo_canonico_e_sha_da_versao_limpa` | — |
| I3 offsets válidos | `test_offsets_dentro_do_canonico` + (metade banco) o INSERT bem-sucedido em `test_recorte_exato_relido_do_banco` — `ck_chunks_offsets` rejeitaria offset inválido, então o INSERT passar **é** a prova; reinserir lixo já é teste da 002 | `hf` / `banco,hf` |
| I4 recorte exato | `test_recorte_do_canonico_bate_com_o_texto_do_chunk` + `test_recorte_exato_relido_do_banco` | `hf` / `banco,hf` |
| I5 disjunção | `test_chunks_sao_disjuntos_e_ordenados_por_position` | `hf` |
| I6 cobertura alfanumérica | `test_nenhum_alfanumerico_some_ou_troca_de_ordem` | `hf` |
| I7 teto duro | `test_nenhum_chunk_passa_de_400_tokens` (inclui `bloco-gigante.txt`) | `hf` |
| I8 piso | `test_chunk_abaixo_de_80_tokens_e_unico_da_secao_ou_infundivel` (`resto-curto.txt`) | `hf` |
| I9 título limite rígido | `test_nenhum_chunk_atravessa_inicio_de_titulo` | `hf` |
| I10 `position`/`chunk_id` | `test_position_contigua_de_zero_a_n_menos_um_e_chunk_id_gerado` | `banco,hf` |
| I11 NO-OP | `test_reingestao_com_sha_identico_nao_toca_chunks_e_registra_sem_mudanca` | `banco,hf` |
| I12 mesmos spans | `test_reingerir_a_depois_b_depois_a_reproduz_os_spans_da_primeira_ingestao` | `banco,hf` |
| I13 falha preserva | `test_falha_no_meio_dos_inserts_preserva_os_chunks_antigos` | `banco,hf` |
| I14 rastro completo | `test_ingestao_grava_duas_linhas_de_rastro_com_o_mesmo_trace_id` | `banco,hf` |
| I15 rastro de erro | `test_ingestao_que_falha_grava_rastro_com_status_erro_e_mesmo_trace_id` | `banco,hf` |
| I16 sem vazamento | `test_rastro_nao_contem_texto_do_documento_nem_segredo` | `banco,hf` |
| I17 origem em `metadata` | `test_metadata_guarda_caminho_relativo_do_fonte_que_reproduz_o_sha` | `banco,hf` |
| 18º dep./migração | `test_requirements_sem_dependencia_nova` (compara conjunto de **nomes** de distribuição, não versões, para não quebrar em bump de patch) + `test_migracao_0001_inalterada` (`versions/` tem exatamente 1 arquivo, com sha256 pinado) | — |

Local `backend/api/tests/` segue o layout aprovado pelo humano no gate 1 da 002 (resposta 05), não o `backend/tests/` genérico de `teste-primeiro.md`.

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| `requirements.txt` já cobre o tokenizer XLM-R (`transformers` 5.17.0, `tokenizers` 0.23.2, `sentencepiece` 0.2.2, `huggingface_hub` 1.32.0); `SQLAlchemy` 2.1.0 atende o `join_transaction_mode="create_savepoint"` | leitura do `requirements.txt` | Passou |
| `0001` exige `title`, `uploaded_by`, `source_type` NOT NULL, gera `chunk_id` e já tem a coluna JSONB `metadata` (atributo `extra`) que recebe o caminho do fonte | leitura de `entities/documents.py` | Passou |
| `providers/tokenizer.py` era BERTimbau (WordPiece PT), não XLM-R, carregava no import e não tinha importador no backend — **removido** pelo `Main` no commit `02d579d` | leitura + grep antes; verificação no disco depois | Passou |
| Código da 002 commitado em `develop` pelo `Main`: `5e68204` gitignore, `6f2f9aa` deps, `bfb9599` entities, `f67ad14` config, `b41cdad` providers, `a115037` migrations, `82fe97f` test, `02d579d` remoção do tokenizer. Árvore limpa (`git status --porcelain -uall` vazio) | `git log --oneline`, `git status` (só leitura) | Passou |
| Implementação: `canonical.py`, `chunking.py`, `ingest.py`, `providers/rastro.py` e `ConfigIngestao`; sem migração nem dependência nova | leitura dos arquivos + execução real | Passou |
| Os 17 critérios I1–I17 e os 2 guardrails (dependências, `0001`), inclusive após redistribuir a sobra de 20 tokens em 190/227 | `./venv/Scripts/python.exe -m pytest backend/api/tests/ -q` → **68 passed in 47.19s** (57 da 004 + 11 da 002) | Passou |
| Hashes dos testes congelados permanecem `310973ef…ae0c` (`test_ingestao.py`), `851774e1…c3b7` (`conftest.py`) e `38ddb058…828` (`test_persistence.py`) | `sha256sum` | Passou |
| Execução real com 6 fixtures, escrita/consulta do banco, rollback externo, 12 linhas JSONL lidas; nenhum documento residual | script efêmero via Python; métricas na seção Baseline | Passou |
| H-004 (<5% fallback; <20% abaixo de 80) | perfil estrutural após revisão | **Falhou** — pelo menos 6,25% e 25%; decisão humana pendente |
| Banco de dev devolvido à revisão `0001 (head)` após pytest | `alembic upgrade head` + `alembic current` | Passou |

## Revisão pedagógica

Veredito: **Não se aplica nesta tarefa** — a ingestão não produz nada que o aluno veja. | Achados: a pergunta da 003 §8 sobre a unidade `estrutural-v1` sustentar questão/flashcard continua aberta e é das tarefas 1.4/1.5, com os pontos pedagógicos hoje em espera por decisão do humano.

## Decisões e conflitos

- Recorte técnico fixado pelo `ai-rag-specialist` (`OrchGoals1112.RagIngest004`) na etapa 1, a pedido do `orchestrator`. Especialista único acionado → sem rodada de handshake, conforme `pipeline.md`.
- **Limite de 2 minutos: removido do pipeline pelo humano** em 2026-10-01, resposta literal: "tire o limite de tempo". Os acionamentos das etapas 1 e 2 tinham estourado o limite antigo (4m16s e 6m59s) e estavam registrados aqui como desvio; o registro de desvio fica obsoleto e sai. `Main` atualizou `pipeline.md` e os 3 arquivos de `.omp/agents/`.
- **Divergência com a 003 (P3), resolvida a favor do especialista** (decisão técnica de IA/RAG prevalece sobre o `orchestrator`): a P3 fundia só o **último** chunk curto da seção; a 004 estende a fusão a **qualquer** chunk abaixo de 80, em passada única (anterior → seguinte → mantém). Motivo: a redação original deixava o chunk curto do meio sem regra. Não contraria decisão do humano.
- `doc_sha256` sobre os bytes UTF-8 do texto **canônico**, não do arquivo cru: sem isso, hash e espaço de offsets deixam de ser a mesma identidade e a regra de acerto da 007 fica frouxa.
- Reingestão com sha idêntico é **NO-OP**, não apaga-e-reinsere: protege os `embedding` que a 008 gravará nas mesmas linhas e preserva `created_at`. O goal exige atomicidade do caminho que muda, não reescrita do que não mudou.
- `position` começa em **0** (alinhado ao passo 7 da P3).
- `max_tokens` é invariante **dura** (garantida pelo fallback por fronteira de token); `min_tokens` é **piso de melhor esforço**. Essa distinção é a fonte nº 1 de ambiguidade e está escrita nesses termos de propósito.
- Contagem de tokens por span é O(n²) no pior caso — aceitável no teto de ~10 mil trechos do MVP, a ser marcado no código com `# ponytail:` e trocado por bisect só se a ingestão passar de segundos. Bisect desde já introduziria deriva de ±1–2 tokens e enfraqueceria a invariante do teto.
- Sem `index_version` no rastro (decisão do humano, gate 2 resposta 11 da 002, reafirmada na 003). `rag-rastreabilidade.md` ainda cita `index_version`: divergência conhecida, já levantada na 003 §8. A 004 segue o humano e **não** edita a instrução.
- A 004 não gera embedding, então não há `embedding_model` no rastro desta tarefa; o versionamento presente é `estrategia="estrutural-v1"` + `parametros.tokenizer`/`revision`.

**Gates do humano (2026-10-01), respostas literais repassadas por `Main`.** A numeração é a dos 5 gates que o `orchestrator` apresentou ao fim da etapa 1.

> gate1: "Autorizar o goal 1.2 inteiro (004 e 005/PDF)"
> gate2: "7 commits atômicos, em develop"
> gate3: "Não — guardar só o caminho do fonte em documents.metadata"
> gate4: "Checkout principal"
> gate5: "Remover agora, em commit separado"

Consequências nesta tarefa:
- **gate1:** execução do goal 1.2 autorizada por inteiro. A 005 (PDF) já está autorizada e abre quando a 004 for aceita. Registrado em `.omp/goals/README.md` e em `01.2-ingestao-acervo.md`.
- **gate2:** o código da 002 é commitado em `develop` pelo `Main`, em 7 commits atômicos, enquanto esta tarefa planeja. A 004 passa a partir de uma base versionada. `backend/logs/` entra no `.gitignore`, o que cobre também o `rag-rastro.jsonl` que esta tarefa vai escrever.
- **gate3:** `[ESCLARECER]` do texto canônico **fechado**. Sem reconstrução pelo banco, sem `documents.source_text`, sem mudança na `0001` e sem migração nova. O caminho relativo do fonte vai em `documents.metadata`. A tarefa **não** volta para replanejar — a condição de bloqueio que eu havia registrado não se realizou.
- **gate4:** a 004 roda no **checkout principal, sem worktree**. O script `.omp/scripts/worktrees.ps1` não é usado nesta tarefa. Consequência prática: a etapa 6 atualiza a tarefa **e** o `progresso.md` na mesma sessão (a regra de "progresso só no checkout principal" deixa de ser restrição aqui).
- **gate5:** `backend/src/Memorix/providers/tokenizer.py` (BERTimbau órfão) é removido pelo `Main` em commit separado. A 004 **não** o reaproveita e **não** o recria; a carga do tokenizer XLM-R do `BAAI/bge-m3` é trabalho novo desta tarefa, com `revision` fixada e carga preguiçosa.

Divisão de trabalho acordada com `Main` em 2026-10-01: o `Main` executa os commits (gate 2) e a remoção (gate 5); o `orchestrator` não toca em git nem em `backend/` enquanto isso. A etapa 3 confere o estado da árvore antes de começar.

**Etapa 2 (2026-10-01), `ai-rag-specialist` `OrchGoals1112.RagPlan004` como especialista líder.** Especialista único → sem rodada de handshake.

Divergências da etapa 2 em relação à etapa 1, todas aceitas (decisão técnica de IA/RAG prevalece sobre o `orchestrator`):
- **Correção sobre o tokenizer.** A etapa 1 escreveu "o teste de I7 precisa do tokenizer, os outros 15 continuam offline". Errado: `chunkar` conta tokens para decidir **cada** corte, então 17 dos 21 testes dependem do tokenizer e só 4 são offline. Corrigido na seção Esclarecer. Injetar um contador falso para libertar os testes estruturais foi **considerado e descartado**: o fallback corta na fronteira de token real, então exigiria também fronteiras falsas — dois parâmetros de injeção e um caminho que ninguém roda em produção.
- **`ingerir(..., session=None)`**, parâmetro que a etapa 1 não previu. Sem sessão injetável, I13 não é provável: se `ingerir` abrir a própria `SessionLocal()`, ela não enxerga a constraint temporária não commitada do teste, os INSERTs passam e o teste fica verde sem provar nada.
- **O 17º critério virou 2 testes** (dependência nova × migração inalterada), porque falham por motivos independentes.
- **I17 acrescentado pelo `orchestrator`** depois do gate 3: a decisão do humano sobre `documents.metadata` só vira critério se for verificável, e a forma verificável é "o caminho gravado basta para reler o fonte e reproduzir o `doc_sha256`".
- **`conftest.py` recebe as fixtures de banco da 002 — decisão do humano, contra a recomendação do `orchestrator`.** Eu havia recomendado duplicar as fixtures para não tocar em teste já aprovado; o humano respondeu "Mover para o conftest.py, escopo session" e autorizou explicitamente a alteração do `test_persistence.py`. Pela ordem de autoridade, vale o humano. O motivo material que ele seguiu derruba a minha posição: duas cópias da fixture fazendo `downgrade base` no teardown contra o **mesmo** banco de dev podem derrubar o schema no meio do outro arquivo durante a suíte completa — ou seja, duplicar não era o caminho seguro, era o caminho com uma corrida silenciosa. O `# ponytail:` previsto na etapa 2 deixa de existir.
- **`revision` do tokenizer é literal de 40 hex, nunca `"main"`.** `"main"` destruiria o determinismo que I1 promete: o teto de 400 passaria a depender da data do download.

**Etapa 3, passo 2 — teste primeiro (2026-10-01), `ai-rag-specialist` `OrchGoals1112.RagTest004`.** Decisões tomadas ao escrever o teste, conferidas pelo `orchestrator`:

- **`_secrets`/`_no_secrets_in_errors` viraram import de módulo, não fixture.** Eles são chamados **fora** de qualquer teste, dentro do helper `_alembic()`, que por sua vez é usado tanto pela fixture `migrated` quanto pelo teste `test_downgrade_base_remove_tabelas_e_upgrade_roda_de_novo`. Transformá-los em fixture obrigaria a reescrever a assinatura de um teste já aprovado — o oposto do que o humano autorizou. `from conftest import ...` funciona porque `backend/api/tests/` não tem `__init__.py` e entra no `sys.path` com o importmode `prepend` padrão. `test_persistence.py` ficou sem cópia local de nada que foi movido.
- **`origem` sai da assinatura de `ingerir`.** O plano previa `origem` e `fonte` separados; o campo `origem` do rastro (tipo + nome do arquivo) é derivável de `fonte` + `source_type`, nenhum critério I1–I17 o exercita isoladamente, e parâmetro que o teste não exercita é superfície não testada. Decisão técnica do especialista, aceita. O passo 7 implementa sem `origem`.
- **`fonte` é caminho relativo à raiz.** I17 verifica que o valor gravado em `documents.metadata` é relativo, relegível por `ROOT / caminho`, e que reler + recanonicalizar reproduz o `doc_sha256`. A **chave** do JSONB não é pinada — o teste varre os valores à procura de um caminho legível —, só o valor. Isso evita pinar uma escolha de nomenclatura que o produto ainda não fez.
- **`bloco-gigante.txt` precisou de um trecho sem espaço para chegar ao fallback.** A descida recursiva tem o nível 5 ("espaço"), então um parágrafo longo com espaços **nunca** alcança o fallback terminal — e I7 jamais provaria o teto duro, que é a invariante que o plano chama de obrigatória. A fixture ganhou uma sequência de nucleotídeos de 1200 caracteres sem espaço (550 tokens), plausível numa apostila de biologia. Total: 1077 tokens, 1 linha, zero linha em branco, zero pontuação de fim de sentença.
- **I8 blindado contra passar vazio** (risco nº 2 do "Onde vai doer"): `assert curtos` falha se `resto-curto.txt` deixar de produzir chunk abaixo de 80 tokens, e a fundibilidade é avaliada contra o **resultado final**, nunca contra uma lista pré-fusão. Fixture calibrada com o tokenizer real: seção 1 = 397 tokens, + parágrafo final de 20 = 417 (> 400, infundível → caso b); seção 2 inteira = 15 tokens (→ caso a).
- **I11 não é detectável por `created_at`.** `now()` do Postgres é o timestamp do início da transação, e tudo roda dentro da transação do teste: apagar-e-reinserir produziria o **mesmo** `created_at` e o mesmo `chunk_id`. O teste compara `(chunk_id, created_at, ctid)` — o `ctid` muda em qualquer DELETE+INSERT e é o detector de verdade. `created_at` e a contagem continuam assertados porque são o texto do critério.
- **I13 exige ≥ 3 chunks no conteúdo novo**, não no antigo: a constraint temporária `check (position <> 2) NOT VALID` só morde os INSERTs da reingestão. `assert len(novos) >= 3` impede que o teste vire um "DID NOT RAISE" silencioso.
- **Traceback acumulado, corrigido.** A primeira versão do stub relançava a mesma exceção e o traceback somava todos os testes anteriores: 59.507 linhas / 3 MB de saída. Trocado por `raise ModuleNotFoundError(msg, name=...) from None` — exceção nova a cada chamada, mesmo tipo e mesma mensagem, 1 frame por falha.
- **Cache do tokenizer populado** (~17 MB, só arquivos de tokenizer, nenhum peso) via `snapshot_download` com `allow_patterns`. Estava vazio, e sem isso a fixture daria skip e os 17 testes de chunking nunca rodariam. É ação de ambiente de dev: zero arquivo no repo, zero dependência nova.
- **Contagem dos grupos A/B/C corrigida:** o plano dizia 4/10/7; a coluna de markers do mapa dá 4 sem marker / 8 `hf` / 9 `banco,hf` = 21. Vale a coluna de markers, que é a executável.

Pontos que precisam de decisão e foram levados ao humano junto com o gate do teste:
1. **CR solto na canonicalização.** Lidos ao pé da letra, o passo 3 ("remover controles C0 exceto `\n` e `\t`") apaga o `\r` antes de o passo 4 ("`\r` isolado → `\n`") agir — o passo 4 vira código morto. O teste pina a leitura em que as duas regras coexistem: em `sujeira.bin` o CR solto vira quebra de linha. Veredito contrário muda a constante `LIMPO` e o teste volta ao gate.
2. **Marcar os 11 testes da 002 com o marker `banco`.** Sem isso, `pytest backend/api/tests/ -q -m "not banco"` ainda roda a 002 contra o banco, e a promessa de "zero conexão" só vale apontando para `test_ingestao.py`. É uma linha, mas mexe de novo em teste aprovado.

**Gate do teste (2026-10-01):** humano respondeu "Aprovar — congela os testes e libera a implementação (passos 4 a 7)". CR solto: "Vira quebra de linha". Marker `banco` nos testes da 002: "Não marcar" — loop offline por caminho explícito `backend/api/tests/test_ingestao.py -m "not banco"`. Os três testes permaneceram com o SHA registrado no gate.

**Execução:** o `orchestrator` e o `ai-rag-specialist` ficaram indisponíveis por erro 429 ao retomar a etapa 3; `Main` implementou os quatro módulos conforme o plano técnico já aprovado, sem alterar o teste congelado. Evidência própria: 68 testes passaram, rastro de 6 ingestões reais relido e banco restaurado. A hipótese H-004 foi refutada nas fixtures e será levada ao humano no aceite final, sem disfarçá-la como sucesso.

**Revisão pedida pelo humano:** no gate de aceite da 004, respondeu "Não aceitar; revisar chunking agora". O `Main` corrigiu o reconhecimento de abreviações (antes a expressão regular considerava o último caractere de qualquer palavra uma inicial) e redistribuiu um resíduo de 20 tokens na mesma seção entre duas fronteiras de sentença: os chunks de 397/20 passaram a 190/227; nenhuma linha de título foi cruzada. Os testes congelados passaram novamente (68/68), hashes intactos, banco devolvido a `0001 (head)`. H-004 melhorou de 31,25% para 25% abaixo de 80, mas os limiares continuam impossíveis nesta amostra sem violar invariantes ou fragmentar para inflar o denominador. O humano autorizou a 005 em outra worktree; esta depende do aceite/commit da 004 antes de poder partir de `develop`.

**Aceite final (2026-10-01):** após a redistribuição da sobra curta, o humano respondeu "Aceitar a 004; H-004 continua Falhou nas fixtures". Também autorizou "Sim, commits atômicos da 004 em develop" para a 005 poder partir de uma base completa em outra worktree. O aceite não transforma a hipótese refutada em Passou; o perfil do acervo real permanece para a 007.
