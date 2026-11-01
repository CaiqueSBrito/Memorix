# 011 — Funções em inglês
Goal: transversal (sem alterar autorização/status de goal)        Trilha: Padrão        Estado: Concluída

## Objetivo
Usar nomes de funções em inglês (`snake_case`) em todo o código Python próprio, incluindo testes, fixtures e helpers; registrar a convenção para funções futuras. Não traduzir textos voltados ao usuário, nomes de arquivos, dados persistidos ou identificadores de APIs externas.

## Critérios de aceitação
- [x] Todas as declarações `def`/`async def` do backend e dos testes têm nomes em inglês; hooks exigidos por pytest/Alembic preservados.
- [x] Imports, chamadas, referências e injeção de fixtures correspondem aos nomes novos, sem aliases legados.
- [ ] Suíte completa comprova todos os comportamentos (não demonstrado: testes com banco bloqueados por timeout; humano aceitou explicitamente esta ressalva). Convenção documentada e 53 testes sem banco passaram.
- [x] Mudanças pré-existentes no checkout foram preservadas.

## Fora do escopo
Tradução de parâmetros/variáveis/classes, texto de interface, conteúdo pedagógico, colunas do banco, valores de `source_type`, eventos e campos JSONL, nomes de arquivos, migração congelada 0001 e regras do pipeline.

## Esclarecer
Resolvido: humano aprovou o plano e autorizou mudar nomes/imports/fixtures dos testes 002/004/005, preservando as asserções e registrando novos hashes.

## Plano
| Passo | Quem | Arquivos |
| --- | --- | --- |
| Renomear funções portuguesas e referências | implementação coordenada | `backend/src/Memorix/ingestion/{canonical,chunking,ingest,pdf}.py`, `providers/rastro.py`, testes e `conftest.py` |
| Reconciliar renomeação pré-existente `chunkar → chunking` | implementação coordenada | `backend/api/tests/test_ingestao.py` (import corrigido para `chunking`) |
| Registrar regra `snake_case` em inglês | implementação coordenada | `README.md` e `.omp/AGENTS.md`, preservando mudanças locais existentes |
| Provar contrato e registrar resultado | implementação coordenada | suíte `backend/api/tests/`, esta tarefa, `.omp/progress/progresso.md` |

## Evidências preliminares
| O quê | Método | Status |
| --- | --- | --- |
| Compilação Python atual | `python -m compileall -q backend` | Passou |
| Coleta do teste de ingestão atual | `pytest backend/api/tests/test_ingestao.py -q -m "not banco and not hf"` | Falhou: importa `chunkar` enquanto código local já expõe `chunking` |
| Hashes atuais dos testes | SHA-256 | `test_ingestao.py` 935984d0eb8b94995fbd7118787b8f295e46772b31782a16093780471dc21cab; `test_pdf.py` 3084a3bd4ef593899b0bdc96c2e9843e76f8b678acea6ccfbd09761f67d700be; `test_persistence.py` 38ddb0586eed33f86b0cdca4a2fddae09c4d6fe62a6e245c499cf7df401be828; `conftest.py` 851774e14e581c85ea5da90d3d6f825ec0b1d9f370e3da1974568574467fc3b7 |

## Evidências após a renomeação
| O quê | Método | Status |
| --- | --- | --- |
| Declarações de funções e ausência de nomes legados | AST de todos os `.py` próprios + procura de referências | Passou |
| Sintaxe do backend | `./venv/Scripts/python.exe -m compileall -q backend` | Passou |
| Ingestão/PDF sem banco | `./venv/Scripts/python.exe -m pytest backend/api/tests/test_ingestao.py backend/api/tests/test_pdf.py -q -m "not banco"` | Passou: 52 passed, 14 deselected |
| Configuração sem banco | `./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py::test_database_url_comes_from_env_without_hardcoded_credentials -q` | Passou: 1 passed |
| Suíte completa | conexão Supabase no setup da fixture `migrated` | Bloqueado: timeout TCP no pooler; não há resultado atual dos testes com banco |
| Hashes novos | SHA-256 | `test_ingestao.py` 89bdd405b89247e2d33e1d3f814b204432a682b1ac528fdc7400cc618714541a; `test_pdf.py` 396373244f13b6afa619e324128ef5e3ee051a9d62f98d899440ce75f2f3ac3d; `test_persistence.py` a317ddea11027a2cb99a1b48f5dc1e80fa8763be1ef9d8ac14ec35f55836fd74; `conftest.py` 97973d4abb7d15a720050f37c2e3e3b577f5f1840032f88cca182e874a891838 |

## Decisões e conflitos
- `README.md`, `entities/documents.py`, `chunking.py` e `ingest.py` já têm alterações locais do usuário; preservá-las, especialmente `chunking` e seu callsite.
- Antes de acionar `orchestrator`, a sessão principal precisa executar `/session pin caique.ds.brito@gmail.com` conforme `.omp/AGENTS.md`; o comando da sessão não está disponível nas ferramentas desta API. Não tratar afinidade como fixada sem executá-lo.
- Gate de plano/testes: respostas literais do humano: `Aprovar plano`; `Autorizar testes`.
- Revisão de `orchestrator` não executada: não houve acesso ao comando `/session pin` da sessão principal nesta API; não afirmar revisão nem afinidade.
- Aceite final do humano: `Aceitar com ressalvas` — autorizou concluir sem resultado atual dos testes com banco e dispensou a revisão do `orchestrator` nesta tarefa. Nenhum status/autorização de goal foi alterado.
