"""Find the CV passages most relevant to a criterion (the R in the scorer's RAG step)."""
import re
from dataclasses import dataclass

from ai.embedding.model import Embedder, cosine
from ai.parsing.sections import Chunk, chunk_sections, split_sections

_STOP = {"경험", "능력", "역량", "관련", "있는", "및", "또는", "등", "the", "and", "with", "for", "of", "a", "to", "보유", "활용", "이해"}


def keywords(text: str) -> list[str]:
    words = re.findall(r"[0-9a-z가-힣+#.]{2,}", text.lower())
    out = []
    for w in words:
        # Drop common Korean particles at the end of a word
        w = re.sub(r"(을|를|이|가|은|는|의|에|에서|으로|로|와|과|한|하는|된)$", "", w)
        if len(w) >= 2 and w not in _STOP and w not in out:
            out.append(w)
    return out


@dataclass(frozen=True)
class Passage:
    chunk: Chunk
    similarity: float  # cosine, -1..1
    coverage: float  # share of query keywords present, 0..1

    @property
    def relevance(self) -> float:
        return 0.5 * max(self.similarity, 0.0) + 0.5 * self.coverage


def cv_chunks(text: str) -> list[Chunk]:
    return chunk_sections(split_sections(text))


def retrieve(query: str, chunks: list[Chunk], embedder: Embedder, k: int = 4, prefer: tuple[str, ...] = ()) -> list[Passage]:
    if not chunks:
        return []
    qv = embedder.embed([query], kind="query")[0]
    cvs = embedder.embed([c.text for c in chunks], kind="passage")
    kws = keywords(query)
    passages = []
    for chunk, vec in zip(chunks, cvs, strict=True):
        low = chunk.text.lower()
        coverage = sum(1 for w in kws if w in low) / len(kws) if kws else 0.0
        sim = cosine(qv, vec)
        if chunk.section in prefer:
            sim += 0.05
        passages.append(Passage(chunk, sim, coverage))
    passages.sort(key=lambda p: p.relevance, reverse=True)
    return passages[:k]


def best_lines(passage_text: str, query: str, n: int = 2) -> list[str]:
    """The lines of a passage that share the most keywords with the query."""
    kws = keywords(query)
    lines = [l.strip() for l in passage_text.splitlines() if len(l.strip()) >= 4]
    scored = sorted(((sum(1 for w in kws if w in l.lower()), -i, l) for i, l in enumerate(lines)), reverse=True)
    return [l for hits, _, l in scored[:n] if hits > 0]
