# Memorix

Sistema educacional web, em português, que usa IA (RAG sobre um acervo próprio) para o aluno criar e estudar material a partir de conteúdo curado.

> **Estado:** estágio inicial. Já existem o classificador de intenção, acervo de texto/PDF, geração local de rascunhos, revisão humana, questionários com acurácia e plano local de prática pela CLI. A geração usa busca lexical, validação estrutural e citações literais verificadas. Busca semântica, interpretação automática integrada do pedido, repetição espaçada, contas e interface web ainda não foram implementadas.

## O que o Memorix faz (visão)

- **Formulários** — questionários de múltipla escolha e verdadeiro/falso.
- **Aulas** geradas a partir do acervo.
- **Flashcards** para prática de recuperação.
- **Plano de estudo** baseado na acurácia das respostas do aluno.
- **Acompanhamento e indicação de material** do acervo conforme o desempenho.

Papéis: o **admin** alimenta o acervo (PDF e texto); o **aluno** gera conteúdo, estuda e responde.

Ciclo central:

```text
admin envia material → acervo
  → aluno pede formulário, aula ou flashcard
  → RAG gera um rascunho a partir do acervo → revisão humana
  → aluno responde → acurácia por questão
  → plano de estudo + indicação de material
  → volta ao estudo
```

Princípios:

- **Fidelidade ao acervo** — todo conteúdo gerado é sustentado por trechos do acervo; sem fonte, não é entregue como fato.
- **Rastreabilidade** — todo conteúdo aponta para os trechos (`doc_id`, `chunk_id`) que o sustentam.
- **Base pedagógica** — prática de recuperação e repetição espaçada.
- **Privacidade (LGPD)** — o público inclui menores de idade: coleta mínima, sem dados do aluno em logs e sem envio a terceiros.

## Pipeline RAG (visão e estado)

```text
pedido do aluno
  → pedagogical_understand   intenção: tema, tipo, quantidade, dificuldade
      └ node classifier      flashcard | questionário (MC | V/F) | aula
  → retrieval → reranking
  → generation_adapter       prompt e schema por tipo de conteúdo
  → geração (LLM)
  → resposta
```

Implementados: node classifier independente e fluxo integrado `tema/tipo explícitos → recuperação FTS5/BM25 → prompt/schema por tipo → LLM local → validação de estrutura e citações`. Os rascunhos podem ser importados na biblioteca SQLite, revisados e, para múltipla escolha e V/F, estudados em sessões com correção objetiva e acurácia histórica. O classificador ainda não participa desse fluxo; não há reranking nem avaliação automática da correção pedagógica ou fidelidade semântica.

## Estrutura

```text
backend/
  src/Memorix/
    __main__.py                CLI de ingestão, geração, revisão, estudo e planejamento
    config/config.py           ConfigLaya: modelo e idioma do classificador
    contracts/questions.py     LayaChoiceQuestion + pergunta CONTENT_TYPE
    contracts/generation.py    pedido de geração: tipo, tema, quantidade e dificuldade
    providers/laya_provider.py Router da Laya (classificação do pedido)
    providers/tokenizer.py     tokenizer BERTimbau (neuralmind/bert-base-portuguese-cased)
    providers/local_llm.py     Chat Completions restrito a loopback
    ingestion/corpus.py        acervo SQLite, trechos e busca FTS5/BM25
    generation_adapter/material.py prompts, schemas e validação das citações
    pipeline/generation.py    recuperação → geração → validação
    storage/material_validation.py validação de rascunhos contra o acervo atual
    storage/materials.py       biblioteca SQLite e decisões de revisão com versão
    storage/study_sessions.py  sessões e snapshots de versões aprovadas
    study/grading.py           perguntas sem gabarito e correção objetiva
    study/progress.py          acurácia por material, versão e questão
    study/planning.py          prioridades por questão e recursos com trechos compartilhados
  evals/test_corpus.py          regressões do acervo
  evals/test_pdf_ingestion.py   PDFs reais, páginas e migração do banco
  evals/test_generation_*.py    contratos e limites da geração
  evals/test_local_llm.py       isolamento de rede e erros do servidor
  evals/test_material_*.py      referências, persistência e revisão concorrente
  evals/test_study_*.py         correção, sessões, histórico e progresso
data/acervo.sqlite3             criado pela CLI, não versionado
requirements.txt               dependências do projeto (UTF-8)
```

## Requisitos

- **Acervo/CLI:** Python 3.12+ com SQLite compilado com FTS5. Texto e busca usam somente a biblioteca padrão; a importação de PDF exige `pypdf==6.21.4`, sem dependências de IA. Verificado com Python 3.14.4 e SQLite 3.46.1.
- **Classificador:** Python 3.12, GPU NVIDIA com CUDA 12.8 (o `torch` fixado é `2.11.0+cu128` e o router usa `device="cuda"`) e token do Hugging Face com acesso ao modelo `Riupul/laya-multilingual-finetuning-memorix`.
- **Geração:** o cliente usa somente a biblioteca padrão, mas exige um servidor local já iniciado com API Chat Completions e suporte a `response_format.type = json_schema`. O servidor e os pesos do modelo são instalados separadamente; o comando não baixa modelos nem exige o classificador Laya.
- **Biblioteca/revisão:** usa somente a biblioteca padrão e o mesmo arquivo SQLite do acervo; não exige modelo ativo, GPU, token nem instalação de `pypdf` para revisar conteúdo já importado.
- **Estudo/progresso/plano:** usa somente a biblioteca padrão e o mesmo arquivo SQLite. Não exige modelo ativo nem envia respostas para IA. O histórico é anônimo e compartilhado por toda a instalação local, sem perfis de alunos.

## Instalação do classificador

```powershell
python -m venv venv
./venv/Scripts/Activate.ps1
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128
```

Defina o token do Hugging Face no ambiente (o código lê `HF_TOKEN` via `os.getenv`; `.env` não é carregado automaticamente):

```powershell
$env:HF_TOKEN = "hf_..."
```

## Uso do acervo textual

Para usar apenas o acervo, instale o extrator de PDF em um ambiente virtual; as dependências de IA não são necessárias:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pypdf==6.21.4
```

Em Debian/Ubuntu, se a criação do ambiente indicar ausência de `ensurepip`, instale o pacote `python3-venv` correspondente ao seu Python. Execute os comandos seguintes a partir da raiz do repositório, com o ambiente ativado:

```bash
python3 -m backend.src.Memorix ingest material.txt --title "Biologia"
python3 -m backend.src.Memorix ingest apostila.pdf --title "Apostila de Biologia"
python3 -m backend.src.Memorix search "fotossíntese" --limit 5
```

Para escolher o banco, informe a opção global antes do comando:

```bash
python3 -m backend.src.Memorix --db data/outro.sqlite3 ingest material.md
python3 -m backend.src.Memorix --db data/outro.sqlite3 search "divisão celular"
```

- Entrada: texto UTF-8, com ou sem BOM, ou arquivos com extensão `.pdf` (sem distinção de caixa) com camada de texto.
- PDFs protegidos por senha, inválidos ou sem texto extraível são recusados antes da substituição do documento existente. Não há OCR: PDFs somente de imagens precisam ser convertidos previamente. Em PDFs mistos, páginas sem texto extraível são ignoradas.
- Trechos: até 180 palavras, com sobreposição de 30; espaços e quebras de linha são normalizados. No PDF, cada página é dividida separadamente, sem misturar conteúdo ou sobrepor trechos entre páginas. Pela API Python, `chunk_size` e `overlap` são configuráveis.
- A extração de PDF não preserva o layout visual; tabelas e documentos multicoluna podem exigir revisão do texto extraído.
- A fonte é o caminho absoluto resolvido do arquivo. Reimportar esse caminho substitui documento e índice atomicamente, preservando `doc_id`; mover o arquivo cria outra fonte.
- `chunk_id` depende do documento, posição e texto do trecho e, em PDFs, da página: permanece igual na reimportação idêntica, mas não há histórico de versões.
- A busca encontra qualquer termo da consulta, ignora caixa e acentos e ordena por BM25. Não interpreta operadores FTS; não faz expansão semântica, stemming nem remoção de palavras comuns.
- Saída JSON: ingestão retorna `doc_id`, título, fonte e quantidade de trechos; busca retorna os trechos com `doc_id`, `chunk_id`, título, fonte, posição (`ordinal`, a partir de zero), texto, `score` e `page`. `page` é o número físico da página do PDF, a partir de 1 (não o rótulo impresso), ou `null` para texto. Score maior indica melhor posição lexical, não probabilidade nem garantia factual.
- Sem termos correspondentes, retorna `[]`. Falhas de arquivo, texto, parâmetros ou SQLite saem com código 2 e mensagem em stderr.
- O banco contém cópias do material e caminhos locais. Não o versione nem o exponha publicamente; esta CLI não implementa contas ou controle de acesso. Nenhum texto é enviado a serviços externos pelo acervo.
- Bancos criados pela versão anterior são migrados automaticamente ao abrir: os trechos existentes recebem `page = null`, sem alterar texto, IDs ou índice. Não é necessário reimportá-los.

## Geração local de material

Use um servidor compatível, por exemplo [llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/b12110), com um modelo GGUF de instruções. Depois de instalar o runtime, inicie-o em outro terminal:

```bash
llama-server --model /caminho/modelo.gguf --alias local \
  --host 127.0.0.1 --port 8080 --ctx-size 8192 --parallel 1 \
  --n-gpu-layers 0 --log-disable
```

O exemplo executa em CPU e desativa os logs do runtime. A qualidade do modelo afeta diretamente a utilidade do material; validação de JSON e citações não substitui revisão pedagógica.

Com o material já importado no acervo:

```bash
python3 -m backend.src.Memorix generate "fotossíntese" --type flashcards --count 3
python3 -m backend.src.Memorix generate "fotossíntese" --type multipla_escolha --count 2
python3 -m backend.src.Memorix generate "fotossíntese" --type verdadeiro_falso --count 2
python3 -m backend.src.Memorix generate "fotossíntese" --type aula --count 2 --difficulty intermediaria
```

- Tipo e tema são explícitos; a geração não carrega Laya nem usa heurísticas para inferir intenção.
- `--count`: 1–20 itens; em aulas, quantidade de seções. `--difficulty`: `basica`, `intermediaria` ou `avancada`. `--limit` controla os trechos recuperados (padrão 5).
- `--endpoint`: URL completa de Chat Completions (padrão `http://127.0.0.1:8080/v1/chat/completions`); `--model`: identificador servido (padrão `local`); `--timeout`: segundos positivos e finitos (padrão 120).
- Apenas HTTP nos IPs literais `127.0.0.1` ou `[::1]` é aceito. Hosts externos, `localhost`, credenciais, query strings e fragmentos são recusados. Proxies do ambiente e redirecionamentos HTTP são desabilitados; tokens do ambiente não são utilizados.
- O cliente envia tema, títulos e textos recuperados ao servidor local; não envia caminhos de arquivos nem registra prompts/respostas em logs. Configure o próprio servidor para não registrar dados e não encaminhar pedidos a terceiros. O JSON final contém os caminhos locais das fontes; proteja essa saída.
- Sem trechos correspondentes, a geração é bloqueada antes de chamar o modelo. Não há tentativas automáticas, correção silenciosa de respostas ou fallback para conhecimento externo.
- O servidor recebe um schema por tipo e deve retornar exatamente a quantidade pedida. Geração truncada, JSON inválido, campos extras, alternativas repetidas, gabaritos fora dos limites e citações ausentes/inventadas são recusados com código 2, sem conteúdo parcial em stdout.
- Cada citação exige `chunk_id` recuperado e `quote` literal presente naquele trecho; somente espaços da citação são normalizados. `doc_id`, título, fonte e página são associados pelo acervo, nunca aceitos do modelo.
- Saída JSON: `status` (sempre `requires_review`), `kind`, `topic`, `difficulty`, `title` e `items`. Flashcards: `front`/`back`; múltipla escolha: `question`/`options`/`answer_index` (0–3)/`explanation`; V/F: `question` (afirmação)/`answer` (booleano)/`explanation`; aula: `heading`/`content`. Todos os itens incluem `citations`. O modelo não pode alterar o status de revisão; a saída não representa material aprovado.
- **Revisão humana obrigatória:** o sistema verifica estrutura e origem literal das citações, não se a resposta, gabarito, distratores ou explicação são corretos ou sustentados por elas. Uma referência existente não comprova fidelidade semântica. Modelos pequenos podem produzir material pedagogicamente inadequado mesmo passando na validação.
- O comando `generate` não persiste automaticamente pedido ou material: a importação na biblioteca é explícita, conforme a seção seguinte. A busca continua lexical, sem interpretação semântica. Questionários aprovados podem ser respondidos pela CLI; a interface web de estudo ainda não existe.

## Biblioteca de materiais e revisão humana

Use o mesmo banco que contém as fontes citadas. A opção global `--db`, quando necessária, fica antes do comando. Os exemplos abaixo usam o banco padrão `data/acervo.sqlite3`.

Salve a saída de geração e importe o rascunho; o diretório `data/` deve existir antes do redirecionamento:

```bash
mkdir -p data
python3 -m backend.src.Memorix generate "fotossíntese" --type multipla_escolha --count 3 \
  > data/rascunho.json &&
python3 -m backend.src.Memorix material-import data/rascunho.json
```

A importação retorna `material_id` e `version`. Nos exemplos seguintes, substitua `ID` pelo identificador retornado e use a versão atual:

```bash
python3 -m backend.src.Memorix material-show ID
python3 -m backend.src.Memorix material-list --status requires_review --limit 20
python3 -m backend.src.Memorix material-review ID --version 1 --decision approve
```

Para editar um material, exporte somente o envelope editável:

```bash
python3 -m backend.src.Memorix material-show ID --draft > data/revisado.json
# Edite perguntas, respostas ou explicações em data/revisado.json e revise as citações.
python3 -m backend.src.Memorix material-update ID data/revisado.json --version 2
python3 -m backend.src.Memorix material-review ID --version 3 --decision approve
```

- Uma nova importação cria um identificador distinto com estado `requires_review` e versão 1; não há deduplicação de arquivos JSON. O envelope aceito é o de `generate` ou `material-show --draft`, não o registro completo de `material-show`.
- Aprovar ou rejeitar exige estado `requires_review`, versão atual e decisão explícita (`--decision approve` ou `reject`). A decisão incrementa a versão e registra `reviewed_at` em UTC. Uma segunda decisão é recusada até que haja edição.
- Qualquer edição válida, inclusive de material aprovado ou rejeitado, volta a `requires_review`, remove a data da decisão e incrementa a versão. `--version` impede sobrescrita ou aprovação de uma edição que o revisor ainda não viu.
- Na biblioteca, a versão é um contador de concorrência do registro atual, não um arquivo de todas as revisões históricas. As sessões de estudo preservam somente as versões efetivamente utilizadas nelas; mantenha cópias externas se precisar do histórico completo das edições.
- A importação e a edição revalidam estrutura, texto literal e todos os metadados das citações. JSON com aprovação forjada, campos extras ou fonte/página/documento adulterados é recusado. Só os espaços das citações podem ser normalizados.
- A aprovação revalida as fontes dentro da mesma transação SQLite que registra a decisão. A checagem e a gravação não podem ser intercaladas com uma atualização do acervo; erros deixam conteúdo, versão e decisão anteriores intactos.
- `material-show` retorna conteúdo, `material_id`, `version`, `status`, datas UTC e `sources_current`; `material-list` retorna resumos sem `items`, com filtro de estado e limite positivo. A listagem usa criação mais recente primeiro e identificador para desempate.
- **Fontes obsoletas:** consulta e listagem continuam disponíveis, mas indicam `sources_current: false` se um trecho desaparecer, mudar de texto ou tiver metadados alterados. Uma aprovação anterior é preservada como decisão histórica, não como comprovação de fontes atuais. Não use apenas `status: approved` para liberar material ao aluno.
- Uma fonte obsoleta impede importar, editar ou aprovar aquele rascunho até corrigir as referências. Rejeitar continua permitido. `material-show --draft` sempre exporta `requires_review` e não transporta uma aprovação anterior.
- A decisão é humana e local; não comprova correção pedagógica automaticamente. Ainda não há autenticação ou papéis de admin: qualquer pessoa com acesso ao banco/CLI pode revisar. O banco e os JSONs contêm material e caminhos locais; proteja-os e não os versione.

## Estudo de questionários e acurácia

O estudo com correção automática aceita somente `multipla_escolha` e `verdadeiro_falso`, com material aprovado, versão exata e fontes atuais. Flashcards e aulas continuam disponíveis na biblioteca, mas não recebem pontuação automática.

Para um questionário recém-aprovado na versão 2, substitua `ID` pelo material e `SESSAO` pelo `session_id` retornado. Após edições, consulte a versão atual em vez de reutilizar o número do exemplo:

```bash
python3 -m backend.src.Memorix study-start ID --version 2
python3 -m backend.src.Memorix study-show SESSAO
python3 -m backend.src.Memorix study-list --status in_progress --limit 20
```

`study-start` e `study-show` de sessão em andamento retornam metadados e `questions`: somente `item_index` (a partir de zero), pergunta e alternativas quando houver. Gabarito, explicação e citações não são entregues antes do envio.

Crie `data/respostas.json` com uma lista na ordem das questões: por exemplo, `[0, 1, 2]` para um questionário de três questões de múltipla escolha. Cada índice deve ser inteiro entre 0 e 3. Em V/F, use booleanos JSON, como `[true, false]`, nunca strings ou números. A lista deve ter exatamente a quantidade de questões daquela sessão.

```bash
python3 -m backend.src.Memorix study-submit SESSAO data/respostas.json
python3 -m backend.src.Memorix study-show SESSAO
python3 -m backend.src.Memorix study-progress
python3 -m backend.src.Memorix study-progress --material ID
```

- O envio é único e integral: uma sessão passa de `in_progress` para `completed` somente se todas as respostas forem válidas. Entradas inválidas não salvam respostas parciais nem alteram o progresso. Para praticar novamente, inicie outra sessão.
- O resultado concluído contém total de questões, acertos, `accuracy` entre 0 e 1 e feedback por item: resposta enviada, `expected_answer`, `correct`, explicação e citações da versão estudada. A correção compara com o gabarito revisado por uma pessoa; não comprova automaticamente a veracidade do conteúdo.
- Cada sessão congela um snapshot do material aprovado e do gabarito. Resultados concluídos não são recalculados usando uma edição posterior. `material_current` e `sources_current` informam separadamente se a versão continua aprovada/atual e se suas citações ainda correspondem ao acervo.
- Se o material ou suas fontes mudarem durante uma sessão aberta, retomar e enviar são bloqueados. A tentativa continua visível em `study-list` com os indicadores de validade; inicie outra sessão após corrigir/revisar o material. Não há cancelamento automático nem retomada com outro gabarito.
- Iniciar e enviar usam transações SQLite que mantêm as checagens e a gravação indivisíveis. Dois envios concorrentes da mesma sessão não podem produzir dois resultados.
- `study-list` retorna apenas resumos, sem perguntas, respostas, snapshots ou resultados detalhados, inclusive para sessões concluídas. Aceita filtro `in_progress`/`completed`, limite positivo e ordena pela criação mais recente.
- `study-progress` conta somente sessões concluídas. Retorna `completed_sessions`, `answered_items`, `correct_items`, `accuracy` e grupos `by_material` separados por identificador e versão. Cada grupo inclui estatísticas por `item_index`: tentativas, acertos e acurácia.
- A acurácia global é a soma dos acertos dividida pela soma das questões respondidas, não a média simples das porcentagens das sessões. Sem respostas concluídas, `accuracy` é `null`, não zero. Cada nova sessão concluída conta como outra tentativa.
- O progresso inclui tentativas históricas mesmo depois de mudanças nas fontes ou no material. Versões diferentes nunca compartilham gabarito ou estatística por questão; `--material ID` filtra o identificador sem fundir versões.
- As respostas são índices/booleanos, armazenados somente no banco local, sem nomes, contas ou envio a modelos. O progresso reúne quem utilizar essa instalação: não é acompanhamento individual multiusuário. Proteja o banco e os arquivos JSON de respostas.
- Ocultar o gabarito no comando de estudo não constitui controle de acesso: comandos administrativos e acesso direto ao SQLite continuam locais e sem autenticação. Ainda não há repetição espaçada nem correção automática de texto livre.

## Plano local de prática

```bash
python3 -m backend.src.Memorix study-plan
python3 -m backend.src.Memorix study-plan --target 0.8 --limit 5
python3 -m backend.src.Memorix study-plan --material ID
```

O plano consulta o histórico e as fontes em uma única transação de leitura e retorna `target_accuracy` e uma lista ordenada de `tasks`. Não cria sessões, não salva uma agenda e não altera acurácia. Cada tarefa contém `material_id` e `material_version` utilizáveis em `study-start`:

```bash
python3 -m backend.src.Memorix study-start ID --version VERSAO
python3 -m backend.src.Memorix material-show RECURSO
```

Substitua `ID`/`VERSAO` pelos dados da tarefa; `RECURSO` é um identificador de aula ou flashcards indicado em `resources`.

Regras de prioridade:

1. `review_errors`: há questões da versão atual abaixo da meta. A prioridade usa a pior acurácia por questão, mesmo se a média do questionário atingir a meta.
2. `diagnostic`: não há sessões concluídas para essa versão; a acurácia aparece como `null`, não como zero.
3. `consolidate`: todas as questões atingem a meta; a tarefa continua disponível para prática, sem alegar domínio ou agendar revisão espaçada.

Nos empates de revisão, menos tentativas concluídas têm precedência; o identificador desempata prioridades iguais. Na consolidação, a menor acurácia tem precedência, seguida da quantidade de tentativas e do identificador. A ordem não depende de datas estimadas ou geração por IA.

- `--target` é uma meta escolhida pelo usuário, finita, maior que 0 e até 1 (padrão 0.8); não é probabilidade de domínio. Acurácia exatamente igual à meta não conta como questão fraca.
- `--limit` é um inteiro positivo e limita as tarefas depois de excluir materiais inválidos (padrão 5). `--material ID` filtra o questionário, sem impedir a indicação de recursos de outros materiais; identificadores desconhecidos são recusados.
- Só questionários objetivos aprovados e com todas as referências atuais entram no plano. Rascunhos, rejeitados e materiais com citações obsoletas são excluídos; sem elegíveis, `tasks` é `[]`, sem fallback para versões antigas.
- O histórico usado pertence somente ao identificador e à versão atual. Reaprovar uma edição inicia diagnóstico dessa nova versão; tentativas antigas permanecem em `study-progress`, mas não viram desempenho de questões alteradas.
- `weak_items` identifica as questões abaixo da meta, com `item_index`, tentativas, acertos e acurácia. `sources` aponta documento, trecho, título, fonte e página dessas questões; em diagnóstico/consolidação, aponta as fontes do questionário inteiro. O plano não inclui gabaritos, explicações ou citações literais.
- A tarefa recomenda uma nova tentativa do questionário completo, não uma sessão recortada apenas para as questões fracas. Use as questões e fontes indicadas para orientar a revisão anterior à tentativa.
- `resources` indica até três aulas/flashcards aprovados e com fontes atuais que compartilham os mesmos `chunk_id` das fontes em foco. Aulas aparecem antes de flashcards, com identificador para desempate. `shared_chunk_ids` torna a ligação verificável; apenas compartilhar tema ou documento não basta.
- Compartilhar um trecho não comprova relevância semântica ou adequação pedagógica do recurso. Se não há correspondência literal de referência, a lista de recursos fica vazia; não há recomendação inventada ou busca externa.
- O plano é uma fotografia da consulta. Se a biblioteca ou as fontes mudarem depois, `study-start` revalida versão, aprovação e referências; para leitura de recursos, confira também o estado atual retornado por `material-show`.
- As prioridades usam a frequência histórica de acertos dessa instalação, sem janela temporal, perfis individuais ou estimativa de retenção. Este plano é uma lista de prática por acurácia, não um calendário ou algoritmo de repetição espaçada.

## Uso do classificador

O classificador identifica o tipo de material pedido (`flashcards`, `exercicios`, `aula`, `outro`). Execute a partir da raiz do repositório (os módulos usam imports relativos; para scripts, use `python -m`):

```python
# REPL iniciado na raiz do repositório
from backend.src.Memorix.providers.laya_provider import router
from backend.src.Memorix.contracts.questions import CONTENT_TYPE

result = router.predict("Queria criar umas aulas sobre Python", questions=CONTENT_TYPE)
answer = result["answers"]["o que devemos gerar"]
print(answer["choice"], answer["probabilities"])
```

Cuidados com a Laya:

- `criteria` deve ser `dict` ou `list` — `set` é rejeitado; `instructions` é obrigatório.
- `confidence` é a entropia normalizada da distribuição, **não** a probabilidade da escolha. Para decidir, use `probabilities[choice]` com um limiar.
- Evite `preload=True` com vários checkpoints em máquinas com pouca memória (crash nativo sem traceback).

## Roadmap

| # | Goal | Status |
| --- | --- | --- |
| 1 | MVP RAG funcional (questões, flashcards, aulas) | Em andamento |
| 2 | Planejamento de estudo | Em andamento — prioridades por acurácia e recursos rastreáveis pela CLI |
| 3 | Acompanhamento por acurácia | Em andamento — questionários e histórico local pela CLI |
| 4 | App mobile | Futuro |
| 5 | Questões dissertativas | Futuro |

## Testes

Com o extrator de PDF instalado:

```bash
python3 -m unittest discover -s backend/evals -v
```

Os 101 testes cobrem acervo textual/PDF, migração, contratos de geração, citações e metadados inválidos, isolamento de rede, revisão, conflitos de versão, sessões, envio único concorrente, rollback, progresso ponderado, snapshots históricos e prioridades/indicações do plano. Não exigem GPU, token, servidor de modelo nem downloads de pesos; os cenários HTTP usam servidores temporários em loopback. Ainda não há avaliações automáticas de qualidade pedagógica ou fidelidade semântica do RAG.

Verificação manual: CLI executada com `llama.cpp b12110` em CPU e `Qwen/Qwen2.5-1.5B-Instruct-GGUF` (`Q4_K_M`), gerando os quatro formatos a partir de texto e dois flashcards com referência à página 3 de um PDF. Também foram exercitados erros de tema sem evidência, quantidade, timeout, endpoint externo e servidor indisponível. Os artefatos e o servidor usados no smoke são temporários, não acompanham o projeto. A amostra de aula acrescentou uma afirmação não sustentada pela fonte apesar de passar na validação literal; isso confirma a necessidade do status `requires_review`, não uma garantia de qualidade semântica.

Verificação manual da biblioteca: CLI exercitada em processos separados para importar, consultar, exportar, editar, aprovar, rejeitar e filtrar materiais. Também foram observados bloqueio de versão antiga, perda de validade das fontes após reimportação do acervo, recusa de aprovação com fonte obsoleta e rejeição válida desse mesmo material, sem incrementar a versão nas operações recusadas. Os arquivos e bancos do cenário eram temporários e foram removidos.

Verificação manual do estudo: CLI exercitada em processos separados para iniciar/retomar MC e V/F, recusar rascunhos e respostas inválidas, corrigir uma única vez, filtrar tentativas e calcular acurácia ponderada por questão. Dois processos enviando a mesma sessão tiveram um único vencedor. Edições e fontes obsoletas bloquearam sessões abertas sem modificar resultados concluídos; gabaritos e grupos de progresso de versões diferentes permaneceram separados. Os questionários de entrada foram preparados localmente com fontes reais do acervo temporário, sem chamar um LLM neste cenário.

Verificação manual do plano: CLI exercitada com revisão de erros, diagnóstico e consolidação, indicação de aula/flashcards por trecho compartilhado, mudança da meta, filtro e limite. Uma tarefa retornada foi executada por `study-start` e corrigida; planejar não alterou o progresso. Fontes obsoletas saíram do plano, e uma edição reaprovada voltou a diagnóstico sem herdar respostas antigas. Meta não finita, limite inválido, identificador desconhecido e início com a versão antiga foram recusados. O cenário usou banco temporário e materiais curados localmente, sem modelo de IA.
