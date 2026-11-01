# 012 — Variáveis em inglês
Goal: transversal (sem mudar status ou autorização de goal)        Trilha: Padrão        Estado: Concluída

## Objetivo
Padronizar em inglês `snake_case` as variáveis próprias do backend: parâmetros, locais, constantes e atributos internos, inclusive testes e fixtures. Preservar nomes impostos por integração, registros persistidos e conteúdos em português do aluno.

## Critérios de aceitação
- [x] Bindings próprios em código Python e testes têm nomes em inglês; imports, keywords, fixture parametrization e acessos aos atributos acompanham as renomeações.
- [x] SQL, nomes de colunas, chaves JSON/JSONL, valores (`texto`, `sem_mudanca`, etc.), variáveis de ambiente e migração 0001 preservam o contrato.
- [ ] Comportamento com banco não comprovado: 53 testes sem banco passaram, 24 erros de setup por timeout Supabase; humano aceitou explicitamente a ressalva.
- [x] A convenção está registrada no README e nas instruções dos agentes; trabalho pré-existente preservado.

## Fora do escopo
Classes/módulos (incluindo a renomeação em andamento `rastro.py → observabilitiy.py` feita pelo usuário), funções já renomeadas, tradução de texto pedagógico, mudança em schemas/DB ou em dados de rastreabilidade.

## Esclarecer
Resolvido pelo humano: `Aprovar plano`, `Autorizar testes`, `Dispensar nesta tarefa`. A dispensa do `orchestrator` vale só para a tarefa 012; não presumir pin nem revisão por agente.

## Plano
| Passo | Arquivos e contrato |
| --- | --- |
| Traduzir parâmetros, locais, constantes e atributos internos, incluindo `Resultado.resultado` e `ConfigIngestao.estrategia/extrator/rastro_path` | `backend/src/Memorix/{config,ingestion,providers}/` e consumidores |
| Migrar kwargs, chamadas, fixtures e `parametrize` sem mexer nas strings de banco/trace | `backend/api/tests/{conftest,test_ingestao,test_pdf,test_persistence}.py` |
| Registrar convenção e provar comportamento | `README.md`, `.omp/AGENTS.md`, estes registros de tarefa/progresso; `pytest` sem banco e suíte de banco se disponível |

## Evidências preliminares
| O quê | Método | Status |
| --- | --- | --- |
| Sintaxe Python prévia | `python -m compileall -q backend` | Passou |
| Ingestão/PDF sem banco prévios | `pytest backend/api/tests/test_ingestao.py backend/api/tests/test_pdf.py -q -m "not banco"` | Passou: 52 passed, 14 deselected |
| Testes atuais (SHA-256) | `sha256sum` | `test_ingestao.py` 641f8b90d7511228081fd50f22bc76f8d77c0d1a267dc8f1e7ffab11ad4c7cea; `test_pdf.py` 396373244f13b6afa619e324128ef5e3ee051a9d62f98d899440ce75f2f3ac3d; `test_persistence.py` a317ddea11027a2cb99a1b48f5dc1e80fa8763be1ef9d8ac14ec35f55836fd74; `conftest.py` 97973d4abb7d15a720050f37c2e3e3b577f5f1840032f88cca182e874a891838 |

## Evidências após a renomeação
| O quê | Método | Status |
| --- | --- | --- |
| Sintaxe | `./venv/Scripts/python.exe -m compileall -q backend` | Passou |
| Ingestão/chunking/PDF sem banco | `./venv/Scripts/python.exe -m pytest backend/api/tests/test_ingestao.py backend/api/tests/test_pdf.py -q -m "not banco"` | Passou: 52 passed, 14 deselected |
| Configuração sem banco | `./venv/Scripts/python.exe -m pytest backend/api/tests/test_persistence.py::test_database_url_comes_from_env_without_hardcoded_credentials -q` | Passou: 1 passed |
| Suíte completa | `./venv/Scripts/python.exe -m pytest backend/api/tests -q` | Bloqueado para testes com banco: 53 passed, 24 errors no setup `migrated` por timeout TCP no pooler Supabase |
| API real sem banco | `ingest_document(..., source='../outside.txt')` + leitura de JSONL temporário | Passou: rejeita caminho inválido, registra `etapa=ingestao`, `erro=ValueError` sem renomear chaves |
| Rastro append-only | `record_trace` num arquivo temporário | Passou: `etapa`, `resultado`, `extrator`, `status` preservados; não aparecem `stage`, `result`, `extractor` no JSON |
| Contratos textuais | AST antes/depois de dez arquivos Python | Passou: declarações de função/classe preservadas; strings alteradas somente nas dez parametrizações `nome → fixture_name` de pytest |
| Hashes após alteração autorizada | SHA-256 | `test_ingestao.py` bd8af09a90adbb5e062afc0ec5d70bef0ff05bfc760d8ff5cfe63c4e10f86cbb; `test_pdf.py` c58f09e74ca6e26911e1f506390b3f256ddb51c010f29175b099424b178d36a8; `test_persistence.py` 89876f095a11a4dcbf17e2067b91d882c5d0798032ad98d4949f539c4b29d907; `conftest.py` 3525b5e5ead7a272f9a6ace15ad14e26b441b683fcd5fa7037ec348eac4922d3 |

## Decisões
- Alterações locais do usuário permanecerão intactas; o provider `observabilitiy.py` substituiu `rastro.py` depois da tarefa 011, com imports já migrados. Esta tarefa só renomeia seus bindings internos.
- LSP indisponível (sem servidores configurados); usar transformação lexical ciente de Python e inspecionar exceções: chaves textuais externas e nomes de módulos não podem mudar.
- A migração 0001 permanece intacta; dados observáveis continuam em português. Atributos Python internos mudaram por corte limpo (`Resultado.status`, `ConfigIngestao.strategy/extractor/trace_path`), com consumidores migrados e sem aliases.
- A revisão de `orchestrator` foi dispensada nesta tarefa pelo humano. Aceite final literal: `Aceitar com ressalvas` — concluir com testes dependentes do banco não executados por timeout, sem afirmar sucesso desses testes. Nenhum goal teve status/autorização alterado.
