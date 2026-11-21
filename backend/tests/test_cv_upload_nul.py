"""A U+0000 in a CV upload is dropped before anything is stored, never refused (D74).

PostgreSQL text cannot hold the character, SQLite can, so an upload whose file name or extracted text had one passed every SQLite test and
would fail on PostgreSQL with a raw database error and no CV. Two ways in: the `filename` of the multipart part (Starlette hands a raw NUL byte
through) and the text of the PDF (no step of extraction, masking or structuring removes it). The API contract is unchanged: 201 and the same
body, no new error. Neither path can carry a lone surrogate (invalid bytes in a file name become Latin-1 characters, and MuPDF gives U+FFFD for
a surrogate glyph), so only the NUL is dropped. Nothing here is PostgreSQL-only: with `TEST_DATABASE_URL` set the same tests run on it."""
import pytest

from ai.parsing.pdf import PdfText
from ai.tests.helpers import SAMPLE_CV, make_pdf
from app.models import CvDocument
from app.services import cv_service

from .test_applications_api import seeker, upload

NUL = "\x00"


def post_named(client, headers, raw_name: bytes):
    """The multipart body written by hand: the test client writes a NUL in a file name as %00, and the server would never see the byte."""
    body = b'--b\r\nContent-Disposition: form-data; name="file"; filename="' + raw_name + b'"\r\nContent-Type: application/pdf\r\n\r\n'
    body += make_pdf(SAMPLE_CV) + b"\r\n--b--\r\n"
    return client.post("/api/cv", content=body, headers={**headers, "Content-Type": "multipart/form-data; boundary=b"})


@pytest.mark.parametrize(
    "raw_name, stored",
    [
        (b"cv\x00.pdf", "cv.pdf"),
        (b"\x00cv.pdf", "cv.pdf"),
        (b"cv.pdf\x00", "cv.pdf"),
        ("이력서\x00_최종.pdf".encode(), "이력서_최종.pdf"),  # the rest of the name is kept as it was
        (b"a\x00b\x00c.pdf", "abc.pdf"),
        (b"\x00\x00", "cv.pdf"),  # nothing left: the name every upload without one gets
        (b"cv.pdf", "cv.pdf"),
    ],
    ids=["inside", "first", "last", "korean", "several", "only NULs", "no NUL"],
)
def test_a_nul_in_the_file_name_is_dropped_and_the_cv_is_stored(client, db, raw_name, stored):
    h = seeker(db, "nul-name@seeker.test", "김지원")
    r = post_named(client, h, raw_name)
    assert r.status_code == 201, r.text  # not a 422 and not a 500
    assert r.json()["file_name"] == stored
    assert db.get(CvDocument, r.json()["document_id"]).file_name == stored


def test_the_file_name_is_cut_to_255_characters_after_the_NULs_are_dropped(client, db):
    h = seeker(db, "nul-long@seeker.test", "김지원")
    r = post_named(client, h, b"a\x00" * 300)  # cut first, this would leave 128 characters
    assert r.status_code == 201, r.text
    assert r.json()["file_name"] == "a" * 255


def test_a_nul_in_the_extracted_text_is_dropped_before_the_cv_is_masked_and_structured(client, db, monkeypatch):
    dirty = SAMPLE_CV.replace("Spring", f"Spr{NUL}ing")  # a PDF whose text layer has the character inside a word
    assert NUL in dirty
    monkeypatch.setattr(cv_service, "extract_text", lambda data: PdfText(text=dirty, pages=1))  # the extractor is patched: no PDF is known to give one
    h = seeker(db, "nul-text@seeker.test", "김지원")
    r = upload(client, h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "Spring" in body["profile"]["skills"]  # dropped before structuring: the word is whole again, so it is found
    assert NUL not in db.get(CvDocument, body["document_id"]).masked_text and "\\u0000" not in r.text
    assert "Java" in body["profile"]["skills"] and body["profile"]["experiences"]  # the rest of the CV is read as before


def test_a_cv_without_a_nul_is_stored_as_it_was(client, db):
    h = seeker(db, "nul-none@seeker.test", "김지원")
    body = upload(client, h).json()
    assert body["file_name"] == "cv.pdf" and "Spring" in body["profile"]["skills"]
