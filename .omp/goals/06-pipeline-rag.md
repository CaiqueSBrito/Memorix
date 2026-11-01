# Goal 6 — Pipeline RAG

Desenhar e validar a arquitetura antes de implementá-la; execução backend/IA autorizada pelo humano em 2026-10-31 na tarefa [013](../tasks/013-backend-ia-todos-goals.md), com frontend adiado.

Fluxo implementado: entrada autenticada → compreensão por tipo explícito/Laya → embedding → busca densa/FTS/RRF → reranking → gate → prompt/schema → Ollama local → validação estrutural/fontes, revisão pedagógica e verificação factual separadas → persistência/resposta, ou recusa/erro sem conteúdo. HTTP real percorreu cinco tipos e correção, com rastro sem prompt/resposta do aluno;155 testes passaram na015.

Decisões: Laya com checkpoint próprio/revisão fixa e probabilidade de escolha; nenhum multiagente de produto sem ganho medido, uma geração com validação local basta à implementação atual. Modelos locais, sem dados a APIs. Operações de modelo serializadas e Ollama descarregado para a GPU de 6 GiB; executar um worker e sem eval concorrente.

Persistência/ingestão anteriores preservadas; migrações `0002` vetores/FTS, `0003` contas/estudo e `0004` quarentena genérica por SHA/intervalo. Fontes em revisão saem de ambos os ramos de busca e invalidam conteúdo já gerado; não é auditoria científica automática.

Status: arquitetura implementada e em validação da 013; metas de gate, qualidade e revisão final permanecem explícitas, sem transformar passagem de schema em aceite pedagógico.

Na015, captura pública de eval restaura/isola seu provider e feedback de critério zerado mantém o trecho avaliado na API/histórico. Experimento de decomposição não ganhou evidência suficiente para acrescentar etapas ao runtime. Provas com Qwen local em `verification_015.json`; nenhum novo modelo/download/frontend.
