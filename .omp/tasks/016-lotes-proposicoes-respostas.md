# 016 — Lotes por proposição e respostas válidas

Goals:1.5,2,3,6,7. Trilha:IA. Estado:Construir.

## Escopo autorizado

Continuação de backend/IA, sem frontend/mobile. Autorizações013 mantidas: execução contínua sem perguntas/gates intermediários, pin/transporte nativos dispensados, PostgreSQLDEV/TEST separados. Sem novos modelos/downloads, inferência externa, commit/push/deploy.

## Problemas e hipótese

`pipeline/service.py::_validate` usa só o gabarito para deduplicar MC/flashcards: fatos diferentes com o mesmo gabarito são rejeitados; paráfrases com respostas textualmente diferentes passam. Comparação literal de V/F/aula/dissertativa também não identifica paráfrases. Goal1.5 exige dedupe por proposição. Hipótese: impressão digital pelo enunciado mais comparação semântica local entre itens de lotes, sem chamada extra em item único, distingue fato repetido de assunto/resposta iguais. Medir em casos balanceados antes de adotar; não usar apenas o próprio juiz como prova.

`services/study.py::grade_objective` também aceita resposta de MC fora de todas as opções e a persiste como erro, contaminando acurácia/revisão/indicações. Corrigir a fronteira compartilhada; opções válidas conservam comparação atual por trim/casefold. Replay histórico permanece anterior à validação nova, sem apagar tentativas.

## Critérios

- Reproduzir antes: lote distinto com gabarito igual rejeitado; paráfrase repetida aceita; opção inexistente registrada.
- Lotes: comparação por proposição, não por igualdade de gabarito; apenas decisões estruturadas/booleanas válidas; repetição rejeita o lote como hoje, sem persistência parcial ou preenchimento inventado.
- Avaliar casos balanceados dos cinco tipos, rotulados independentemente; mesmos exemplos antes/depois e resultados negativos preservados. Sem alterar20casos originais de retrieval/geração ou seus labels/gate.
- MC inválida retorna422, sem consumir request_id e sem alterar histórico/acurácia/plano/recomendações; escolha válida aceita, replay mantido.
- Suíte isolada e smoke real da API/modelos, rastros sem conteúdo do aluno, teste primeiro e hashes medidos antes da implementação.

## Ownership e prova

Main: providers/generation.py,pipeline/service.py,services/study.py, testes/regressões, casos/harness de avaliação, documentação e infraestrutura/GPU. Revisores só leitura, sem testes/build/lint/formatters/inferência. Contratos e labels serão revistos em fatias independentes após os casos estarem definidos; ninguém além do Main usa GPU. LSP consultado: nenhum servidor configurado; referências literais verificadas antes dos reparos.

Baseline geral preservado da013:8/12positivos aprovados,8/8fora recusados,29/38claims apoiadas,relevância10/20. A016 não pode apresentar avaliação de duplicatas como melhora geral desses números.

## Teste primeiro e baseline congelado

RED6 observado antes de alterar produto:3falhas IA (gabarito igual rejeitado; paráfrase e veredito inválido aceitos) e3HTTP (opção inexistente/em branco e nova tentativa inválida após replay legado retornavam201). PostgreSQLTESTE,2,52s; nenhum dado real de aluno. Hashes registrados antes da implementação:

| Arquivo | SHA-256 |
| --- | --- |
| `test_ai_duplicate_propositions.py` | `06751e6cc3b1aaa07f1468a05be6788c940ffbd83c664e48f0053a71c5a2a54f` |
| `test_study_choice_boundary.py` | `d4cd42fa182cf94c9bdc684f1d57cb254a7f397f222f856dd736a41717c5bfc2` |
| `generation_duplicates.jsonl` | `bebe66b5bddda134b55777eb94b044fbb0a23104437f8d16b19b9d228814278e` |

DuplicateLabels016(reviewer nativo) revisou24casos/12duplicados/12distintos, incluindo rubricas parcialmente sobrepostas e duplicata apenas entre itens posteriores. Labels/rationales confirmados antes da medição. Amostra pequena/sintética com conceitos repetidos, sem garantia externa. ChoiceContract016(orchestrator) confirmou guard na correção compartilhada, replay antes dele e efeitos derivados somente de tentativas persistidas; sem testes/inferência por esses revisores.
