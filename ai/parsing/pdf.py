"""PDF → plain text with PyMuPDF. Text-layer PDFs only (no OCR, per README scope)."""
from dataclasses import dataclass

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 5
# Fewer extracted characters than this per page means a scanned (image-only) PDF
MIN_CHARS_PER_PAGE = 40


class PdfError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PdfText:
    text: str
    pages: int


def extract_text(data: bytes) -> PdfText:
    import pymupdf

    if len(data) > MAX_BYTES:
        raise PdfError("CV_TOO_LARGE", "이력서 파일은 5MB 이하여야 합니다.")
    if not data.startswith(b"%PDF"):
        raise PdfError("CV_NOT_PDF", "PDF 파일만 업로드할 수 있습니다.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001  (PyMuPDF raises several types for broken files)
        raise PdfError("CV_UNREADABLE", "PDF 파일을 읽을 수 없습니다.") from e
    with doc:
        if doc.needs_pass:
            raise PdfError("CV_ENCRYPTED", "암호가 걸린 PDF는 업로드할 수 없습니다.")
        if doc.page_count > MAX_PAGES:
            raise PdfError("CV_TOO_MANY_PAGES", "이력서는 5페이지 이하여야 합니다.")
        # sort=True keeps reading order for simple multi-column layouts
        text = "\n".join(page.get_text("text", sort=True) for page in doc)
        pages = doc.page_count
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(text) < MIN_CHARS_PER_PAGE * max(pages, 1):
        raise PdfError("CV_NO_TEXT", "텍스트를 추출할 수 없는 PDF입니다. 스캔본이 아닌 텍스트 PDF를 올려 주세요.")
    return PdfText(text=text, pages=pages)
