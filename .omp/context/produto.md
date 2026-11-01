# Contexto do produto — Memorix

Documento vivo. O escopo cresce com o desenvolvimento; toda entrada ou mudança de escopo vem do humano e é registrada em **Histórico de escopo**. O que não está aqui não é requisito.

## O que é

Sistema educacional web, em português, que usa IA (RAG sobre um acervo próprio) para o **aluno**:

1. **Criar formulários** — questionários de múltipla escolha e verdadeiro/falso.
2. **Criar aulas.**
3. **Criar flashcards.**
4. **Planejar o estudo** com base na acurácia das respostas dele.
5. **Ser acompanhado** e receber **indicação de material** do acervo conforme o desempenho.

## Papéis

| Papel | O que faz |
| --- | --- |
| Aluno | cria formulários, aulas e flashcards; estuda e responde; recebe plano e indicações. Inclui menores de idade. |
| Admin | alimenta o acervo com material (PDF e texto). Inicialmente, o único que envia material. |

## Ciclo central

```text
Admin envia material (PDF/texto) → acervo
  → aluno pede formulário, aula ou flashcard
  → RAG gera o conteúdo a partir do acervo
  → aluno estuda e responde
  → acerto por questão → acurácia
  → planejamento: o que revisar e quando
  → acompanhamento + indicação de material do acervo
  → volta ao estudo
```

O valor do produto está no ciclo fechado: cada resposta do aluno muda o que ele estuda a seguir.

## Vocabulário

| Termo | Significado |
| --- | --- |
| Acervo | conjunto de materiais mantido pelo admin; única fonte do RAG e das indicações |
| Material | documento do acervo (PDF ou texto); tem `doc_id` |
| Trecho | pedaço do material recuperável pelo RAG; tem `chunk_id` |
| Formulário | conjunto de questões criado pelo aluno para responder |
| Questão | item de múltipla escolha ou V/F, ligado aos trechos que o sustentam |
| Aula | conteúdo explicativo gerado a partir do acervo |
| Flashcard | par pergunta/resposta para prática de recuperação |
| Resposta | o que o aluno respondeu a uma questão ou flashcard, com data |
| Acurácia | acerto objetivo por questão MC/V-F; autoavaliação de flashcards e rubrica dissertativa são indicadores separados |
| Plano de estudo | o que revisar e quando, derivado da acurácia |
| Indicação | material do acervo sugerido ao aluno, com o motivo |

## Requisitos transversais

- **Fidelidade ao acervo.** Todo conteúdo gerado é sustentado por trechos do acervo; sem fonte, não é entregue como fato.
- **Rastreabilidade.** Todo conteúdo gerado aponta para seus trechos (`.omp/instructions/rag-rastreabilidade.md`); todo plano e toda indicação apontam para as respostas/acurácia que os motivaram.
- **Base pedagógica.** Planejamento e flashcards seguem prática de recuperação e repetição espaçada; avaliação alinhada a objetivos de aprendizagem (lentes do `pedagogy-specialist`).
- **Teste primeiro** em toda feature (`.omp/instructions/teste-primeiro.md`).
- **Menores de idade (LGPD, art. 14).** Dados de crianças e adolescentes exigem tratamento no melhor interesse deles; dados de crianças exigem consentimento específico de pelo menos um dos pais ou responsável. Coletar o mínimo, nunca copiar dados do aluno para logs, nunca enviar a terceiros (inclui provider de IA) sem decisão do humano. Confirmar com assessoria jurídica antes de lançar.
- **Idioma:** somente português.

## Pipeline RAG (backend local implementado; qualidade em avaliação)

Ingestão PDF/texto, canonicalização e chunking persistem documentos/trechos; indexação local BGE-M3 de 1.024 dimensões atualiza vetores. A migração `0002` adiciona vetores e FTS `pt_unaccent`; `0003` adiciona contas e estudo; `0004` exclui intervalos em revisão por SHA-256/offset. O PostgreSQL local isolado da tarefa 013 tem 17 PDFs e 7.158 trechos indexados. O Supabase original permanece separado e rejeita o tenant/usuário configurado.

```text
pedido autenticado
  → pedagogical_understand: tipo explícito ou Laya; ambiguidade → esclarecimento
  → embedding da consulta → retrieval denso + FTS/RRF
  → reranking BGE local → gate de suficiência
  → generation_adapter: schema/prompt por tipo, contexto com referências
  → Ollama local → validação estrutural/proveniência/afirmações
  → conteúdo validado persistido por aluno, ou erro/recusa sem conteúdo
  → resposta → histórico/acurácia → revisão/indicação de material
```

- Laya escolhido pelo humano: `Riupul/laya-multilingual-finetuning-memorix`, revisão fixa, carregamento sob demanda sem preload. Foi medido em 20 pedidos, com 17 acertos; o limiar usa `probabilities[choice]`, não `confidence` (entropia).
- Rótulos Laya: `flashcards`, `exercicios`, `aula`, `outro`. Não representam classificação multilabel nem distinguem automaticamente todos os subtipos. Pedido que não determine tipo suficiente exige esclarecimento; tipo explícito da API é aceito sem fingir classificação do texto.
- Tipos da API: `multiple_choice`, `true_false`, `flashcards`, `lesson`, `essay`.
- Sem suporte suficiente → recusa, sem geração. Saída inválida não vira conteúdo estudável. Citações/IDs sozinhos não são prova de correção: há verificação adicional de afirmações, ainda sujeita a limites do modelo/da fonte.
- Modelos e geração locais; sem envio de dados do aluno a APIs. `multiagent` não é necessário para o fluxo implementado: geração e validação local, sem criar coordenação especulativa.
- Cada etapa deixa rastro mínimo sem copiar prompt/resposta do aluno. Configuração por modelo/revisão/chunking/FTS, sem `index_version`, conforme decisão humana da 003.
- Aulas selecionam fontes por relevância e as apresentam em ordem documental; conteúdo parcial precisa de aviso. Questões preservam gabarito/rubrica privados. Flashcards exigem `POST /reveal` antes de nova autoavaliação: registro por conteúdo/item, sem tentativa. Ele comprova processamento pelo servidor, não recebimento/leitura/aprendizagem. Falta de revelação retorna409; reenvios históricos continuam idempotentes. GET antigo foi removido.

### Avaliação e limites

Retrieval, classificação e geração são avaliados separadamente em `backend/evals/`; registros reais em `backend/evals/results/`. Baselines e regressões da 013 não substituem metas/aceite humano. Juiz LLM é complementar às checagens determinísticas e à revisão pedagógica.

- Retrieval: denso→híbrido→híbrido/reranker,100consultas quentes por variante; recall@5 4/12→5/12→9/12, p95 quente469ms. O ajuste antigo ao maior negativo tinha FAR leave-one-out1/8. Calibrador corrigido usa ambas as classes e margem, fold só nos outros19: FAR0/8 e FRR0/12, limiar `-1.067626953125`. Evidência limitada à amostra, sem generalização garantida.
- O corpus não foi inteiramente auditado cientificamente. Um trecho sobre cianobactérias contém erro na própria fonte; o intervalo identificado foi posto em quarentena administrativa no banco local. Filtros dense/FTS e conteúdo anterior respeitam a exclusão; a correção editorial e a revisão científica integral continuam pendentes.
- O `pedagogy-specialist` configurado não executou nesta sessão por limite 429. Um revisor nativo com as mesmas lentes fornece revisão orientativa substituta, explicitamente distinguida de execução do especialista original e de aceite humano.
- Avaliação final de geração:8/12positivos passam validação,4rejeitados,8/8fora recusados;29/38afirmações apoiadas pelo juiz e relevância combinada10/20. Validador ainda erra objetivos (ret10/ret11). Implementação executável não é aceite de qualidade; juiz local, curadoria parcial e amostras úteis não permitem declarar todos os goals concluídos.

### Estudo, contas e consentimento

- HTTP API implementa cadastro/login/logout, roles aluno/admin, isolamento dos conteúdos/respostas e sessões com token opaco revogável. Papéis não são escolhidos pelo cadastro público.
- Adulto declara maioridade. Menor só cadastra com convite único vinculado ao e-mail, emitido pelo admin após verificar o responsável **fora do sistema**. Guardam-se referências mínimas da verificação, não documentos pessoais; não é verificação automática de idade nem conformidade jurídica comprovada.
- MC/V-F: acerto por gabarito; primeira tentativa/revisões distintas. Flashcards: autoavaliação separada. Dissertativas: dois critérios factuais/rubrica, crédito com evidência literal do aluno, soma e feedback compostos pelo servidor; nota fora da acurácia objetiva. Julgamento semântico de objetivo/premissa não exige inventar citação factual.
- Histórico e idempotência por requisição; plano inicial usa sequência de acertos e intervalos fixos 1/3/7/14 dias, erro reinicia. Indicações apontam às respostas e às fontes do acervo que motivaram a revisão.
- Web/mobile, notificações e validação científica de um algoritmo adaptativo não foram implementados.

## Estado técnico atual

Backend/API implementados na013 e reforçados nas014/015: persistência/ingestão,retrieval/gate,cinco tipos,contas/consentimento,respostas,revisão/indicações,curadoria e observabilidade. **155testes passaram** no PostgreSQL isolado. Na015, captura do benchmark deixa de registrar gerações ordinárias posteriores; feedback de nota zero preserva frase incorreta e sua associação ao critério na API/histórico. Provas reais e hashes em `verification_015.json`; modelos/gate/prompt de geração preservados. Decomposição de objetivos sem ganho demonstrado não foi adotada. Qualidade geral da IA não aceita; web/mobile continuam adiados.

## Goals

Roadmap, status e autorização de execução: `.omp/goals/`.

## Em aberto

- Faixa etária mínima, procedimento verificável de consentimento/retensão e avaliação jurídica precisam ser confirmados antes do lançamento; o fluxo administrativo externo aprovado para desenvolvimento não resolve essas obrigações.
- Metas/aceite de qualidade e curadoria do acervo dependem da evidência registrada na 013. Frontend web/mobile ficam para etapa posterior por decisão do humano.

## Histórico de escopo

| Data | Mudança | Origem |
| --- | --- | --- |
| 2026-09-23 | Escopo inicial: formulários, aulas, flashcards, planejamento por acurácia, acompanhamento e indicação de material | humano |
| 2026-09-23 | Aluno cria o conteúdo; admin envia material (PDF/texto) para acervo próprio; público inclui menores; web primeiro; questões MC e V/F; acurácia por acerto por questão; só português. Mobile e dissertativa viram goals futuros. | humano |
| 2026-09-23 | Goals definidos: 1 MVP RAG (questões, flashcards, aulas), 2 planejamento de estudo, 3 acompanhamento por acurácia; mobile e dissertativa como futuros. | humano |
| 2026-09-23 | Pipeline RAG de consulta definido (planejamento): input → pedagogical_understand → retrieval → reranking → multiagent → generation_adapter → geração. | humano |
| 2026-09-23 | `laya` definido como node classifier do `pedagogical_understand`: flashcard, questionário (MC/V/F) ou aula. | humano |
| 2026-09-23 | `laya`: baixa confiança → perguntar ao aluno; pedido com vários tipos → multi-rótulo. | humano |
| 2026-09-23 | Classifier do `pedagogical_understand` troca `laya` por zero-shot `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (sem fine-tuning); `laya` fica como opção futura com dados reais. | humano |
| 2026-10-13 | Decisão atual: o classificador no código será Laya com o checkpoint fine-tuned já configurado; substitui a escolha anterior de mDeBERTa zero-shot. A classificação ainda não está integrada ao fluxo; medir antes de definir o limiar. | humano |
| 2026-10-31 | Humano pediu todos os goals de backend/IA, adiando frontend/mobile; aprovou execução contínua, PostgreSQL local isolado, especialistas nativos sem pin nesta solicitação, consentimento por convite admin após verificação externa e regras iniciais de acurácia/revisão. Posteriormente determinou executar sem novas perguntas, escolhendo opções conservadoras. Detalhes/evidências na tarefa 013. | humano |
