"""Local OCR for company hiring posters. The uploaded bytes are deleted after recognition."""
import os
import subprocess
import tempfile

from app.core.errors import AppError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_OCR_TEXT = 10_000


def extract_text(data: bytes, mime: str | None) -> str:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise AppError(422, "POSTER_SIZE", "Please upload an image of 5 MB or smaller.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix, expected = ".png", "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        suffix, expected = ".jpg", "image/jpeg"
    else:
        raise AppError(422, "POSTER_FORMAT", "Please upload a PNG or JPEG image only.")
    if mime not in (None, expected, "application/octet-stream"):
        raise AppError(422, "POSTER_FORMAT", "The image file format does not match its type.")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            path = tmp.name
            tmp.write(data)
        try:
            result = subprocess.run(
                ["tesseract", path, "stdout", "-l", "kor+eng", "--psm", "3"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AppError(503, "POSTER_OCR_UNAVAILABLE", "The image text recognition service is unavailable.") from exc
        if result.returncode:
            raise AppError(422, "POSTER_OCR_FAILED", "No text could be extracted from the image.")
        text = result.stdout.strip()
        if not text:
            raise AppError(422, "POSTER_OCR_EMPTY", "No text was recognized. Please type it in.")
        if len(text) > MAX_OCR_TEXT:
            raise AppError(422, "POSTER_OCR_TOO_LONG", "The recognized text is too long.")
        return text
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
