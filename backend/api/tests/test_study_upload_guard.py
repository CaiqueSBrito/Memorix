"""Anonymous multipart must be rejected without reading/spooling its request body."""

from test_study_api import client


def test_anonymous_pdf_upload_is_denied_before_body_is_consumed(client):
    http, _ = client
    consumed = []
    def body():
        consumed.append(True)
        yield b"private-oversized-pdf"
    response = http.post("/admin/ingest/pdf", content=body(),
                         headers={"Content-Type": "multipart/form-data; boundary=untrusted"})
    assert response.status_code == 401
    assert consumed == []
