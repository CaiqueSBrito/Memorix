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

from ..providers.rastro import registrar
from .ingest import Resultado, ingerir


def _motor_ocr() -> tuple[str, str]:
    comando = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if not comando and os.name == "nt":
        instalado = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
        if instalado.is_file():
            comando = str(instalado)
    if not comando:
        raise RuntimeError("Tesseract não instalado; configure TESSERACT_CMD")
    idiomas = subprocess.run([comando, "--list-langs"], capture_output=True, text=True, timeout=15, check=True)
    if "por" not in idiomas.stdout.splitlines():
        raise RuntimeError("Tesseract não tem o idioma por instalado")
    versao = subprocess.run([comando, "--version"], capture_output=True, text=True, timeout=15, check=True)
    return comando, versao.stdout.splitlines()[0]


def _extrair(caminho: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        leitor = PdfReader(str(caminho))
        if leitor.is_encrypted:
            raise ValueError("PDF protegido por senha")
        if not leitor.pages:
            raise ValueError("PDF sem páginas")
    except (PdfReadError, OSError) as erro:
        raise ValueError("PDF inválido ou ilegível") from erro

    paginas = []
    metodos = []
    renderizador = None
    ocr = None
    try:
        with tempfile.TemporaryDirectory() as temporario:
            for indice, pagina in enumerate(leitor.pages):
                texto = (pagina.extract_text() or "").strip()
                if texto:
                    metodo = {"pagina": indice + 1, "metodo": "texto", "motor": f"pypdf {pypdf_version}"}
                else:
                    if ocr is None:
                        ocr = _motor_ocr()
                    if renderizador is None:
                        renderizador = pypdfium2.PdfDocument(str(caminho))
                    imagem = Path(temporario) / f"pagina-{indice + 1}.png"
                    bitmap = renderizador[indice].render(scale=300 / 72)
                    try:
                        bitmap.to_pil().save(imagem)
                    finally:
                        bitmap.close()
                    leitura = subprocess.run(
                        [ocr[0], str(imagem), "stdout", "-l", "por"],
                        capture_output=True, text=True, encoding="utf-8", timeout=120, check=True,
                    )
                    texto = leitura.stdout.strip()
                    metodo = {"pagina": indice + 1, "metodo": "ocr", "motor": ocr[1], "idioma": "por"}
                if not texto:
                    raise ValueError(f"Página {indice + 1} sem texto legível após extração/OCR")
                paginas.append(texto)
                metodos.append(metodo)
    finally:
        if renderizador is not None:
            renderizador.close()
    return "\n\n".join(paginas), metodos


def extrair_pdf(caminho: str | Path) -> str:
    """Retorna páginas em ordem; PDFs inválidos ou ilegíveis falham explicitamente."""
    texto, _ = _extrair(Path(caminho))
    return texto


def ingerir_pdf(
    caminho: str | Path, *, title: str, uploaded_by: str,
    doc_id: int | None = None, session: Session | None = None,
) -> Resultado:
    """Extrai integralmente antes de tocar no banco; compartilha o trace da 004."""
    inicio = monotonic()
    trace_id = str(uuid4())
    fonte = Path(caminho)
    try:
        if fonte.is_absolute() or ".." in fonte.parts:
            raise ValueError("fonte deve ser um caminho relativo dentro do acervo")
        texto, paginas = _extrair(fonte)
    except Exception as erro:
        registrar(trace_id, "extracao", status="erro", erro=type(erro).__name__,
                  duracao_ms=(monotonic() - inicio) * 1000)
        raise
    registrar(trace_id, "extracao", status="ok", erro=None,
              duracao_ms=(monotonic() - inicio) * 1000, paginas=paginas)
    return ingerir(texto, title=title, source_type="pdf", uploaded_by=uploaded_by,
                   fonte=fonte, doc_id=doc_id, session=session,
                   trace_id=trace_id, extrator=", ".join(dict.fromkeys(p["motor"] for p in paginas)))
