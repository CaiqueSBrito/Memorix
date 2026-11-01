# Teste primeiro — toda feature

Vale para toda criação de feature, em qualquer trilha. Mudança que não é feature (typo, rename, log) segue a trilha Rápida sem esta regra.

## Ordem obrigatória

1. **Escrever o teste automatizado** a partir dos critérios de aceitação da tarefa — o que a feature faz, vista de fora (entrada → saída/efeito observável). Não testar detalhes internos que a implementação ainda nem escolheu.
   - Local: `backend/tests/`, `pytest` (instalar no `venv` na primeira feature).
   - Cobrir o caminho feliz, bordas e o erro esperado de cada critério.
2. **Checar o teste antes de existir a feature.**
   - Cada critério de aceitação tem ao menos uma asserção; registrar o mapa critério → teste na tarefa.
   - Rodar: o teste **deve falhar**, e pelo motivo certo (feature ausente — não import quebrado, fixture errada ou erro de sintaxe). Teste que passa sem a feature não testa nada → reescrever.
   - Registrar na tarefa: saída da execução falhando + `sha256` de cada arquivo de teste.
   - Gate humano: "ok" no teste. **Mudança pequena** (≤3 arquivos afetados, sem dependência nova): funde com o gate do plano (etapa 2 do pipeline) — um único pedido de "ok" cobre plano + teste falhando; mudança maior mantém os dois gates separados.
3. **Implementar a feature sem tocar no teste.**
   - Pronto = o teste passa + os testes anteriores continuam passando.
   - Ao final, conferir o `sha256` dos arquivos de teste contra o registrado. Diferente → a entrega é inválida.
4. **Teste errado?** Parar. Não ajustar o teste para a implementação passar. Voltar para Planejar, explicar o defeito do teste e pedir aprovação do humano antes de alterá-lo; o novo teste passa de novo pela etapa 2.

## Proibido

- Implementar antes do teste falhar pelo motivo certo.
- Editar, pular (`skip`/`xfail`), afrouxar asserção ou apagar teste para obter "passou".
- Mockar a própria unidade sob teste. Mock só em fronteira externa (rede, modelo pago), e o teste deve deixar claro o que é simulado.
