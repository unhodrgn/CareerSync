"""Extract editable JD text from a PDF without persisting uploaded bytes.

Text-layer PDFs only. Scans are refused rather than silently treated as empty JDs.
Separate from CV parsing so the CV's page/count/error contract stays unchanged.
"""
from dataclasses import dataclass

import pymupdf

from app.core.errors import AppError

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_SOURCE_CHARS = 10_000
MIN_TEXT_CHARS_PER_PAGE = 40


@dataclass(frozen=True)
class JobPdfText:
    text: str
    pages: int


def extract_text(data: bytes, mime: str | None = None) -> JobPdfText:
    if not data or len(data) > MAX_PDF_BYTES:
        raise AppError(422, "JD_PDF_SIZE", "PDF는 5MB 이하로 업로드해 주세요.")
    if not data.startswith(b"%PDF"):
        raise AppError(422, "JD_PDF_FORMAT", "올바른 PDF 파일을 업로드해 주세요.")
    if mime not in (None, "application/pdf", "application/octet-stream"):
        raise AppError(422, "JD_PDF_FORMAT", "PDF 형식의 파일을 업로드해 주세요.")
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF uses several exception types for broken documents
        raise AppError(422, "JD_PDF_UNREADABLE", "PDF 파일을 읽을 수 없습니다.") from exc

    with document:
        if document.needs_pass:
            raise AppError(422, "JD_PDF_ENCRYPTED", "암호화된 PDF는 지원하지 않습니다.")
        if not 1 <= document.page_count <= MAX_PDF_PAGES:
            raise AppError(422, "JD_PDF_PAGES", "PDF는 1~10페이지여야 합니다.")
        page_texts = [page.get_text("text", sort=True).strip() for page in document]
        pages = document.page_count

    text = "\n".join(page_texts)
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(text) < MIN_TEXT_CHARS_PER_PAGE * pages:
        raise AppError(422, "JD_PDF_NO_TEXT", "텍스트가 없는 이미지·스캔 PDF입니다. 텍스트 PDF 또는 이미지 포스터를 이용해 주세요.")
    if len(text) > MAX_SOURCE_CHARS:
        raise AppError(422, "JD_PDF_TOO_LONG", "추출된 텍스트가 10,000자를 초과합니다. 필요한 부분만 복사해 분석해 주세요.")
    return JobPdfText(text=text, pages=pages)
