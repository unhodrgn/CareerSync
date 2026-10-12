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
