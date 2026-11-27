"""The model-independent LLM layer of the practice interview (docs/DECISIONS.md D52, D54, D59).

No provider, no socket, no SDK: this module only prepares what a model may see, and checks what comes back. The model
call itself belongs to the caller, so the backend can use the `LLMClient` gateway and the Interview Agent its own async
Groq call (D52) with the same rules:

    request = prepare_turn(engine, transcript)         # None: the rules handle this answer, do not call a model
    raw = ...call a model with request.system / request.user, within the deadline, in the caller's own way...
    turn = parse_turn(request, raw, method="llm:<model>")      # turn.analysis is None whenever anything is wrong
    action = engine.on_answer(transcript, now, turn.analysis)  # None: the engine uses its rules (D54)

`analyze_turn` does all three for an injected `LLMClient` (the sync path; tests use `FakeLLM`). Each of the three steps
fails safe: a failed call, an invalid answer or an unverifiable quote means no model analysis and the deterministic
rules, never a guess.

What a model sees is exactly `engine.turn_context()` (masked text and the plan's own words), minus what the vocabulary of
`sensitive.py` matches (sentences, or the clauses of a mixed sentence) about age, gender or military service, with angle
brackets neutralized so an answer cannot close a tag. A request is a `ModelInput` made by `boundary.compose` from SafeText
parts, and the only call is `boundary.ask` (D61). What a model may say is narrow: how the answer relates to the rubric, at most two verbatim quotes, and one suggested follow-up. It
cannot call an answer empty or short, cannot ask for a repeat, cannot change a limit or a transition: those stay with the
rules and the state machine.

Not wired anywhere yet, by decision: the rubric request and parser at the end (plan-time enrichment is a later step).
"""
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from ai.guardrails.blocklist import Blocklist
from ai.guardrails.evidence import MIN_QUOTE_CHARS, verify_quotes
from ai.interview import rules
from ai.interview.boundary import ModelInput, ask, compose
from ai.interview.engine import InterviewEngine
from ai.interview.guards import MAX_QUOTE_CHARS, MAX_QUOTES, is_duplicate, screen_spoken
from ai.interview.sensitive import for_model, is_sensitive, safe_text
from ai.interview.types import (
    IMPORTANCE_RANK,
    MAX_RUBRIC_POINTS,
    MIN_RUBRIC_POINTS,
    STRUCTURAL_ANSWER_TYPES,
    AnswerType,
    Phase,
    RubricPoint,
    TurnAnalysis,
    TurnContext,
)
from ai.llm.client import LLMClient
from ai.parsing.extract import PROMPT_DIR

log = logging.getLogger(__name__)

TURN_PROMPT = "interview_turn.md"
RUBRIC_PROMPT = "interview_rubric.md"
TURN_MAX_TOKENS = 800
RUBRIC_MAX_TOKENS = 600
MAX_FOLLOW_UP_CHARS = 150
_STRICT = ConfigDict(extra="forbid", strict=True)  # no extra fields, no coercion: the model fills the schema or fails it


@lru_cache(maxsize=None)
def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


_flat = for_model  # the one exit for text that goes to a model (sensitive.py)


# ── The turn: what a model may say ──


class PointJudgement(BaseModel):
    model_config = _STRICT
    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8)]
    level: Literal["demonstrated", "partial", "not_shown"]


class TurnLlmOut(BaseModel):
    """The only shape a model may answer in. Four answer types, not eight: empty, too short and a request to hear the
    question again are decided by the rules before a model is asked (and never by a model)."""

    model_config = _STRICT
    answer_type: Literal["answered", "partial", "off_topic", "dont_know"]
    points: list[PointJudgement] = Field(default_factory=list, max_length=MAX_RUBRIC_POINTS)
    quotes: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=MIN_QUOTE_CHARS, max_length=MAX_QUOTE_CHARS)]] = Field(
        default_factory=list, max_length=MAX_QUOTES
    )
    follow_up: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_FOLLOW_UP_CHARS)] | None = None


@dataclass(frozen=True)
class TurnRequest:
    """What to send (`model_input`: system, user, schema, max tokens) and what the answer is checked against (the rest,
    never sent)."""

    model_input: ModelInput
    rubric_ids: tuple[str, ...]
    answer: str  # the answer exactly as the model saw it; a quote must be found in it
    asked: tuple[str, ...]
    blocklists: tuple[Blocklist, ...]

    @property
    def system(self) -> str:
        return self.model_input.system

    @property
    def user(self) -> str:
        return self.model_input.user

    @property
    def schema(self) -> type[TurnLlmOut]:
        return self.model_input.schema  # type: ignore[return-value]

    @property
    def max_tokens(self) -> int:
        return self.model_input.max_tokens


@dataclass(frozen=True)
class LlmTurn:
    """The outcome for one turn. `analysis` is None whenever the rules must decide, and `reason` says why (codes only,
    never text of the interview): ok, rules_only, llm_error, invalid_type, invalid_json, schema, duplicate_point,
    unknown_point, missing_point, inconsistent or invented_quote. `dropped` names parts of a valid answer left out."""

    analysis: TurnAnalysis | None
    reason: str
    dropped: tuple[str, ...] = ()


def scrub_context(context: TurnContext) -> TurnContext | None:
    """The model view of a turn context, or None when nothing meaningful is left (the question or the answer was only
    about age, gender or military service): then no model is asked and the rules analyse the answer."""
    question, answer = _flat(context.question), _flat(context.answer)
    if not question or not answer:
        return None
    return replace(
        context,
        question=question,
        criterion_name=_flat(context.criterion_name) or None,
        rubric=tuple((pid, _flat(text) or "(excluded)") for pid, text in context.rubric),
        answer=answer,
        previous=tuple(line for line in map(_flat, context.previous) if line),
        asked=tuple(line for line in map(_flat, context.asked) if line),
    )


def prepare_turn(engine: InterviewEngine, text: str) -> TurnRequest | None:
    """The request for the answer the engine is waiting for, or None when no model should be asked: no question is
    waiting, the rules already classify the answer (empty, very short, a request to hear it again), or the answer is only
    about age, gender or military service. The input is `engine.turn_context()` and nothing else."""
    state = engine.state
    item = state.current
    if state.phase is not Phase.LISTENING or item is None:
        return None
    context = scrub_context(engine.turn_context(text))
    if context is None:
        return None
    # Judged on what the model would see. The cuts only remove text, so an answer the rules classify as empty, very short
    # or a request to hear the question again stays that way; one that is too thin only after the cuts is caught too. The
    # engine's rules still read the full text.
    if rules.analyze(context.answer, item).answer_type in STRUCTURAL_ANSWER_TYPES:
        return None
    try:
        model_input = compose("turn", _prompt(TURN_PROMPT), context.sections(), TurnLlmOut, TURN_MAX_TOKENS)
    except ValueError:  # the cut text still matches the vocabulary across a seam: no model is asked, the rules decide
        return None
    return TurnRequest(
        model_input=model_input,
        rubric_ids=tuple(p.id for p in item.rubric),
        answer=context.answer,
        asked=context.asked,
        blocklists=engine.blocklists,
    )


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _load(raw: Any, schema: type[BaseModel]) -> tuple[Any, str]:
    """(validated model, "") or (None, reason). Accepts the model object, a dict, or JSON text (one code fence tolerated)."""
    if isinstance(raw, schema):
        return raw, ""
    if isinstance(raw, bytes | bytearray):
        raw = bytes(raw).decode("utf-8", "replace")
    if isinstance(raw, str):
        text = raw.strip()
        if m := _FENCE.match(text):
            text = m.group(1)
        try:
            data = json.loads(text)
        except ValueError:
            return None, "invalid_json"
    elif isinstance(raw, dict):
        data = raw
    else:
        return None, "invalid_type"
    try:
        return schema.model_validate(data), ""
    except ValidationError:
        return None, "schema"


def parse_turn(request: TurnRequest, raw: Any, *, method: str = "llm") -> LlmTurn:
    """Check a model's answer against the request. Anything wrong with the answer as a whole returns no analysis (the rules
    decide); a follow-up that fails a screen is dropped on its own, since the template then speaks instead."""
    out, reason = _load(raw, request.schema)
    if out is None:
        return LlmTurn(None, reason)
    kind = out.answer_type
    ids = [p.id for p in out.points]
    if len(set(ids)) != len(ids):
        return LlmTurn(None, "duplicate_point")
    if not set(ids) <= set(request.rubric_ids):
        return LlmTurn(None, "unknown_point")  # an invented rubric id: the model is not following the input
    if kind in ("off_topic", "dont_know"):
        if out.points or out.quotes:
            return LlmTurn(None, "inconsistent")
    else:
        if set(ids) != set(request.rubric_ids):
            return LlmTurn(None, "missing_point")
        levels = {p.level for p in out.points}
        if (kind == "answered" and "not_shown" in levels) or (kind == "partial" and "not_shown" not in levels):
            return LlmTurn(None, "inconsistent")
    if len(out.quotes) != len(verify_quotes(out.quotes, request.answer)):
        return LlmTurn(None, "invented_quote")  # one quote that is not in the answer: nothing else it says is trusted

    dropped: list[str] = []
    follow_up = out.follow_up or None
    if follow_up:
        line = screen_spoken(follow_up, request.blocklists, "question") if kind == "partial" else None
        if line is None or is_sensitive(line) or is_duplicate(line, request.asked):
            dropped.append("follow_up")
            follow_up = None
        else:
            follow_up = line
    analysis = TurnAnalysis(AnswerType(kind), {p.id: p.level for p in out.points}, tuple(out.quotes), follow_up, method)
    return LlmTurn(analysis, "ok", tuple(dropped))


def analyze_turn(llm: LLMClient, engine: InterviewEngine, text: str) -> LlmTurn:
    """Prepare, ask an injected `LLMClient`, parse. Never raises: any failure of the call is `llm_error` and the rules
    take over (D54). The caller enforces the per-turn deadline; a late answer must not be passed to the engine."""
    request = prepare_turn(engine, text)
    if request is None:
        return LlmTurn(None, "rules_only")  # nothing to ask a model: the rules decide, as for an empty or very short answer
    try:
        raw = ask(llm, request.model_input)
    except Exception as e:  # noqa: BLE001  (every failure means the rules; only the type is logged, never any text)
        log.warning("interview turn analysis failed (%s); using the rules", type(e).__name__)
        return LlmTurn(None, "llm_error")
    turn = parse_turn(request, raw, method=f"llm:{llm.model}")
    if turn.analysis is None:
        log.warning("interview turn analysis rejected (%s); using the rules", turn.reason)
    return turn


# ── The rubric (not wired into the plan yet) ──


class RubricPointOut(BaseModel):
    model_config = _STRICT
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=60)]
    keywords: list[
        Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2, max_length=24, pattern=r"^[0-9A-Za-z가-힣+#.\-]+$")]
    ] = Field(min_length=1, max_length=6)


class RubricLlmOut(BaseModel):
    model_config = _STRICT
    points: list[RubricPointOut] = Field(min_length=MIN_RUBRIC_POINTS, max_length=MAX_RUBRIC_POINTS)


@dataclass(frozen=True)
class RubricRequest:
    model_input: ModelInput
    blocklists: tuple[Blocklist, ...]

    @property
    def system(self) -> str:
        return self.model_input.system

    @property
    def user(self) -> str:
        return self.model_input.user

    @property
    def schema(self) -> type[RubricLlmOut]:
        return self.model_input.schema  # type: ignore[return-value]

    @property
    def max_tokens(self) -> int:
        return self.model_input.max_tokens


def rubric_request(
    *, question: str, name: str, category: str, description: str, importance: str, blocklists: Sequence[Blocklist]
) -> RubricRequest | None:
    """The request for the rubric of one question, or None when there is nothing safe to ask with (a sensitive or empty
    question or criterion name, or an importance that is not a label). No weight can be passed: only the label."""
    q, n, d = safe_text(question), safe_text(name), safe_text(description)
    if not q or not n or importance not in IMPORTANCE_RANK:
        return None
    sections = [("question", (q,)), ("criterion", (safe_text(f"{n} | {safe_text(category)} | {importance} | {d}"),))]
    try:
        model_input = compose("rubric", _prompt(RUBRIC_PROMPT), sections, RubricLlmOut, RUBRIC_MAX_TOKENS)
    except ValueError:
        return None
    return RubricRequest(model_input, tuple(blocklists))


def parse_rubric(request: RubricRequest, raw: Any) -> tuple[RubricPoint, ...] | None:
    """2 to 4 validated rubric points, or None (keep the rules rubric). Ids and `min_hits` are set here, never by the
    model; every text must pass the spoken-line screens because a follow-up speaks it."""
    out, _reason = _load(raw, request.schema)
    if out is None:
        return None
    points: list[RubricPoint] = []
    seen: set[str] = set()
    for i, p in enumerate(out.points, 1):
        text = screen_spoken(p.text, request.blocklists)
        key = re.sub(r"\W+", "", p.text.lower())
        words = tuple(dict.fromkeys(p.keywords))
        if text is None or is_sensitive(text) or key in seen:
            return None
        seen.add(key)
        points.append(RubricPoint(f"p{i}", text, words, rules.min_hits(len(words))))
    return tuple(points)
