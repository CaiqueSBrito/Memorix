"""Extrai PDFs locais por página e entrega texto ao núcleo transacional da ingestão."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pypdfium2
from pypdf import PdfReader, __version__ as pypdf_version
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from ..providers.observabilitiy import record_trace
from .ingest import Resultado, ingest_document


def _ocr_engine() -> tuple[str, str]:
    command = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if not command and os.name == "nt":
        installed = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
        if installed.is_file():
            command = str(installed)
    if not command:
        raise RuntimeError("Tesseract não instalado; configure TESSERACT_CMD")
    languages = subprocess.run([command, "--list-langs"], capture_output=True, text=True, timeout=15, check=True)
    if "por" not in languages.stdout.splitlines():
        raise RuntimeError("Tesseract não tem o idioma por instalado")
    version = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=15, check=True)
    return command, version.stdout.splitlines()[0]


def _extract_with_metadata(path: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError("PDF protegido por senha")
        if not reader.pages:
            raise ValueError("PDF sem páginas")
    except (PdfReadError, OSError) as error:
        raise ValueError("PDF inválido ou ilegível") from error

    pages = []
    methods = []
    renderer = None
    ocr = None
    try:
        with tempfile.TemporaryDirectory() as temporary_dir:
            for index, page in enumerate(reader.pages):
                content = (page.extract_text() or "").strip()
                if content:
                    method = {"pagina": index + 1, "metodo": "texto", "motor": f"pypdf {pypdf_version}"}
                else:
                    if ocr is None:
                        ocr = _ocr_engine()
                    if renderer is None:
                        renderer = pypdfium2.PdfDocument(str(path))
                    image_path = Path(temporary_dir) / f"pagina-{index + 1}.png"
                    bitmap = renderer[index].render(scale=300 / 72)
                    try:
                        bitmap.to_pil().save(image_path)
                    finally:
                        bitmap.close()
                    ocr_result = subprocess.run(
                        [ocr[0], str(image_path), "stdout", "-l", "por"],
                        capture_output=True, text=True, encoding="utf-8", timeout=120, check=True,
                    )
                    content = ocr_result.stdout.strip()
                    method = {"pagina": index + 1, "metodo": "ocr", "motor": ocr[1], "idioma": "por"}
                if not content:
                    method["metodo"] = "vazio"
                else:
                    pages.append(content)
                methods.append(method)
    finally:
        if renderer is not None:
            renderer.close()
    if not pages:
        raise ValueError("PDF sem texto legível após extração/OCR")
    return "\n\n".join(pages), methods


def extract_pdf(path: str | Path) -> str:
    """Retorna páginas em ordem; PDFs inválidos ou ilegíveis falham explicitamente."""
    content, _ = _extract_with_metadata(Path(path))
    return content


def ingest_pdf(
    path: str | Path, *, title: str, uploaded_by: str,
    doc_id: int | None = None, session: Session | None = None, trace_id: str | None = None,
) -> Resultado:
    """Extrai integralmente antes de tocar no banco; compartilha o trace da 004."""
    start = monotonic()
    trace_id = trace_id or str(uuid4())
    source = Path(path)
    try:
        if source.is_absolute() or ".." in source.parts:
            raise ValueError("fonte deve ser um caminho relativo dentro do acervo")
        content, pages = _extract_with_metadata(source)
    except Exception as error:
        record_trace(trace_id, "extracao", status="erro", erro=type(error).__name__,
                  duracao_ms=(monotonic() - start) * 1000)
        raise
    record_trace(trace_id, "extracao", status="ok", erro=None,
              duracao_ms=(monotonic() - start) * 1000, paginas=pages)
    return ingest_document(content, title=title, source_type="pdf", uploaded_by=uploaded_by,
                   source=source, doc_id=doc_id, session=session,
                   trace_id=trace_id, extractor=", ".join(dict.fromkeys(p["motor"] for p in pages)))
