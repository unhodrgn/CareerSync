"""Evidence check: every quote an LLM gives must actually appear in the (masked) CV text."""
import re
from difflib import SequenceMatcher

MIN_RATIO = 0.9
MIN_QUOTE_CHARS = 4

_WS = re.compile(r"\s+")


def _squash(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def quote_in_text(quote: str, text: str, min_ratio: float = MIN_RATIO) -> bool:
    q, t = _squash(quote), _squash(text)
    if len(q) < MIN_QUOTE_CHARS:
        return False
    if q in t:
        return True
    n = len(q)
    step = max(1, n // 4)
    for i in range(0, max(1, len(t) - n + 1), step):
        window = t[i : i + n + step]
        if SequenceMatcher(None, q, window, autojunk=False).ratio() >= min_ratio:
            return True
    return False


def verify_quotes(quotes: list[str], text: str, min_ratio: float = MIN_RATIO) -> list[str]:
    """The quotes that appear in text, deduplicated, in the given order."""
    out = []
    for q in quotes:
        q = q.strip()
        if q and q not in out and quote_in_text(q, text, min_ratio):
            out.append(q)
    return out
