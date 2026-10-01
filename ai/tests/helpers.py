from pathlib import Path

import pymupdf

from ai.embedding.model import HashingEmbedder
from ai.embedding.skills import load_dictionary

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CV = (FIXTURES / "sample_cv.txt").read_text(encoding="utf-8")
SKILLS = load_dictionary()
EMBEDDER = HashingEmbedder()


def make_pdf(text: str, pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((50, 60), text, fontname="korea", fontsize=10)
    return doc.tobytes()


class FakeLLM:
    """Returns queued responses in order and records every prompt it was sent."""

    model = "fake-llm"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls.append((system, user))
        if not self.responses:
            from ai.llm.client import LLMError

            raise LLMError("no response queued")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return schema.model_validate(r)
