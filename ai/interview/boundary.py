"""The one model-input boundary of the practice interview (docs/DECISIONS.md D61).

Everything the interview sends to a model, for planning, for the answer of one turn and (later) for the feedback, is a
`ModelInput`, and the only way to make one is `compose`, which takes `SafeText` parts (`sensitive.SafeText`: text that went
through `for_model`) and renders the tags itself. The only way to call a model with one is `ask`. So a caller cannot put a
raw transcript line, a raw plan field or a raw CV line into a request: a plain string is refused by `compose`, and
`SafeText` refuses a string that `for_model` would still change.

What this guarantees: text that reaches a model through this module has had every sentence or clause that matches the
vocabulary of `sensitive.py` taken out, and angle brackets neutralized. What it does not: it cannot recognize a disclosure
that uses none of the vocabulary, and it cannot stop code that calls a model some other way. That second part is covered by
the architecture tests (`ai/tests/test_interview_model_boundary.py`), which list every place in `ai/` and `backend/app/`
that calls or acquires a model client and fail when a new one appears.

No provider, no network: the call itself is the injected `LLMClient`'s (or, for the realtime agent, the agent's own call,
made with the `system` and `user` of a `ModelInput` and nothing else).
"""
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ai.interview.sensitive import SafeText, is_sensitive, safe_text
from ai.llm.client import LLMClient

_SEAL = object()  # only `compose` holds it; the architecture test fails if another module refers to it
_TAG = re.compile(r"^<(/?)([a-z_]{1,24})>$")
Section = tuple[str | None, Sequence[SafeText]]  # (tag or None, lines)


@dataclass(frozen=True)
class ModelInput:
    """What may be sent to a model. Built by `compose` only; `system` is a static prompt, `user` is made of SafeText."""

    purpose: str  # "turn" | "rubric" | "plan" | "feedback": for logs and the architecture test, never for text
    system: str
    user: str
    schema: type[BaseModel]
    max_tokens: int
    seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.seal is not _SEAL:
            raise TypeError("a ModelInput is built by boundary.compose only")
        if is_sensitive(self.user):  # a seam between two clean lines that matches on its own: refuse rather than send
            raise ValueError("the model input still matches the age, gender or military-service vocabulary")


def render(sections: Iterable[Section]) -> str:
    """The text of the sections: each tagged section as <tag>, its lines, </tag>; an untagged one as its lines."""
    lines: list[str] = []
    for tag, items in sections:
        if tag is not None:
            lines.append(f"<{tag}>")
        lines.extend(item.value for item in items)
        if tag is not None:
            lines.append(f"</{tag}>")
    return "\n".join(lines)


def compose(purpose: str, system: str, sections: Iterable[Section], schema: type[BaseModel], max_tokens: int) -> ModelInput:
    """A `ModelInput` from SafeText parts. A part that is not SafeText, or a tag that is not a plain name, is refused."""
    checked: list[Section] = []
    for tag, items in sections:
        if tag is not None and not re.fullmatch(r"[a-z_]{1,24}", tag):
            raise ValueError(f"not a plain tag name: {tag!r}")
        parts = tuple(items)
        if not all(isinstance(p, SafeText) for p in parts):
            raise TypeError("a model input is made of SafeText only; use safe_text() on the raw text")
        checked.append((tag, parts))
    return ModelInput(purpose, system, render(checked), schema, max_tokens, seal=_SEAL)


def ask(llm: LLMClient, model_input: ModelInput) -> Any:
    """Send one `ModelInput` through an injected client. The one call of `complete_json` in the interview package."""
    if not isinstance(model_input, ModelInput) or model_input.seal is not _SEAL:
        raise TypeError("only a ModelInput built by boundary.compose may be sent to a model")
    return llm.complete_json(model_input.system, model_input.user, model_input.schema, model_input.max_tokens)


def sections_of(user: str, tags: frozenset[str]) -> list[Section]:
    """Split a prompt that was assembled as text (the D21 planning prompt) into its tagged sections, every other line cut
    through `safe_text`. Only a line that is exactly one of `tags` opens or closes a section."""
    sections: list[Section] = []
    tag: str | None = None
    lines: list[SafeText] = []
    for raw in user.splitlines():
        m = _TAG.match(raw.strip())
        if m and m.group(2) in tags:
            closing, name = bool(m.group(1)), m.group(2)
            if not closing and tag is None:
                if lines:
                    sections.append((None, lines))
                tag, lines = name, []
                continue
            if closing and tag == name:
                sections.append((tag, lines))
                tag, lines = None, []
                continue
        if line := safe_text(raw):
            lines.append(line)
    if tag is not None or lines:
        sections.append((tag, lines))
    return sections


class GatedClient:
    """An `LLMClient` that sends only what passed the boundary. It wraps the real client for code that builds its own prompt
    as text, namely `ai.career.interview.make_questions` (the D21 planner, reused by the interview plan): every line of the
    prompt is cut again and the request is made with `ask`."""

    def __init__(self, llm: LLMClient, purpose: str = "plan", tags: Iterable[str] = ("job", "criteria", "cv_excerpts")) -> None:
        self._llm, self._purpose, self._tags = llm, purpose, frozenset(tags)
        self.model = getattr(llm, "model", "unknown")

    def complete_json(self, system: str, user: str, schema: type[BaseModel], max_tokens: int = 4000) -> Any:
        model_input = compose(self._purpose, system, sections_of(user, self._tags), schema, max_tokens)
        return ask(self._llm, model_input)
