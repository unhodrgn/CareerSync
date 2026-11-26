"""Local OCR for company hiring posters. The uploaded bytes are deleted after recognition."""
import os
import subprocess
import tempfile

from app.core.errors import AppError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_OCR_TEXT = 10_000


def extract_text(data: bytes, mime: str | None) -> str:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise AppError(422, "POSTER_SIZE", "이미지는 5MB 이하로 업로드해 주세요.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix, expected = ".png", "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        suffix, expected = ".jpg", "image/jpeg"
    else:
        raise AppError(422, "POSTER_FORMAT", "PNG 또는 JPEG 이미지만 업로드해 주세요.")
    if mime not in (None, expected, "application/octet-stream"):
        raise AppError(422, "POSTER_FORMAT", "이미지 파일의 형식이 일치하지 않습니다.")
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
            raise AppError(503, "POSTER_OCR_UNAVAILABLE", "이미지 글자 인식 서비스를 사용할 수 없습니다.") from exc
        if result.returncode:
            raise AppError(422, "POSTER_OCR_FAILED", "이미지에서 글자를 추출하지 못했습니다.")
        text = result.stdout.strip()
        if not text:
            raise AppError(422, "POSTER_OCR_EMPTY", "인식한 글자가 없습니다. 직접 입력해 주세요.")
        if len(text) > MAX_OCR_TEXT:
            raise AppError(422, "POSTER_OCR_TOO_LONG", "인식한 텍스트가 너무 깁니다.")
        return text
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
