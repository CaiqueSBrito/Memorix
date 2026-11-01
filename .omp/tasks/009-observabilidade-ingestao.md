# 009 — Observabilidade básica da ingestão

Goal: 7 — Observabilidade ponta a ponta        Trilha: Padrão        Estado: Concluída (com ressalva)

## Objetivo

Tornar o rastro JSONL da ingestão de texto/PDF consultável por `trace_id` e agregável, preservando a correlação de extração, chunking e persistência inclusive quando uma etapa falha. Preparar o mesmo formato para as etapas futuras de retrieval e geração sem implementá-las antecipadamente.

## Critérios de aceitação

- [x] Consultar um `trace_id` retorna só os registros daquela execução, em ordem; identificador inexistente retorna lista vazia.
- [x] Agregar por etapa retorna contagem, p95 de `duracao_ms` (percentil nearest-rank), taxa de erro; eventos futuros de geração, quando presentes, também somam tokens de entrada/saída e custo estimado sem inventar valores ausentes.
- [x] Ingestão de texto/PDF mantém `trace_id` comum de extração à persistência (fluxo PDF existente); falha em chunking deixa evento de erro na etapa, sem duplicar sucesso ou registrar conteúdo/segredo. Sucesso completo de PDF não reexecutado nesta sessão sem banco.
- [x] Nenhuma dependência nova, serviço, dados do aluno, chamada a terceiros ou alteração no esquema do banco.

## Fora do escopo

Retrieval, geração, conjunto de evals 006, métricas de qualidade E2E 010, custo/token em requisição inexistente, ferramenta dedicada e scoring online. Goal 7 permanece em andamento, não concluído, até essas dependências existirem.

## Decisões e bloqueios

Humano (2026-10-14): “logger básico já rastreando a ingestão ponta a ponta, e preparar a base para o goal 7 que vai ser algo implementado ao passo que outros goals são feitos”. A 012 renomeia bindings nos arquivos de ingestão; suas alterações foram preservadas. `/session pin` não está disponível pela API desta sessão; o humano aprovou plano e dispensou revisão por agente somente nesta tarefa, autorizou teste congelado e aceitou a 009 com ressalva de 14 testes com banco não executados. O Goal 7 não está concluído; 006–008 e 010 permanecem bloqueadas.

## Plano

1. Escrever teste de consulta/agregação com rastros reais emitidos pela porta existente; registrar falha anterior e hash, pedir autorização.
2. Implementar leitura/agregação por streaming no provider atual, sem persistência extra nem framework.
3. Cobrir falha do chunking na ingestão e confirmar correlação também no fluxo de PDF; preservar o contrato JSONL existente.
4. Rodar cenário e testes específicos; registrar evidência e atualizar goal/progresso/README conforme resultado, sem declarar Goal 7 concluído.

## Teste primeiro

`backend/api/tests/test_observability.py`: SHA-256 `3b50c1d175a8aadcf590352892d26719f81cad820691344338df1b542deb098e` antes e depois. Consulta/métricas falharam antes da implementação na coleta por `ImportError: cannot import name 'read_trace'` do provider existente; o caso de chunking também permanecia indisponível pela mesma falta da interface. Humano autorizou implementar sem tocar no teste.

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| Consulta por trace_id, p95 nearest-rank, taxa, tokens/custo sintéticos | `python -m pytest backend/api/tests/test_observability.py -q` | Passou: 2/2 |
| Falha real na ingestão de texto antes do banco | Mesmo teste com chunking lançando `ValueError` | Passou: eventos `chunking` e `ingestao` ligados, sem conteúdo |
| Falha real de extração PDF + consulta/agregação | `ingest_pdf` com PDF ausente e `read_trace`/`summarize_traces` | Passou: 1 erro em `extracao`, mesmo trace consultado, taxa de erro 1,0 |
| Regressão offline | `pytest test_ingestao.py test_pdf.py test_observability.py -q -m "not banco"` | Passou: 54; 14 casos com banco não executados |
| PDF e persistência com banco nesta sessão | Não executado (conexão Supabase registrou timeout na 012; não revalidado aqui) | Não executado |
