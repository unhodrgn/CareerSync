"""What the interview cuts out of a model's input, best effort: age, gender and military-service information (docs/DECISIONS.md D59, D61, D62).

A leaf module on purpose (it imports nothing of the interview package), so every layer uses the same policy: the CV
boundary (`cv_context.py`), the plan validator, the guards, and the model-input boundary (`boundary.py`). The vocabulary
itself (`is_sensitive`, `strip_sensitive`, `cut_sensitive`) lives in `ai/guardrails/sensitive.py`, shared with the CV
cleaner (D85), and is re-exported here. This vocabulary
is the last of several layers, not the only one: the CV is first cut by its structure (`clean_cv`), a plan is
validated before it is used (`validate.py`), and text for a model only ever leaves through `for_model` / `SafeText`.

What it is: a list of terms, applied sentence by sentence and then clause by clause, so a mixed sentence ("27살이고 Java로
API를 개발했습니다") keeps its professional clause. What it is not: understanding. A disclosure that uses none of the
terms passes (docs/PROJECT_DOCUMENTATION.md §6.2 lists what is known to pass). Over-blocking is accepted: the terms skip
common compounds that are not about a person (3세대, 세션, 나이브 베이즈, 나이스, 제대로, 전역 변수, 연령대별, 사단법인).
"""
from dataclasses import dataclass

from ai.guardrails.sensitive import cut_sensitive, is_sensitive, strip_sensitive  # noqa: F401  (re-exported for the interview package)


def for_model(text: str | None) -> str:
    """The only form in which interview text may be put into a model's input: what touches these topics left out, angle
    brackets neutralized so the text cannot close a tag of the prompt, one line. Idempotent."""
    return strip_sensitive(text or "").replace("<", "‹").replace(">", "›").strip()


def for_model_block(text: str | None) -> str:
    """`for_model` for text with its own line structure (a job description): each line on its own, empty lines dropped."""
    return "\n".join(line for line in (for_model(raw) for raw in (text or "").splitlines()) if line)


@dataclass(frozen=True)
class SafeText:
    """One line of text that may be put into a model's input. Only `safe_text` makes one from arbitrary text, and the
    constructor refuses anything `for_model` would still change, so there is no way to wrap raw text in it."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or for_model(self.value) != self.value:
            raise ValueError("SafeText holds text that went through for_model; build it with safe_text()")

    def __str__(self) -> str:
        return self.value

    def __bool__(self) -> bool:
        return bool(self.value)


def safe_text(raw: str | None) -> SafeText:
    return SafeText(for_model(raw))
