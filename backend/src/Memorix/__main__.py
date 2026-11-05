"""Interface local: python3 -m backend.src.Memorix --help."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .contracts.generation import CONTENT_TYPES, DIFFICULTIES, GenerationRequest
from .ingestion.corpus import Corpus
from .pipeline.generation import generate_material
from .providers.local_llm import LocalLLM
from .storage.flashcard_sessions import FlashcardStore
from .storage.materials import MaterialStore
from .storage.study_sessions import StudyStore
from .study.flashcard_queue import flashcard_queue
from .study.flashcard_schedule import RATINGS
from .study.planning import build_study_plan
from .study.progress import progress_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Acervo, geração, revisão e estudo no Memorix")
    parser.add_argument("--db", type=Path, default=Path("data/acervo.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Importar texto UTF-8 (.txt, .md) ou PDF")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--title", help="Título do documento (padrão: nome do arquivo)")
    search = commands.add_parser("search", help="Buscar trechos do acervo")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    generate = commands.add_parser("generate", help="Gerar material com fontes usando LLM local")
    generate.add_argument("topic", help="Tema usado para recuperar trechos do acervo")
    generate.add_argument("--type", dest="kind", choices=CONTENT_TYPES, required=True)
    generate.add_argument("--count", type=int, default=5, help="Quantidade de itens ou seções da aula (1–20)")
    generate.add_argument("--difficulty", choices=DIFFICULTIES, default="basica")
    generate.add_argument("--limit", type=int, default=5, help="Máximo de trechos recuperados")
    generate.add_argument("--endpoint", default="http://127.0.0.1:8080/v1/chat/completions")
    generate.add_argument("--model", default="local", help="Identificador do modelo no servidor local")
    generate.add_argument("--timeout", type=float, default=120.0, help="Timeout da requisição, em segundos")
    material_import = commands.add_parser("material-import", help="Salvar um rascunho JSON para revisão")
    material_import.add_argument("file", type=Path)
    material_list = commands.add_parser("material-list", help="Listar materiais salvos")
    material_list.add_argument("--status", choices=("requires_review", "approved", "rejected"))
    material_list.add_argument("--limit", type=int, default=20)
    material_show = commands.add_parser("material-show", help="Consultar um material e suas fontes")
    material_show.add_argument("material_id")
    material_show.add_argument("--draft", action="store_true", help="Exportar JSON editável, sem decisão de revisão")
    material_update = commands.add_parser("material-update", help="Substituir conteúdo e exigir nova revisão")
    material_update.add_argument("material_id")
    material_update.add_argument("file", type=Path)
    material_update.add_argument("--version", type=int, required=True, help="Versão atual esperada")
    material_review = commands.add_parser("material-review", help="Aprovar ou rejeitar a versão revisada")
    material_review.add_argument("material_id")
    material_review.add_argument("--version", type=int, required=True, help="Versão atual esperada")
    material_review.add_argument("--decision", choices=("approve", "reject"), required=True)
    study_start = commands.add_parser("study-start", help="Iniciar questionário aprovado sem mostrar gabarito")
    study_start.add_argument("material_id")
    study_start.add_argument("--version", type=int, required=True, help="Versão aprovada esperada")
    study_show = commands.add_parser("study-show", help="Retomar sessão ou consultar resultado concluído")
    study_show.add_argument("session_id")
    study_submit = commands.add_parser("study-submit", help="Enviar lista JSON completa de respostas")
    study_submit.add_argument("session_id")
    study_submit.add_argument("file", type=Path)
    study_list = commands.add_parser("study-list", help="Listar sessões de estudo locais")
    study_list.add_argument("--status", choices=("in_progress", "completed"))
    study_list.add_argument("--limit", type=int, default=20)
    study_progress = commands.add_parser("study-progress", help="Consultar acurácia das sessões concluídas")
    study_progress.add_argument("--material", dest="material_id", help="Filtrar por identificador de material")
    study_plan = commands.add_parser("study-plan", help="Priorizar prática e indicar materiais com fontes compartilhadas")
    study_plan.add_argument("--target", type=float, default=0.8, help="Meta de acurácia, maior que 0 e até 1")
    study_plan.add_argument("--limit", type=int, default=5, help="Máximo de tarefas do plano")
    study_plan.add_argument("--material", dest="material_id", help="Filtrar questionário por identificador")
    flash_start = commands.add_parser("flash-start", help="Praticar cartões novos ou vencidos de material aprovado")
    flash_start.add_argument("material_id")
    flash_start.add_argument("--version", type=int, required=True, help="Versão aprovada esperada")
    flash_start.add_argument("--limit", type=int, default=20)
    flash_show = commands.add_parser("flash-show", help="Retomar prática de flashcards ou consultar histórico")
    flash_show.add_argument("session_id")
    flash_reveal = commands.add_parser("flash-reveal", help="Revelar verso e fontes do cartão atual")
    flash_reveal.add_argument("session_id")
    flash_reveal.add_argument("--item", type=int, required=True, help="item_index do cartão atual")
    flash_rate = commands.add_parser("flash-rate", help="Autoavaliar o cartão revelado e agendar revisão")
    flash_rate.add_argument("session_id")
    flash_rate.add_argument("--item", type=int, required=True, help="item_index do cartão atual")
    flash_rate.add_argument("--rating", choices=RATINGS, required=True)
    flash_queue = commands.add_parser("flash-queue", help="Listar cartões novos e revisões vencidas")
    flash_queue.add_argument("--material", dest="material_id")
    flash_queue.add_argument("--limit", type=int, default=20)
    flash_list = commands.add_parser("flash-list", help="Listar sessões de flashcards sem expor versos")
    flash_list.add_argument("--status", choices=("in_progress", "completed"))
    flash_list.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    try:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        with Corpus(args.db) as corpus:
            if args.command == "ingest":
                result = asdict(corpus.ingest_file(args.file, title=args.title))
            elif args.command == "search":
                result = [asdict(hit) for hit in corpus.search(args.query, limit=args.limit)]
            elif args.command == "generate":
                request = GenerationRequest(args.kind, args.topic, args.count, args.difficulty)
                result = generate_material(
                    corpus,
                    request,
                    client=LocalLLM(args.endpoint, args.model, args.timeout),
                    retrieval_limit=args.limit,
                )
            elif args.command.startswith("material-"):
                with MaterialStore(args.db) as materials:
                    if args.command == "material-import":
                        payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
                        result = materials.create(payload)
                    elif args.command == "material-list":
                        result = materials.list_materials(status=args.status, limit=args.limit)
                    elif args.command == "material-show":
                        result = materials.get(args.material_id)
                        if args.draft:
                            result = {
                                key: result[key]
                                for key in ("kind", "topic", "difficulty", "title", "items")
                            }
                            result["status"] = "requires_review"
                    elif args.command == "material-update":
                        payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
                        result = materials.update(
                            args.material_id, payload, expected_version=args.version
                        )
                    else:
                        result = materials.review(
                            args.material_id, args.decision, expected_version=args.version
                        )
            elif args.command.startswith("flash-"):
                with MaterialStore(args.db), FlashcardStore(args.db) as cards:
                    if args.command == "flash-start":
                        result = cards.start(
                            args.material_id, expected_version=args.version, limit=args.limit
                        )
                    elif args.command == "flash-show":
                        result = cards.get(args.session_id)
                    elif args.command == "flash-reveal":
                        result = cards.reveal(args.session_id, expected_item=args.item)
                    elif args.command == "flash-rate":
                        result = cards.rate(
                            args.session_id, args.rating, expected_item=args.item
                        )
                    elif args.command == "flash-queue":
                        result = flashcard_queue(
                            args.db, material_id=args.material_id, limit=args.limit
                        )
                    else:
                        result = cards.list_sessions(status=args.status, limit=args.limit)
            else:
                with MaterialStore(args.db), StudyStore(args.db) as studies:
                    if args.command == "study-start":
                        result = studies.start(args.material_id, expected_version=args.version)
                    elif args.command == "study-show":
                        result = studies.get(args.session_id)
                    elif args.command == "study-submit":
                        answers = json.loads(args.file.read_text(encoding="utf-8-sig"))
                        result = studies.submit(args.session_id, answers)
                    elif args.command == "study-list":
                        result = studies.list_sessions(status=args.status, limit=args.limit)
                    elif args.command == "study-progress":
                        result = progress_summary(args.db, material_id=args.material_id)
                    else:
                        result = build_study_plan(
                            args.db,
                            target_accuracy=args.target,
                            limit=args.limit,
                            material_id=args.material_id,
                        )
    except (OSError, UnicodeError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"Erro: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
