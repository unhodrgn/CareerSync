"""Text-layer PDF JD import API tests (upload is never stored)."""
import pymupdf

from app.services import job_pdf_service


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    result = doc.tobytes()
    doc.close()
    return result


def test_company_can_extract_pdf(client, world):
    data = _pdf("Required: Vue or React and TypeScript. API integration and state management.")
    result = client.post(
        "/api/jobs/pdf-text",
        files={"file": ("jd.pdf", data, "application/pdf")},
        headers=world["recruiter"],
    )
    assert result.status_code == 200, result.json()
    assert result.json()["pages"] == 1
    assert "React and TypeScript" in result.json()["text"]


def test_pdf_import_requires_company(client, world):
    data = _pdf("Required: TypeScript, React, API integration and testing for a web app.")
    files = {"file": ("jd.pdf", data, "application/pdf")}
    assert client.post("/api/jobs/pdf-text", files=files).status_code == 401
    assert client.post("/api/jobs/pdf-text", files=files, headers=world["seeker"]).status_code == 403


def test_pdf_import_rejects_bad_bytes(client, world):
    result = client.post(
        "/api/jobs/pdf-text",
        files={"file": ("bad.pdf", b"%PDF-not-a-real-document", "application/pdf")},
        headers=world["recruiter"],
    )
    assert result.status_code == 422
    assert result.json()["code"] == "JD_PDF_UNREADABLE"


def test_pdf_import_rejects_scan_without_text():
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    try:
        job_pdf_service.extract_text(data, "application/pdf")
    except Exception as exc:
        assert getattr(exc, "code", None) == "JD_PDF_NO_TEXT"
    else:
        raise AssertionError("Image-only PDF should fail with a clear message")


def test_pdf_import_rejects_long_source(monkeypatch):
    import pytest
    from app.core.errors import AppError

    class FakePage:
        def get_text(self, *_args, **_kwargs):
            return "X" * 10_001

    class FakeDocument:
        needs_pass = False
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter((FakePage(),))

    monkeypatch.setattr(job_pdf_service.pymupdf, "open", lambda **_kwargs: FakeDocument())
    with pytest.raises(AppError) as caught:
        job_pdf_service.extract_text(b"%PDF-mock", "application/pdf")
    assert caught.value.code == "JD_PDF_TOO_LONG"
