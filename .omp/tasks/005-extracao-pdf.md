# 005 — Extração de PDF com OCR local para o acervo
Goal: 1.2 — Ingestão do acervo        Trilha: IA        Estado: Concluída

Execução do goal 1.2 autorizada pelo humano em 2026-10-01 ("Autorizar o goal 1.2 inteiro (004 e 005/PDF)"). A 004 foi aceita e commitada em `develop`; o humano pediu que a 005 rode "em outra worktree".

## Objetivo

Extrair texto de PDF selecionável **e** digitalizado (OCR local, português) e passá-lo ao núcleo da 004 (`ingerir`) com `source_type="pdf"`, preservando ordem de páginas, texto canônico, SHA, offsets, reingestão atômica e rastro. PDF misto decide por página: usa texto nativo quando presente e OCR quando a página não tem camada textual. O PDF de origem fica referenciado por caminho relativo em `documents.metadata`; conteúdo jamais sai para terceiros.

## Critérios de aceitação

- [x] PDF selecionável de duas páginas extrai texto na ordem; a 004 canonicaliza, divide e persiste offsets que recortam exatamente o texto.
- [x] Reingestão idêntica é `sem_mudanca` sem recriar chunks; PDF alterado no mesmo `doc_id` substitui spans na transação da 004.
- [x] PDF de duas páginas digitalizadas em português, com acentos, passa por OCR local; PDF misto usa texto nativo na primeira página e OCR só na segunda. Método/motor/idioma registrados por página sem texto no rastro.
- [x] PDF inválido, protegido e página digitalizada em branco falham antes da transação; falha registrada no rastro, sem documento vazio ou perda de chunks prévios.
- [x] `source_type="pdf"`, caminho relativo em `metadata`, SHA canônico, extrator efetivo e `chunk_id` conferidos no banco e JSONL, sem conteúdo no rastro.
- [x] 67 casos existentes restantes após remoção autorizada do guardrail mais 10 casos PDF passam; migração `0001` mantém bytes SHA congelados.

## Fora do escopo

- Reconstrução de layout complexo, fórmulas, tabelas e manuscritos; OCR de texto impresso em português está **dentro** do escopo, por decisão expressa do humano.
- Interface HTTP de upload, autenticação do admin, embeddings, busca e migração nova.

## Esclarecer

- OCR **dentro** da 005 por decisão humana: "Sim; incluir OCR na 005". Motor selecionado pelo humano: **Tesseract OCR + pypdfium2**; Tesseract 5.5.3 instalado nesta máquina via winget, com `por`, `eng` e `osd` disponíveis (`--list-langs`). Nunca enviar PDF/imagens a terceiros.
- Dependência `pypdf` **autorizada** e teste aprovado alterável apenas no recorte autorizado: "Autorizar pypdf e remover o guardrail global obsoleto". Remover somente `test_requirements_sem_dependencia_nova` da 004, sem repinar nem afrouxar outros testes; registrar sha256 antigo/novo e provar as demais asserções.

## Plano

**Plano aprovado pelo humano:** "Aprovar plano e seguir ao teste primeiro". Usar `pypdf==6.19.0` na extração selecionável, `pypdfium2==5.13.0` + `Pillow==12.3.0` para renderizar só páginas sem texto a 300 DPI e Tesseract 5.5.3 com `-l por` para OCR local. Três dependências Python pinadas e binário/dados `por` exigidos no runtime; validar disponibilidade no caminho OCR. Páginas em ordem unidas por `\n\n`; página sem texto nem OCR legível falha antes do banco.

| Passo | Arquivo | Entrega/prova |
| --- | --- | --- |
| 1. Gate humano do plano | esta tarefa | Aprovar escopo, três deps Python, binário Tesseract e casos testados. |
| 2. Teste primeiro | `backend/api/tests/test_pdf.py` + PDFs de fixture em `backend/api/tests/fixtures/pdf/` | PDF selecionável de duas páginas, PDF imagem de duas páginas em português, PDF misto, PDF inválido/protegido, reingestão/rollback e rastro; rodar falhando por `ModuleNotFoundError` de `ingestion.pdf`, registrar sha256 e pedir gate humano do teste. |
| 3. Dependências + implementação | `requirements.txt`, `backend/src/Memorix/ingestion/pdf.py` | `extrair_pdf` decide texto/OCR por página; `ingerir_pdf` chama o núcleo da 004. Renderizar página via PDFium + Pillow em arquivo temporário, subprocess sem shell para Tesseract `por`; nada online. |
| 4. Propagar rastro | `backend/src/Memorix/ingestion/ingest.py` | Parâmetros opcionais de trace/extrator/páginas; texto da 004 mantém defaults; PDF registra método de cada página e erro de extração com mesmo `trace_id`, nunca conteúdo. |
| 5. Remover guardrail aprovado | `backend/api/tests/test_ingestao.py` | Apagar só `test_requirements_sem_dependencia_nova` (não repinar), registrar novo SHA; os 56 casos restantes e 11 da 002 passam com o novo teste PDF. |
| 6. Provar e revisar | esta tarefa + banco de dev | Execução real com PDFs de fixture, texto extraído e SHA verificável, OCR português e rastro; suíte completa; devolver Alembic a `0001 (head)`; pedir aceite final. |

Como é mudança >3 arquivos com novas dependências, gate de plano e gate de teste são **separados**. Nenhuma biblioteca é instalada no runtime implicitamente: o ambiente deve ser provisionado antes, com falha explícita se Tesseract/`por` não existirem. PDF sem texto não vira documento vazio. O OCR é local e nenhuma senha/conteúdo entra no JSONL.

## Baseline (IA)

Baseline: não havia extrator PDF no produto, logo comparação de retrieval antes × depois **Não se aplica**. Com uma fixture sintética digitalizada de duas páginas e fonte DejaVu Sans legível a 300 DPI, o Tesseract 5.5.3 `por` (chamado diretamente antes da implementação) transcreveu exatamente as duas frases de referência com acentos: "A fotossíntese converte a luz solar em energia química para as plantas." e "A água líquida é essencial para a vida e regula a temperatura do planeta.". Hipótese H-005: PDF selecionável preserva todas as palavras em ordem e OCR local reconhece ≥90% das palavras por página em fixture impressa; o teste novo mede o alinhamento de palavras, não só um `not None`. O perfil estrutural da 004 não mede OCR e H-004 continua Falhou.

## Teste primeiro (feature)

`backend/api/tests/test_pdf.py` (SHA-256 **`3084a3bd4ef593899b0bdc96c2e9843e76f8b678acea6ccfbd09761f67d700be`**) e seis PDFs reais de fixture foram criados antes do módulo `ingestion/pdf.py`. Rodada da raiz da worktree: `./venv/Scripts/python.exe -m pytest backend/api/tests/test_pdf.py -q --tb=short` → **10 failed in 6.53s**, todas por `ModuleNotFoundError: No module named 'backend.src.Memorix.ingestion.pdf'` (motivo certo; zero erro de coleta, fixture ou OCR). Hashes dos PDFs: `selecionavel` `7467e75e…c2cbe6`, `digitalizado` `bf50d624…0584d`, `misto` `f7ea4e4d…b6d5555`, `alterado` `1b2dd210…c7b6a`, `protegido` `688d1093…e2977`, `invalido` `f0f98bfe…ea398`. O banco foi devolvido a `0001 (head)`. **Gate humano do teste aprovado:** "Aprovar e congelar teste/fixtures PDF". Implementar sem editar esses artefatos.

## Evidências

| O quê | Método | Status |
| --- | --- | --- |
| Tesseract 5.5.3.20260724 instalado, com idioma `por` disponível | `winget install` + `tesseract --version` + `--list-langs` | Passou |
| Pins `pypdf==6.19.0`, `pypdfium2==5.13.0`, `Pillow==12.3.0` instalados e registrados em `requirements.txt` | `pip install` após gate + conteúdo dos pins | Passou |
| Tarefa 004 aceita e commitada (`5383c8d` é o último commit da série) | `git log`, aprovação literal do humano | Passou |
| `test_pdf.py` falha pelo motivo certo, em 10 casos; OCR direto da fixture transcreveu as duas páginas com acentos | `pytest` + subprocess Tesseract local | Passou |
| Novo teste PDF e regressões existentes | `./venv/Scripts/python.exe -m pytest backend/api/tests -q --tb=short` na worktree, rodada final | **77 passed in 73.92s** |
| H-005: fidelidade por página em selecionável, digitalizado e misto | `extrair_pdf` real com `SequenceMatcher` nas sequências de palavras das seis páginas | **6/6 = 1,0**; alvo ≥0,90, **Passou** nas fixtures impressas |
| Página imagem branca sem texto, sem efeitos colaterais | PDF temporário real com Pillow → `extrair_pdf` e `ingerir_pdf`, rastro temporário | `ValueError`, único registro `extracao/erro`, nenhum PNG residual; Passou |
| Imutabilidade do teste PDF e fixtures aprovadas | SHA-256 após implementação | `test_pdf.py` **`3084a3bd…d700be`** e seis PDFs idênticos aos hashes de antes do produto |
| Banco de desenvolvimento após suíte | `alembic -c alembic.ini upgrade head && ... current` | **`0001 (head)`** |
| Extrator real, origem e trechos sem texto no rastro | Integração SQL + JSONL de três etapas com `trace_id` único nos casos PDF | Passou |
| Código integrado em `develop` por fast-forward | `pytest backend/api/tests/test_pdf.py -q --tb=short` da raiz principal + SHA-256 dos PDFs, teste e `0001` | **10 passed in 31.87s**, hashes preservados; banco restaurado a `0001 (head)` |

## Revisão técnica

O `orchestrator` revisou em leitura os seis critérios contra `pdf.py`, `ingest.py`, testes, pins e `.gitattributes`: **todos Passou; nenhum achado bloqueante; pronto para gate final humano**. Conferiu os SHA de `test_pdf.py` e `0001`; não reexecutou a suíte. Ressalva operacional: Tesseract e dados `por` precisam existir em cada instalação. A revisão pedagógica não se aplica nesta etapa de extração sem saída ao aluno.

## Revisão pedagógica

Não se aplica à extração técnica enquanto o conteúdo não chega ao aluno; a qualidade de trechos para questões/flashcards será medida na 007 e revisada nos goals 1.4/1.5.

## Decisões e conflitos

- O humano autorizou "pode fazer, em outra worktree". A tarefa é criada no checkout principal; a implementação roda no worktree a partir de `develop` com 004 commitada.
- O `orchestrator`/`ai-rag-specialist` estiveram indisponíveis por erro 429 no desenho da 005; o humano aprovou o plano específico para avançar. O `orchestrator` conseguiu revisar o produto antes do gate final e não achou bloqueios; não atribuir aprovação técnica ao especialista IA ausente.
- Gate humano de 2026-10-01: OCR incluído ("Sim; incluir OCR na 005"), `pypdf` autorizado e exclusão do guardrail global da 004 explicitamente autorizada ("Autorizar pypdf e remover o guardrail global obsoleto"). Ainda não há autorização para baixar/enviar conteúdo privado a terceiros; o OCR será local.
- O humano selecionou "Tesseract OCR + pypdfium2" no gate de motor. Tesseract 5.5.3 veio do pacote winget `tesseract-ocr.tesseract` (Apache-2.0); idioma `por` presente. A tentativa `--scope user` não tinha instalador aplicável, e a instalação padrão silenciosa passou. pypdfium2 fornece wheel com PDFium; Pillow converte bitmap para imagem temporária do subprocess. Deploy precisa provisionar binário e dados `por`; isto é requisito operacional real, não fallback falso.
- Gate humano do plano: "Aprovar plano e seguir ao teste primeiro". O `ai-rag-specialist` ficou indisponível por erro 429, e o humano escolheu avançar com o plano específico sujeito ao teste e ao aceite final.
- Em outra worktree, Git autocrlf produziu SHA de bytes `46912fd2…ad5d73` para `test_ingestao.py` ainda **sem qualquer edição**, enquanto o checkout principal registrara `310973ef…ae0c`. Não interpretar diferença de line ending de checkout como mudança de asserção; registrar o SHA desta worktree antes e depois da remoção autorizada de um único guardrail.
- Gate humano do teste: "Aprovar e congelar teste/fixtures PDF". `test_pdf.py` e os seis PDFs estão congelados nos hashes acima.
- A remoção aprovada de `test_requirements_sem_dependencia_nova` retirou apenas essa função, sua constante não usada e comentários de contagem. `test_ingestao.py` nesta worktree: SHA anterior `46912fd2104b282bff02c57bc2c9d95c84a1059354bdfc382a7f577112ad5d73`; SHA posterior `935984d0eb8b94995fbd7118787b8f295e46772b31782a16093780471dc21cab`; as demais asserções permanecem.
- O teste ainda aprovado que fixa SHA de `0001` falhou na primeira suíte completa porque `core.autocrlf=true` fez checkout da migração com CRLF (SHA `9859f13c…10b1`). O blob versionado é LF com SHA `eba47c86…76562`. `.gitattributes` limita `text eol=lf` à migração e ao teste PDF congelado; bytes da migração no worktree foram normalizados, `git add` atualizou o índice sem diff da migração. A segunda suíte passou 77/77, sem alterar o conteúdo da migração nem o teste congelado.
- H-005 **Passou nas fixtures**: seis páginas com alinhamento de palavras 1,0; isto não garante OCR em layouts complexos/manuscritos fora do escopo. H-004 **Falhou** segue aceito, sem maquiagem; medir corpus real na 007. Binário Tesseract + dados `por` devem existir em todo deploy, com `TESSERACT_CMD` se fora do PATH/instalação padrão Windows.
- Gate humano final: "Aceitar 005 e concluir goal 1.2". Autorização Git separada: "Commits atômicos e integrar em develop". Cinco commits `3ac43dc`, `a3fb26d`, `b9ffe71`, `6f68345`, `e70f44a` integrados por fast-forward local em `develop`, sem push/deploy; goal e progresso registrados no checkout principal após o merge.
