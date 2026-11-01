"""A future frontend can open cited archive material without filesystem paths."""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4


from test_study_api import auth, client, login, register


def test_cited_text_is_readable_only_after_authentication(client):
    http, session = client
    from backend.src.Memorix.entities.documents import Chunk, Document
    text = "Texto didático sintético sobre adição."
    document = Document(doc_sha256=sha256(text.encode()).hexdigest(), title="Matemática sintética",
                        source_type="texto", uploaded_by="admin", extra={"fonte": "synthetic.txt"})
    session.add(document)
    session.flush()
    chunk = Chunk(doc_id=document.doc_id, position=0, text=text, offset_start=0, offset_end=len(text))
    session.add(chunk)
    session.commit()
    url = f"/study/materials/{document.doc_id}?chunk_id={chunk.chunk_id}"
    assert http.get(url).status_code == 401
    headers = auth(register(http, "reader@example.test"))
    response = http.get(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Matemática sintética"
    assert response.json()["text"] == text
    assert "synthetic.txt" not in response.text
    assert http.get(f"/study/materials/{document.doc_id}?chunk_id=unknown", headers=headers).status_code == 404


def test_uploaded_pdf_is_downloadable_only_for_existing_archive_record(client):
    http, session = client
    from backend.src.Memorix.entities.documents import Document
    path = Path("backend/uploads") / f"{uuid4()}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"%PDF-1.4\nsynthetic archive content"
    path.write_bytes(data)
    try:
        document = Document(doc_sha256=sha256(data).hexdigest(), title="PDF sintético",
                            source_type="pdf", uploaded_by="admin", extra={"fonte": path.as_posix()})
        session.add(document)
        session.commit()
        url = f"/study/materials/{document.doc_id}/download"
        assert http.get(url).status_code == 401
        student = auth(register(http, "download@example.test"))
        response = http.get(url, headers=student)
        assert response.status_code == 200 and response.content == data
        assert "backend/uploads" not in str(response.headers)
        admin = login(http, "admin@example.test", "admin-secret-123")
        assert http.get(url, headers=admin).content == data
    finally:
        path.unlink(missing_ok=True)
