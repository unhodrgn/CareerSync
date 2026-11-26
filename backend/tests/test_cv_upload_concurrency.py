"""A slow CV upload (PDF, LLM) must not block other requests: upload_cv runs in the threadpool."""
import threading
import time

from ai.llm.client import LLMError
from ai.tests.helpers import SAMPLE_CV, make_pdf
from app.services import ai_runtime

BLOCK_SECONDS = 5


class BlockingLLM:
    """Holds the upload inside `complete_json` until released, then fails so the rules fallback runs."""

    model = "blocking-llm"

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.released = None

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.entered.set()
        self.released = self.release.wait(BLOCK_SECONDS)
        raise LLMError("blocking fake")


def test_other_requests_are_served_while_an_upload_runs(client, world, monkeypatch):
    llm = BlockingLLM()
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    result = {}

    with client:  # one event loop for all requests, as in uvicorn
        def upload():
            files = {"file": ("cv.pdf", make_pdf(SAMPLE_CV), "application/pdf")}
            result["response"] = client.post("/api/cv", files=files, headers=world["seeker"])

        uploader = threading.Thread(target=upload)
        uploader.start()
        try:
            assert llm.entered.wait(BLOCK_SECONDS), "upload never reached the LLM call"
            start = time.monotonic()
            health = client.get("/health")
            elapsed = time.monotonic() - start
        finally:
            llm.release.set()
            uploader.join(BLOCK_SECONDS * 2)

    assert health.status_code == 200
    assert elapsed < 1, f"/health waited {elapsed:.1f}s for the upload"
    assert llm.released is True, "the upload was not released by the test (event loop was blocked)"
    assert result["response"].status_code == 201


def test_cv_update_locks_document_and_queries_max_version(client, db, world):
    from sqlalchemy import event

    from ai.parsing.profile import CvProfile as ProfileData
    from app.models import CvProfile, User
    from app.services import cv_service

    files = {"file": ("cv.pdf", make_pdf(SAMPLE_CV), "application/pdf")}
    created = client.post("/api/cv", files=files, headers=world["seeker"]).json()
    p1 = db.get(CvProfile, created["id"])
    # Preload `p1.document.profiles` in memory, then slip a version 2 row straight into DB to simulate a parallel commit
    _ = list(p1.document.profiles)
    db.add(CvProfile(cv_document_id=p1.cv_document_id, seeker_id=p1.seeker_id, version=2, schema_version=p1.schema_version, method="seeker"))
    db.commit()

    statements: list[str] = []
    listener = lambda _conn, _cur, stmt, *_rest: statements.append(stmt)
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        saved = cv_service.update(db, db.get(User, p1.seeker_id), p1.id, ProfileData.model_validate(created["profile"]), True)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)

    assert saved.version == 3
    assert any("FOR UPDATE" in s.upper() for s in statements) or db.get_bind().dialect.name == "sqlite"
