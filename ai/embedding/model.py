"""Text embeddings for skill similarity and CV retrieval.

Default: intfloat/multilingual-e5-base through sentence-transformers (Korean + English, CPU).
When sentence-transformers or the model weights are unavailable (tests, offline machines), a
character n-gram hashing embedder is used instead; it catches spelling variants but not meaning.
"""
import hashlib
import logging
import math
import os
import re
from functools import lru_cache
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL = "intfloat/multilingual-e5-base"


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        """Unit-length vectors. kind is "query" or "passage" (e5 uses different prefixes)."""
        ...


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class E5Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device="cpu")
        self.name = model_name

    def embed(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        prefix = "query: " if kind == "query" else "passage: "
        vectors = self._model.encode([prefix + t for t in texts], normalize_embeddings=True)
        return [v.tolist() for v in vectors]


class HashingEmbedder:
    """Character 2-3 gram hashing into a fixed space. Deterministic, no dependencies."""

    name = "hashing-ngram-v1"

    def __init__(self, dims: int = 1024):
        self.dims = dims

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        words = re.findall(r"[0-9a-z가-힣+#.]+", text.lower())
        for word in words:
            padded = f" {word} "
            for n in (2, 3):
                for i in range(len(padded) - n + 1):
                    h = int.from_bytes(hashlib.blake2b(padded[i : i + n].encode(), digest_size=4).digest(), "little")
                    vec[h % self.dims] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        return [self._vector(t) for t in texts]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    if name == HashingEmbedder.name:
        return HashingEmbedder()
    try:
        return E5Embedder(name)
    except Exception as e:  # noqa: BLE001  (missing package, no network for weights, ...)
        log.warning("Embedding model %s unavailable (%s); using %s", name, e, HashingEmbedder.name)
        return HashingEmbedder()
