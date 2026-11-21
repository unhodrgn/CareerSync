"""Checks every line the interviewer may say, and every analysis the engine accepts (docs/DECISIONS.md D51, D54).

A spoken line passes only when it has no URL, email, placeholder or code fence, no verdict word (AI rule 5: the AI never
says who passes), nothing about age, gender or military service (`sensitive.py`), and nothing either blocklist matches (the criteria guardrail and the interview blocklist of D21,
through `ai.career.interview.allowed`). Over-blocking is acceptable: the caller then falls back to a fixed line.

Evidence follows AI rule 4: a quote in an analysis must appear in the masked answer (`verify_quotes`), and a rubric
point id must belong to the item, or the engine drops it.
"""
import re
from collections.abc import Iterable, Sequence
from dataclasses import replace
from difflib import SequenceMatcher
from typing import Literal

from ai.career.interview import _URL, allowed
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.evidence import verify_quotes
from ai.interview.sensitive import is_sensitive, strip_sensitive  # noqa: F401  (strip_sensitive stays importable from here)
from ai.interview.types import DUPLICATE_RATIO, LEVEL_RANK, PlanItem, TurnAnalysis

# Words the interviewer never says: no verdict, no score, nothing about hiring (the PoC list, kept as is)
VERDICT_WORDS = ("합격", "불합격", "탈락", "점수", "채용", "선발", "뽑")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MAX_QUESTION_CHARS = 300  # D21 allows questions up to 300 characters
MAX_STATEMENT_CHARS = 200
MAX_CLOSING_CHARS = 240
MAX_QUOTES = 2
MAX_QUOTE_CHARS = 120

LineKind = Literal["question", "statement", "closing"]

_WRAPPERS = {'"': '"', "'": "'", "“": "”", "‘": "’", "`": "`"}


def _clean(text: str) -> str:
    """Whitespace collapsed; one pair of quotes that wraps the whole line removed. A quote that only starts the line is
    content (the D21 template begins with '<criterion>'와(과) …), so it stays."""
    line = " ".join((text or "").split())
    if len(line) >= 2 and _WRAPPERS.get(line[0]) == line[-1]:
        line = line[1:-1].strip()
    return line


def screen_spoken(text: str, blocklists: Sequence[Blocklist], kind: LineKind = "statement") -> str | None:
    """The cleaned line when it passes every check, else None (the caller speaks a fixed line instead)."""
    if "```" in (text or ""):  # code is never spoken; checked before cleaning, which strips quote and backtick characters
        return None
    line = _clean(text)
    limit = {"question": MAX_QUESTION_CHARS, "statement": MAX_STATEMENT_CHARS, "closing": MAX_CLOSING_CHARS}[kind]
    if not line or len(line) > limit:
        return None
    if "[" in line or "]" in line:  # a placeholder (masked data) must never be spoken
        return None
    if _URL.search(line) or _EMAIL.search(line):
        return None
    if kind == "closing" and ("?" in line or "？" in line):
        return None
    if any(word in line for word in VERDICT_WORDS):
        return None
    if is_sensitive(line):  # the interviewer never asks about or mentions age, gender or military service (D59, D62)
        return None
    if not allowed(line, "", (), blocklists):
        return None
    return line


def _normal(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def is_duplicate(text: str, earlier: Iterable[str], ratio: float = DUPLICATE_RATIO) -> bool:
    """True when `text` equals a line in `earlier` (spacing, case and punctuation are ignored), or, with `ratio` below 1,
    closely resembles one. Use the default ratio for wording a model chose freely (an LLM rephrases a question it
    already asked) and `ratio=1.0` for template lines: two templates that differ only in the criterion name are
    similar by construction and are different questions."""
    new = _normal(text)
    if not new:
        return True
    for old in map(_normal, earlier):
        if new == old or (ratio < 1.0 and old and SequenceMatcher(None, new, old, autojunk=False).ratio() >= ratio):
            return True
    return False


def verified_quotes(quotes: Iterable[str], text: str) -> tuple[str, ...]:
    """The quotes that really appear in `text` (the masked answer), at most MAX_QUOTES, none longer than MAX_QUOTE_CHARS,
    none that matches the age, gender and military-service vocabulary (a quote is kept in the analysis and may be read
    again later, so a disclosure the candidate made is not carried along as evidence)."""
    short = [q for q in quotes if len(q.strip()) <= MAX_QUOTE_CHARS and not is_sensitive(q)]
    return tuple(verify_quotes(short, text)[:MAX_QUOTES])


def sanitize_analysis(
    analysis: TurnAnalysis, item: PlanItem, answer: str, asked: Iterable[str], blocklists: Sequence[Blocklist]
) -> TurnAnalysis:
    """An analysis the engine can trust: unknown rubric points and unverifiable quotes dropped, a suggested follow-up kept
    only when it passes the screens and repeats nothing. Whatever produced `analysis`, this is the one gate."""
    ids = {p.id for p in item.rubric}
    points = {pid: level for pid, level in analysis.points.items() if pid in ids and level in LEVEL_RANK}
    follow_up = None
    if analysis.suggested_follow_up:
        line = screen_spoken(analysis.suggested_follow_up, blocklists, "question")
        if line is not None and not is_duplicate(line, asked):
            follow_up = line
    return replace(analysis, points=points, quotes=verified_quotes(analysis.quotes, answer), suggested_follow_up=follow_up)
