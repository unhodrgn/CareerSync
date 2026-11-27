"""PDF → plain text with PyMuPDF. Text-layer PDFs only (no OCR)."""
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
        raise PdfError("CV_TOO_LARGE", "CV file must be 5 MB or smaller.")
    if not data.startswith(b"%PDF"):
        raise PdfError("CV_NOT_PDF", "Only PDF files can be uploaded.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001  (PyMuPDF raises several types for broken files)
        raise PdfError("CV_UNREADABLE", "Could not read the PDF file.") from e
    with doc:
        if doc.needs_pass:
            raise PdfError("CV_ENCRYPTED", "Password-protected PDF files cannot be uploaded.")
        if doc.page_count > MAX_PAGES:
            raise PdfError("CV_TOO_MANY_PAGES", "CV must be 5 pages or fewer.")
        # sort=True keeps reading order for simple multi-column layouts
        text = "\n".join(page.get_text("text", sort=True) for page in doc)
        pages = doc.page_count
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(text) < MIN_CHARS_PER_PAGE * max(pages, 1):
        raise PdfError("CV_NO_TEXT", "Could not extract text from this PDF. Please upload a text-based PDF rather than a scanned image.")
    return PdfText(text=text, pages=pages)
