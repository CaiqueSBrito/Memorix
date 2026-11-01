# Memorix

Backend educacional em português: acervo PDF/texto → retrieval local → conteúdo com fontes → respostas → acurácia, revisão espaçada e indicação de material. **Frontend web e app mobile ficam para depois.**

## Estado

- PostgreSQL/SQLAlchemy/Alembic: documentos, trechos, vetores de 1.024 dimensões, busca textual em português, contas, sessões revogáveis, convites para menores e histórico de estudo.
- Ingestão PDF com texto selecionável ou OCR local Tesseract `por`; canonicalização e chunking estrutural de até 400 tokens. Páginas vazias são omitidas; documento inteiro sem texto é rejeitado.
- Retrieval exato BGE-M3 + FTS `pt_unaccent`/RRF; reranker BGE local e gate de suficiência. Laya classifica pedidos sem tipo explícito; baixa probabilidade exige esclarecimento.
- Geração local via Ollama: múltipla escolha, V/F, flashcards, aulas e dissertativas; validação de estrutura, proveniência e suporte. Saídas inválidas não são entregues como conteúdo de estudo.
- API com isolamento por aluno, gabaritos privados, autoavaliação de flashcards separada da acurácia objetiva, correção dissertativa por rubrica, plano de revisão e recomendações com as respostas que os motivaram.
- Rastro JSONL por `trace_id`, agregação de latência/erros/tokens e evals separados de retrieval, classificação e geração.

Implementação não equivale a aceite de qualidade nem autorização de produção. Estado dos goals e evidências: [.omp/goals/](.omp/goals/README.md), [tarefa 013](.omp/tasks/013-backend-ia-todos-goals.md) e [progresso](.omp/progress/progresso.md).

## Ambiente

Python 3.12; dependências em `requirements.txt`. Para os modelos locais, GPU NVIDIA/CUDA 12.8 é recomendada; a configuração do Laya usa CUDA. A execução medida nesta máquina usa GPU de 6 GiB, PostgreSQL 17 e Ollama com `qwen2.5:7b-instruct-q4_K_M` (aproximadamente4,7GB de pesos). Instale separadamente Tesseract e dados `por` para OCR, ou configure `TESSERACT_CMD`.

```powershell
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128
ollama pull qwen2.5:7b-instruct-q4_K_M
```

Modelos Hugging Face fixados:

| Uso | Modelo | Revisão |
| --- | --- | --- |
| Embedding/tokenizer | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` |
| Reranking | `BAAI/bge-reranker-v2-m3` | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |
| Classificação | `Riupul/laya-multilingual-finetuning-memorix` | `a200a32c9c4859d9ec5ed84a8a160465ec2dcb5b` |

Ollama medido: digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`. As tags do Ollama podem mudar; repita as avaliações se atualizar os pesos. Nesta execução os modelos já estão em cache; não há download pendente.

Baixe antes de iniciar a API; providers usam cache local. Se o checkpoint Laya exigir acesso, configure `HF_TOKEN` no ambiente de download, nunca no código/logs.

```python
from huggingface_hub import snapshot_download

snapshot_download("BAAI/bge-m3", revision="5617a9f61b028005a4858fdac845db406aefb181", allow_patterns=["config.json", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "sentencepiece.bpe.model"])
snapshot_download("BAAI/bge-reranker-v2-m3", revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", allow_patterns=["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "sentencepiece.bpe.model"])
snapshot_download("Riupul/laya-multilingual-finetuning-memorix", revision="a200a32c9c4859d9ec5ed84a8a160465ec2dcb5b", allow_patterns=["model.safetensors", "rl_agent_config.json", "encoder/config.json", "tokenizer/*"])
```

## Banco local isolado

Não rode a suíte no banco de produção: fixtures fazem `downgrade base`. O `.env` Supabase original permanece separado do desenvolvimento local; o projeto remoto configurado rejeitou o tenant/usuário nesta execução.

```powershell
docker run --detach --name memorix-dev-013 --publish 127.0.0.1:55432:5432 --env POSTGRES_USER=memorix --env POSTGRES_PASSWORD=memorix-local-dev-013 --env POSTGRES_DB=memorix_dev --volume memorix-dev-013-data:/var/lib/postgresql/data pgvector/pgvector:pg17
docker exec memorix-dev-013 psql -U memorix -d memorix_dev -c "CREATE DATABASE memorix_test"
```

Crie `.env.local` (ignorado pelo Git). A senha abaixo é **exclusivamente de desenvolvimento em loopback**, não de produção:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=55432
DB_USER=memorix
DB_PASSWORD=memorix-local-dev-013
DB_DATABASE=memorix_dev
DB_SSLMODE=disable
```

`MEMORIX_ENV_FILE` seleciona outro arquivo em vez de `.env`, mas variáveis já presentes no processo têm precedência. Para evitar herdar `DB_*` do Supabase no terminal/serviço, os comandos abaixo usam o CLI já instalado de `python-dotenv` com `--override`:

```powershell
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m alembic -c backend/api/alembic.ini upgrade head
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.src.Memorix.services.auth create-admin admin@example.test
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

A criação do admin pede senha por `getpass`; cadastro público nunca aceita papel admin. Use **um worker** na GPU de 6 GiB; operações de modelo são serializadas dentro do processo. Não rode evals/inferência em outro processo simultaneamente ao servidor nessa GPU.

## API

Contrato interativo local em `http://127.0.0.1:8000/docs`; OpenAPI em `/openapi.json`. Envie tokens por `Authorization: Bearer <token>`, nunca na URL.

| Fluxo | Rotas |
| --- | --- |
| Disponibilidade | `GET /health` |
| Contas/sessões | `POST /auth/register`, `/auth/login`, `/auth/logout` |
| Menores | `POST /admin/minor-invitations` após verificação externa do responsável |
| Acervo admin | `POST /admin/ingest/text`, `/admin/ingest/pdf`, `/admin/index` |
| Geração/estudo | `POST /study/generate`, `GET /study/content/{id}` |
| Flashcards | `POST /study/content/{id}/items/{item_id}/reveal` registra entrega do verso antes da autoavaliação |
| Respostas | `POST /study/content/{id}/answer` com `item_id`, `answer`, `request_id` e, para flashcard, `self_assessment` |
| Evolução | `GET /study/history`, `/study/accuracy`, `/study/plan`, `/study/recommendations` |
| Fontes | `GET /study/materials/{doc_id}?chunk_id=...`, `/study/materials/{doc_id}/download` |
| Observabilidade admin | `GET /admin/traces/{trace_id}`, `/admin/metrics` |

Exemplo de geração autenticada:

```json
{"prompt":"Crie um flashcard sobre a membrana plasmática","type":"flashcards","count":1}
```

Tipos explícitos: `multiple_choice`, `true_false`, `flashcards`, `lesson`, `essay`. O tipo pode ser omitido para classificação Laya; pedido ambíguo retorna `clarification`. Tema sem suporte retorna `not_found`, sem persistir conteúdo. Erros de modelo/validação não são respostas pedagógicas aprovadas.

`count` aceita1–5; sem valor explícito, o pipeline pode inferir a quantidade do pedido. Conflitos entre tipo/quantidade explícitos e o texto são rejeitados. `difficulty`: `basic`, `intermediate`, `advanced`; `cognitive_level`: `recall`, `understand`, `apply`, `analyze`. Padrão inicial documentado: básico/compreensão, não uma adaptação pedagógica validada.

- Cadastro de adulto exige `adult_confirmed: true`. Menor exige convite único vinculado ao e-mail, criado por admin que declara ter verificado o responsável **fora do sistema**. Isso não verifica idade automaticamente nem atesta conformidade jurídica.
- Gabarito, explicação privada, rubrica e citações que revelam a resposta não vêm no conteúdo inicial. Para flashcards, `POST /reveal` disponibiliza o verso ao proprietário e registra o processamento sem criar tentativa; repetir é idempotente. `POST /answer` sem revelação daquele item retorna409. O antigo `GET /reveal` retorna405; não há alias de transição. O registro é confirmado antes da resposta HTTP: não comprova recebimento, visualização, leitura ou aprendizagem.
- Acurácia objetiva inclui somente MC/V-F; histórico distingue primeira tentativa e revisão. Flashcards são autoavaliação; dissertativas são correção assistida por rubrica, não nota objetiva.
- Revisão usa intervalos simples de 1, 3, 7 e 14 dias conforme acertos consecutivos; erro reinicia. Não há promessa de algoritmo adaptativo validado ou notificações automáticas.
- Dissertativas usam critérios atômicos com `points`, `criterion`, `expected_answer`. O modelo atribui pontos e seleciona evidência literal da resposta; o servidor soma a nota e compõe feedback consistente com os critérios. Citação não vazia permanece mesmo em critério zerado, como “Trecho avaliado da sua resposta”, sem apresentar erro como prova de acerto. Nota fora da acurácia objetiva; julgamento automático ainda pode errar.
- `request_id` evita respostas duplicadas; reutilização com conteúdo divergente retorna conflito. Histórico/plano/indicações pertencem ao aluno autenticado.
- PDF admin é armazenado em `backend/uploads/` (ignorado), com nome UUID. Autorização ocorre antes de ler o corpo; PDF até 256 MiB e texto até 8 MiB. Upload exige `Content-Length` e rejeita transferência chunked. Ingestão e indexação são duas etapas: falha do índice mantém o documento para reindexação por `/admin/index`.

## Corpus e avaliações

Nesta execução foram ingeridos **17 PDFs, 7.158 trechos/vetores** no banco local, sem alterar o Supabase. Há 20 casos reais anotados por SHA-256 e offsets em `backend/evals/retrieval/cases.jsonl` e 20 pedidos de classificação. As amostras de geração são sintéticas e permanecem separadas de dados de aluno.
A captura de amostras públicas restaura o provider ao terminar ou falhar e ignora saídas de outras threads. Benchmarks simultâneos são serializados; a substituição permanece global durante a avaliação. Isso não autoriza inferência concorrente na GPU nem transforma amostras de aluno em dados públicos.


Curadoria administrativa: `POST`/`GET /admin/review-spans` e `DELETE /admin/review-spans/{id}` registram intervalos canônicos `[offset_start, offset_end)` por SHA-256 do documento e motivo. A migração `0004` mantém exclusões independentes dos IDs de chunks; tanto o ramo denso quanto FTS excluem trechos sobrepostos. Conteúdo anterior com fonte em revisão retorna410; histórico é preservado/sinalizado, mas tentativas contaminadas não contam na acurácia válida, plano ou recomendações. Isso é curadoria humana explícita, não auditoria científica automática.
```powershell
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.evals.run ingest --corpus "C:/caminho/do/acervo"
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.evals.run index
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.evals.run retrieval --corpus "C:/caminho/do/acervo" --out backend/evals/results/retrieval.json
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.evals.run laya --out backend/evals/results/laya.json
./venv/Scripts/python.exe -m dotenv -f .env.local run --override -- ./venv/Scripts/python.exe -m backend.evals.run generation --out backend/evals/results/generation.json
```

Baseline pré-curadoria (`retrieval.json`): híbrido/reranker9/12 e p95 quente469ms. Na014, com um intervalo em quarentena, quatro variantes/100consultas quentes cada isolaram o componente lexical com reranker fixo: denso6/12→híbrido8/12, ganhos ret05/ret06 sem perdas, p95 quente454→468ms e FAR leave-one-out0 nos dois (`retrieval_four_variants_014.json`). Isso sustenta manter a busca híbrida, sem atribuir ao lexical o ganho conjunto do reranker. Gate runtime `-1.067626953125`; calibração registrada FAR0/8 e FRR0/12 nos20casos, sem garantia externa. Laya17/20; o limiar usa `probabilities[choice]`, não a entropia `confidence`.

Fidelidade ao PDF não garante correção científica: foi identificado um trecho sobre cianobactérias com erro no próprio material. O intervalo identificado foi colocado em quarentena pelo endpoint admin no banco local; o chunk problemático retorna410, outro chunk do mesmo documento permanece acessível e ambos os ramos de busca respeitam a exclusão. A correção editorial da fonte continua pendente, e o acervo não foi integralmente auditado.

Versão final em `generation_final_013.json`, mantendo20casos e1span ativo:8/12positivos passaram a validação,4foram rejeitados,8/8negativos recusados. A taxa0,80 inclui recusas, **não**16conteúdos estudáveis. O juiz apoiou29/38afirmações e deu relevância combinada0,50/20casos. Detectou-se conteúdo sobre o tema mas fora do objetivo (ret10/ret11); por isso a qualidade geral dos goals de IA **não está aceita**. Reformulações de juiz e busca foram medidas, mas rejeitadas por piorarem positivos/erros do gate; nenhum novo modelo foi baixado para ocultar a limitação.

Continuação014 experimentou schema evidence-first nos mesmos20casos: saídas positivas8→6/12 e relevância local10→9/20. Candidato rejeitado; geração estável preservada, sem novo modelo ou chamadas extras no runtime. Qualidade geral não aceita só porque a razão condicional de claims apoiadas aumentou.

Continuação015 mediu decomposição literal nos mesmos20pedidos:20planos válidos,ret10dividido em três objetivos. As buscas por objetivo não recuperaram a âncora rotulada; acrescentar o tema ainda perdeu pena de morte no gate. Candidato não incorporado, sem chamadas extras no runtime. Não houve nova bateria completa de geração; métricas gerais acima continuam da013.

## Testes e privacidade

Os testes usam PostgreSQL real; fronteiras de inferência podem ser simuladas nos testes para isolar autorização e persistência. Os evals e o smoke de API são provas separadas com modelos locais reais. Para testar, copie a configuração local para `.env.test` e altere **somente** `DB_DATABASE=memorix_test`:

```powershell
./venv/Scripts/python.exe -m dotenv -f .env.test run --override -- ./venv/Scripts/python.exe -m pytest backend/api/tests -q
```

Prova integrada atual: **155 testes passaram** no PostgreSQL isolado (29,47s), com um aviso TestClient/HTTPX. A013 provou cinco formatos/respostas/notas/revisão; a014 provou ordem de revelação dos flashcards. A015 provou captura pública restaurada após sucesso/erro com Qwen real e correção HTTP201/nota0 preservando frase incorreta no feedback/histórico, com replay200. Evidências e hashes em `backend/evals/results/verification_013.json`, `verification_014.json` e `verification_015.json`. Retrieval quente468ms não é latência ponta a ponta nem aceite de qualidade.

O rastro append-only fica em `backend/logs/rag-rastro.jsonl`, ou em `MEMORIX_RASTRO_PATH` (prefira absoluto para ferramentas de corpus). Não guarda prompts/respostas do aluno, senhas ou tokens. Consulte por `trace_id` com `read_trace` e agregue com `summarize_traces` em `providers/observabilitiy.py`. As inferências do produto usam somente Ollama loopback e modelos locais; download de pesos não envia o acervo.

**Antes de produção:** HTTPS e controle operacional, avaliação jurídica de menores/consentimento/retensão, curadoria do material e metas de qualidade ainda não aceitas. PostgreSQL remoto deve usar `DB_SSLMODE=verify-full` e CA confiável; o padrão legado `require` cifra, mas não garante validação de hostname/cadeia. O perfil `disable` só serve ao banco local isolado.

Funções/variáveis internas em inglês (`snake_case`); nomes impostos por ferramentas, dados persistidos e conteúdo PT são preservados. Migrações: `0001` original preservada, `0002` vetores/FTS, `0003` contas e estudo, `0004` fontes em revisão e `0005` revelações de flashcard. Aplique `alembic upgrade head` antes de iniciar a API atualizada; nenhuma revelação é fabricada para dados históricos.
