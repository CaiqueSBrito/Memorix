# 014 — Continuação backend/IA: objetivos e ordem dos flashcards

Goal: 1.3,1.5,2,3,5,6,7. Trilha: IA. Estado: Concluída — incremento de backend, verificação e medições; qualidade geral de IA não aceita.

## Pedido e escopo

Pedido reiterado: continuar todos os goals de backend e IA; frontend fica para depois. Mantidas as exceções da013: execução sem novas perguntas/gates, subagentes nativos/pin dispensado, banco local isolado, nenhum envio de dados de aluno a terceiros. Sem novos modelos/downloads, frontend/mobile, push ou deploy.

## Baseline

151 testes aprovados na013; `generation_final_013.json`:20casos,8/12positivos aprovados pelo validador,8/8negativos recusados,29/38afirmações apoiadas e relevância local10/20. Os números não equivalem a aceite geral. Falhas conhecidas ret10(objetivos omitidos),ret11(objetivo trocado/distrator ambíguo),ret02(fonte geral insuficiente).

## Plano e critérios

1. Medir seleção de contexto orientada ao pedido depois do gate, preservando decisão e labels originais; não incorporar sem ganho nas mesmas fontes/casos. Comparar variantes de retrieval isoladas para conferir C-ret, sem atribuir ao lexical o ganho do reranker.
2. Garantir no backend que a autoavaliação de flashcard acontece depois de revelar o verso daquele item. Outro aluno/item não autoriza a avaliação; repetir reveal é idempotente, não registra tentativa. Mudança de estado usa POST/reveal, com cutover dos consumidores existentes; GET não muda estado. Não atestar que o aluno leu/compreendeu o verso.
3. Teste primeiro da ordem, migração aditiva preservando acervo/histórico, suíte no memorix_test e smoke HTTP real no DEV. Reavaliar mudanças IA com os mesmos20casos e revisar exemplos, sem esconder falhas ou transformar âncora excluída em tema proibido.

## Ownership

Main: testes primeiro, IA/medição, integração e documentação. `GoalAcceptanceCheck`(orchestrator): revisão finita de critérios. Especialista pedagógico bloqueado429; `PedagogyObjectiveFallback`(reviewer) faz revisão orientativa das amostras existentes, explicitamente distinta de aceite humano/modelo original. Não executar inferência concorrente na GPU6GiB.

## Evidências em andamento

- Revisão encontrou ordem reveal→self_assessment apenas sugerida, não exigida pelo backend; gap consumer-visible.
- Revisão encontrou C-ret lexical não provado isoladamente: denso4/12,híbrido5/12; comparar denso+reranker antes de atribuir ganho lexical.
- Experimentos `selection_*_014.json` preservados; candidatos pós-gate apenas reranqueados não melhoraram cobertura, pool ampliado90 chegou9/12 mas ret10 continua ausente. Nenhum experimento adotado sem prova end-to-end.

## Backend — evidência obtida

- RED observado antes da implementação: `test_study_flashcards.py` esperava409 antes de revelar, recebeu201 com gabarito e tentativa persistida. Regressão fortalecida cobre outro aluno/item,GET405,repetição da revelação,idempotência de resposta e replay legado que não inventa revelação.
- Implementação pelo owner: `FlashcardReveal` e migração0005 com PK(content_id,item_id), FKconteúdo/cascade e RLS; `POST /reveal` usa insert-on-conflict. Respostas novas sem registro daquele item retornam409; replay histórico checado antes do pré-requisito. Nenhuma alteração no acervo/vetores.
- Migração DEV executada0004→0005. HTTP real `flashcard_order_http_014.json` reutilizou flashcard gerado pelo modelo na013:409antes,history inalterado,GET405,outroaluno404,POST200/repetido200sem tentativa,rating201/replay200depois. Duas sessões sintéticas novas revogadas.
- Suíte final após remover experimento rejeitado: **151passed,1warning,32,50s**, banco TESTE separado. Inclui replay legado, migrações upgrade/downgrade; testes nunca executados no DEV. SHAfinal do teste `566bfb9a354af2e3ef1776ecdb36fc0e230f21c3d961616f8835fe37fb28880d`.
- Revisão pedagógica fallback: sequência operacional adequada, sem impedimento nessa fatia; evento confirmado antes da resposta HTTP registra processamento, não recebimento,leitura,compreensão ou evocação. Autoavaliação permanece autodeclarada e fora da acurácia objetiva. Não é aceite global/humano nem execução do especialista bloqueado.

## IA — medições

- Quatro variantes e100consultas quentes por variante em `retrieval_four_variants_014.json`: denso4/12,híbrido5/12,denso+reranker6/12,híbrido+reranker8/12; um span ativo. Comreranker fixo, lexical ganha2casos(ret05/ret06),nenhum perdido,FARleave-one-out0,p95quente454→468ms. `retrieval_decision_014.json` registraC-ret isolado; manterretrieval/gate atuais.
- Seleção objetiva pós-gate e união de buscas não corrigiram ret10; pool90 melhora cobertura para9/12, mas não há prova suficiente de qualidade/latência para adotar complexidade. Artefatos preservados, nenhum branch experimental de retrieval no produto.
- Experimento concluído `generation_evidence_first_014.json`: mesma única mudança de ordem de campos, mesmos20casos/labels/modelos/query/gate/fontes. Entregas positivas8→6de12; relevância local10→9de20; recusas8/8preservadas. Claims apoiadas29/38→29/36: razão condicional maior não compensa menor cobertura e relevância. **Rejeitado**, schema/runtime restaurados exatamente para `grounded-pt-v5`/SHA `5a664542413203d84a440b307477d20e7fe1a928763011a41f69b24c21914db3`. Sem adotar regressão por passar schema.

## Prova final e revisão

- `fresh_flashcard_http_014.json`: geração NOVA por modelos locais reais201/44,54s,verso inicialmente privado; rating409,POSTreveal200,ratingnegativo201,persistência200,sessão revogada. `fresh_flashcard_trace_014.json`: retrieval/rerank/gate/geração/validação/resposta presentes, gate0ms observado,2/2claims apoiadas e pedido bruto ausente. API reiniciada com schema estável e nova regra de revelação, `/health`ok. Quatro sessões sintéticas desta continuação foram revogadas.
- Revisão de completude peloorchestrator identificou e fechou duas lacunas finitas: ordem operacional dos flashcards e evidência isolada do lexical. Sem outra feature backend explicitamente ausente demonstrada; isso não equivale a qualidade geral atingida.
- Revisão pedagógica fallback das8amostras antigas: ret01/05/07 adequados,ret04 e12 com cobertura restrita,ret02 correto cientificamente mas insuficientemente apoiado pela tabela citada,ret10 omite tortura/pena de morte,ret11 troca atividades por origem e tem distratores sobrepostos. Falhas permanecem visíveis; nenhuma mudança de label ou aceite global.
- Manifest final `backend/evals/results/verification_014.json` registra comandos/resultados,hashes, migração,HTTP e decisão de rejeitar candidato. SQL confirmou0005 e17documentos/7.158chunks/7.158vetores/1span preservados; antes da geração nova havia1revelação sintética.
- Nenhum frontend/mobile,providerremoto,downloadnovo,commit,push ou deploy. Produção,Supabase,curadoria integral e requisitos jurídicos não comprovados. Goals de qualidade continuam em andamento; não foram encerrados pelo autorrelato do modelo.

