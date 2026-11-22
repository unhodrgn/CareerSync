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


def test_pdf_import_rejects_long_source():
    # The preview API has a 10,000-character limit; never silently truncate text.
    document = pymupdf.open()
    page = document.new_page()
    for i in range(130):
        page.insert_text((48, 48 + i * 4), "Required: " + ("TypeScript Vue React API " * 7), fontsize=4)
    data = document.tobytes()
    document.close()
    try:
        job_pdf_service.extract_text(data, "application/pdf")
    except Exception as exc:
        assert getattr(exc, "code", None) in ("JD_PDF_TOO_LONG", "JD_PDF_NO_TEXT")
    else:
        raise AssertionError("Long extraction should be refused, not silently truncated")
