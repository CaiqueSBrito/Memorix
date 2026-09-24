# Memorix

Sistema educacional web, em português, que usa IA (RAG sobre um acervo próprio) para o aluno criar e estudar material a partir de conteúdo curado.

> **Estado:** estágio inicial. Hoje existe só o esqueleto do backend e o classificador de intenção do pedido. Acervo, RAG, geração, persistência, contas e interface web ainda não foram implementados.

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
  → RAG gera o conteúdo a partir do acervo
  → aluno responde → acurácia por questão
  → plano de estudo + indicação de material
  → volta ao estudo
```

Princípios:

- **Fidelidade ao acervo** — todo conteúdo gerado é sustentado por trechos do acervo; sem fonte, não é entregue como fato.
- **Rastreabilidade** — todo conteúdo aponta para os trechos (`doc_id`, `chunk_id`) que o sustentam.
- **Base pedagógica** — prática de recuperação e repetição espaçada.
- **Privacidade (LGPD)** — o público inclui menores de idade: coleta mínima, sem dados do aluno em logs e sem envio a terceiros.

## Pipeline RAG (planejado)

```text
pedido do aluno
  → pedagogical_understand   intenção: tema, tipo, quantidade, dificuldade
      └ node classifier      flashcard | questionário (MC | V/F) | aula
  → retrieval → reranking
  → generation_adapter       prompt e schema por tipo de conteúdo
  → geração (LLM)
  → resposta
```

Só o node classifier tem código hoje.

## Estrutura

```text
backend/
  src/Memorix/
    config/config.py          ConfigLaya: modelo e idioma do classificador
    contracts/questions.py    LayaChoiceQuestion + pergunta CONTENT_TYPE
    providers/laya_provider.py  Router da Laya (classificação do pedido)
    providers/tokenizer.py    tokenizer BERTimbau (neuralmind/bert-base-portuguese-cased)
    ingestion/  pipeline/  generation_adapter/  entities/  multi-agent/   (vazios)
  api/                        (vazio)
  evals/                      (vazio)
  logs/                       (não versionado)
requirements.txt
```

## Requisitos

- Python 3.12
- GPU NVIDIA com CUDA 12.8 (o `torch` fixado é `2.11.0+cu128` e o router usa `device="cuda"`)
- Token do Hugging Face com acesso ao modelo `Riupul/laya-multilingual-finetuning-memorix`

## Instalação

```powershell
python -m venv venv
./venv/Scripts/Activate.ps1
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128
```

Defina o token do Hugging Face no ambiente (o código lê `HF_TOKEN` via `os.getenv`; `.env` não é carregado automaticamente):

```powershell
$env:HF_TOKEN = "hf_..."
```

## Uso

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
| 2 | Planejamento de estudo | Planejado |
| 3 | Acompanhamento por acurácia | Planejado |
| 4 | App mobile | Futuro |
| 5 | Questões dissertativas | Futuro |

## Testes

Ainda não há testes nem evals. `pytest` está em `requirements.txt`; os casos de avaliação do RAG vão morar em `backend/evals/`.
