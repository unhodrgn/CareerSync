"""Find the CV passages most relevant to a criterion (the R in the scorer's RAG step)."""
import re
from dataclasses import dataclass

from ai.embedding.model import Embedder, cosine
from ai.parsing.sections import Chunk, chunk_sections, heading_key, split_sections

# Generic words that say nothing about the content (D27: 직무, 본인, 역할 added)
_STOP = {
    "경험", "능력", "역량", "관련", "있는", "및", "또는", "등", "the", "and", "with", "for", "of", "a", "to", "보유", "활용", "이해",
    "직무", "본인", "역할",
}


def keywords(text: str) -> list[str]:
    words = re.findall(r"[0-9a-z가-힣+#.]{2,}", text.lower())
    out = []
    for w in words:
        # A trailing period ends a sentence ("경험."); inner ones stay ("node.js")
        w = w.rstrip(".")
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


# Masked personal data (ai/parsing/pii.py) and contact labels: a chunk with nothing else is no evidence (issue 32)
_PII_TOKEN = re.compile(r"\[(?:이름|이메일|전화번호|주소|생년월일|링크|주민번호)\]")
_CONTACT_LABEL = re.compile(
    r"성명|이름|연락처|이메일|e-?mail|휴대\s*(?:폰|전화)|핸드폰|전화\s*번호|전화|phone|mobile|tel|주소|address|생년월일|"
    r"birth(?:day)?|링크|github|blog|블로그|포트폴리오|portfolio",
    re.IGNORECASE,
)


def has_content(text: str) -> bool:
    """False for a chunk of section headings, masked personal data and contact labels only."""
    if all(heading_key(line) is not None for line in text.splitlines() if line.strip()):
        return False
    rest = _CONTACT_LABEL.sub(" ", _PII_TOKEN.sub(" ", text))
    return bool(re.search(r"[0-9a-z가-힣]{2,}", rest.lower()))


def cv_chunks(text: str) -> list[Chunk]:
    """Retrieval candidates for scoring, the LLM rubric and interview excerpts; contact/heading-only chunks left out."""
    return [c for c in chunk_sections(split_sections(text)) if has_content(c.text)]


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
