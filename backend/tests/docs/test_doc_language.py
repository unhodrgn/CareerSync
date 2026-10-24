"""Markdown docs are English (docs/DECISIONS.md D40): no Vietnamese in the guarded docs, code blocks included. Korean
stays allowed (product and UI terms, law names, the README's Korean summary). Vietnamese is recognized by letters the
docs have no other use for: ă â đ ê ô ơ ư ĩ ũ and the precomposed vowels with a dot below, hook or horn
(U+1EA0–U+1EF9). Letters shared with French or Spanish (é, à, ã, …) pass, so "résumé" is fine. Lines are read in NFC,
so a decomposed letter (o + combining marks) counts too. Excluded like every guard: docs/archive/, AUDIT_REPORT.md,
ai/prompts/ (markdown.EXCLUDED)."""
import re
import unicodedata

from .markdown import Doc, guarded_docs, report

VIETNAMESE = frozenset("ăâđêôơưĩũĂÂĐÊÔƠƯĨŨ") | frozenset(chr(c) for c in range(0x1EA0, 0x1EFA))
WORD = re.compile(r"\S+")
PUNCT = "*_`()[]{},.;:!?\"'“”‘’"
SHOWN = 3  # words quoted per line in the message


def vietnamese_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    return [w.strip(PUNCT) for w in WORD.findall(text) if any(ch in VIETNAMESE for ch in w)]


def language_problems(docs: list[Doc]) -> list[str]:
    problems = []
    for doc in docs:
        for line, text in doc.numbered():
            if words := vietnamese_words(text):
                shown = ", ".join(repr(w) for w in words[:SHOWN])
                more = f" (+{len(words) - SHOWN} more)" if len(words) > SHOWN else ""
                problems.append(
                    f"{doc.rel}:{line} has Vietnamese text: {shown}{more}. Markdown docs are English (docs/DECISIONS.md D40): "
                    f"translate the line; Korean terms stay, with an English gloss at first use."
                )
    return problems


def test_docs_are_english():
    problems = language_problems(guarded_docs())
    assert not problems, report(problems)
