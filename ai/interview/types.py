"""Types of the practice-interview engine (docs/DECISIONS.md D51–D54, D57).

Plain dataclasses and enums, JSON-friendly through `to_dict`. Nothing here holds a criterion weight: a plan carries only
the importance label (core / important / general, D94) that the caller derives from the weight (D30, AI rule 9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from ai.career.interview import Kind
from ai.interview.boundary import render
from ai.interview.sensitive import SafeText, safe_text

Importance = Literal["core", "important", "general"]
IMPORTANCE_RANK: dict[str, int] = {"core": 0, "important": 1, "general": 2}

# ── Limits (D57) ──
# Approved defaults. The backend will read overrides from its settings (M4); the engine only knows these.
INTERVIEW_MAX_QUESTIONS = 5
INTERVIEW_MAX_SECONDS = 600
INTERVIEW_MAX_FOLLOWUPS_PER_ITEM = 2
INTERVIEW_MAX_CLARIFIES_PER_ITEM = 1
INTERVIEW_SILENCE_NUDGE_SECONDS = 20
INTERVIEW_SILENCE_SKIP_SECONDS = 45
INTERVIEW_TURN_LLM_DEADLINE_SECONDS = 8  # used by the realtime agent (M5); carried here so one object holds the D57 defaults

# Engine tuning defaults. Recommended in the audit but not part of D57: PROJECT_DOCUMENTATION.md §6.2 labels them [Recommended].
WRAP_RESERVE_SECONDS = 45  # below this many seconds left, no new question and no follow-up: wrap up
MIN_ANSWER_CHARS = 8  # an answer shorter than this (or than MIN_ANSWER_WORDS words) is "too short"
MIN_ANSWER_WORDS = 3
DUPLICATE_RATIO = 0.8  # a new line this similar to an earlier one counts as a duplicate
MIN_RUBRIC_POINTS = 2
MAX_RUBRIC_POINTS = 4

AI_GENERATED = "ai_generated"
RUBRIC_NOTICE = "Rubric points are AI-generated expectations, not company requirements."


@dataclass(frozen=True)
class InterviewLimits:
    max_questions: int = INTERVIEW_MAX_QUESTIONS
    max_seconds: int = INTERVIEW_MAX_SECONDS
    max_followups_per_item: int = INTERVIEW_MAX_FOLLOWUPS_PER_ITEM
    max_clarifies_per_item: int = INTERVIEW_MAX_CLARIFIES_PER_ITEM
    silence_nudge_seconds: int = INTERVIEW_SILENCE_NUDGE_SECONDS
    silence_skip_seconds: int = INTERVIEW_SILENCE_SKIP_SECONDS
    turn_llm_deadline_seconds: int = INTERVIEW_TURN_LLM_DEADLINE_SECONDS
    wrap_reserve_seconds: int = WRAP_RESERVE_SECONDS

    def __post_init__(self) -> None:
        if self.max_questions < 1 or self.max_seconds < 1:
            raise ValueError("max_questions and max_seconds must be positive")
        if self.max_followups_per_item < 0 or self.max_clarifies_per_item < 0 or self.wrap_reserve_seconds < 0:
            raise ValueError("followup, clarify and wrap-reserve limits cannot be negative")
        if not 0 < self.silence_nudge_seconds < self.silence_skip_seconds:
            raise ValueError("the silence nudge must come before the silence skip")


DEFAULT_LIMITS = InterviewLimits()


# ── Plan ──


@dataclass(frozen=True)
class PlanCriterion:
    """One criterion of the job as the engine sees it. No weight: `importance` is the label the caller derived (D30)."""

    id: int
    name: str
    category: str
    description: str = ""
    importance: Importance = "general"
    position: int = 0


@dataclass(frozen=True)
class RubricPoint:
    """One thing a good answer would show: an AI-generated expectation, never a company requirement."""

    id: str
    text: str  # a noun phrase, so "<text>에 대해 …" reads as a question
    keywords: tuple[str, ...]  # lower-case cues the rules analysis looks for
    min_hits: int = 1  # cue hits needed to count the point as demonstrated; one hit is partial
    source: str = AI_GENERATED

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "keywords": list(self.keywords), "min_hits": self.min_hits, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricPoint:
        return cls(data["id"], data["text"], tuple(data["keywords"]), int(data["min_hits"]), data.get("source", AI_GENERATED))


@dataclass(frozen=True)
class PlanItem:
    topic_id: str  # "c<criterion id>", "warmup" or "behavioral"
    kind: Kind
    question: str
    rephrase: str  # a shorter, easier wording for a repeat or clarification request
    rubric: tuple[RubricPoint, ...]
    topic_keywords: tuple[str, ...] = ()
    criterion_id: int | None = None
    criterion_name: str | None = None
    importance: Importance | None = None
    intent: str = ""
    answer_tips: tuple[str, ...] = ()
    cv_quote: str | None = None  # a line of the masked CV, verified against it
    depth: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "kind": self.kind,
            "question": self.question,
            "rephrase": self.rephrase,
            "rubric": [p.to_dict() for p in self.rubric],
            "topic_keywords": list(self.topic_keywords),
            "criterion_id": self.criterion_id,
            "criterion_name": self.criterion_name,
            "importance": self.importance,
            "intent": self.intent,
            "answer_tips": list(self.answer_tips),
            "cv_quote": self.cv_quote,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanItem:
        return cls(
            topic_id=data["topic_id"],
            kind=data["kind"],
            question=data["question"],
            rephrase=data["rephrase"],
            rubric=tuple(RubricPoint.from_dict(p) for p in data["rubric"]),
            topic_keywords=tuple(data.get("topic_keywords", ())),
            criterion_id=data.get("criterion_id"),
            criterion_name=data.get("criterion_name"),
            importance=data.get("importance"),
            intent=data.get("intent", ""),
            answer_tips=tuple(data.get("answer_tips", ())),
            cv_quote=data.get("cv_quote"),
            depth=data.get("depth"),
        )


@dataclass(frozen=True)
class UncoveredCriterion:
    """A criterion the plan does not ask about: no slot left under the question cap, or no question passed the screens."""

    criterion_id: int
    name: str
    importance: Importance
    reason: str  # "no_slot" | "no_question"


@dataclass(frozen=True)
class InterviewPlan:
    items: tuple[PlanItem, ...]
    uncovered: tuple[UncoveredCriterion, ...] = ()
    rubric_notice: str = RUBRIC_NOTICE
    bank_method: str = "rules"  # how the D21 question bank was made: "rules" or "llm:<model>"
    depth: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "uncovered": [
                {"criterion_id": u.criterion_id, "name": u.name, "importance": u.importance, "reason": u.reason} for u in self.uncovered
            ],
            "rubric_notice": self.rubric_notice,
            "bank_method": self.bank_method,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterviewPlan:
        raw_depth = data.get("depth")
        return cls(
            items=tuple(PlanItem.from_dict(i) for i in data["items"]),
            uncovered=tuple(UncoveredCriterion(**u) for u in data.get("uncovered", ())),
            rubric_notice=data.get("rubric_notice", RUBRIC_NOTICE),
            bank_method=data.get("bank_method", "rules"),
            depth=2 if raw_depth is None else raw_depth,
        )


# ── Turns and decisions ──


class TopicStatus(str, Enum):
    NOT_ASKED = "not_asked"
    ASKED = "asked"
    DEMONSTRATED = "demonstrated"
    PARTIAL = "partial"
    NOT_SHOWN = "not_shown"
    SKIPPED = "skipped"


PointLevel = Literal["demonstrated", "partial", "not_shown"]
LEVEL_RANK: dict[str, int] = {"not_shown": 0, "partial": 1, "demonstrated": 2}


class AnswerType(str, Enum):
    EMPTY = "empty"
    TOO_SHORT = "too_short"
    REPEAT_REQUEST = "repeat_request"
    CLARIFICATION_REQUEST = "clarification_request"
    OFF_TOPIC = "off_topic"
    DONT_KNOW = "dont_know"
    PARTIAL = "partial"
    ANSWERED = "answered"


# Answers the rules classify, by themselves, before any model is asked: nothing was said, almost nothing was said, or the
# candidate asks to hear the question again. A model's analysis never replaces these, in either direction (D54, D59).
STRUCTURAL_ANSWER_TYPES = frozenset(
    {AnswerType.EMPTY, AnswerType.TOO_SHORT, AnswerType.REPEAT_REQUEST, AnswerType.CLARIFICATION_REQUEST}
)


@dataclass(frozen=True)
class TurnAnalysis:
    """What one candidate answer showed. From the rules (`rules.analyze`), or from a model (`llm.py`); either way the
    engine sanitizes it (`guards.sanitize_analysis`)."""

    answer_type: AnswerType
    points: dict[str, PointLevel] = field(default_factory=dict)  # rubric point id -> level for this answer
    quotes: tuple[str, ...] = ()  # verbatim parts of the masked answer
    suggested_follow_up: str | None = None
    method: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_type": self.answer_type.value,
            "points": dict(self.points),
            "quotes": list(self.quotes),
            "method": self.method,
        }


class DecisionKind(str, Enum):
    WRAP = "wrap"
    CLARIFY = "clarify"
    REPEAT = "repeat"
    REDIRECT = "redirect"
    FOLLOW_UP = "follow_up"
    NEXT = "next"
    SKIP = "skip"


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str
    point_id: str | None = None  # the rubric point a follow-up asks about
    rephrase: bool = False  # a repeat that uses the shorter wording


class ActionKind(str, Enum):
    ASK = "ask"
    FOLLOW_UP = "follow_up"
    CLARIFY = "clarify"
    REPEAT = "repeat"
    REDIRECT = "redirect"
    NUDGE = "nudge"
    WRAP = "wrap"


@dataclass(frozen=True)
class Action:
    """What the interviewer says next. Every `text` has passed `guards.screen_spoken`."""

    kind: ActionKind
    text: str
    item_index: int | None = None
    topic_id: str | None = None
    reason: str = ""
    done: bool = False  # True for WRAP: the interview is over after this line


class Phase(str, Enum):
    NEW = "new"
    LISTENING = "listening"  # a question was asked and an answer is expected
    ENDED = "ended"
    ABORTED = "aborted"


@dataclass(frozen=True)
class Turn:
    """One line of the transcript. `text` is masked; nothing else about the speaker is kept."""

    seq: int
    role: Literal["agent", "candidate"]
    kind: str  # question | follow_up | clarify | repeat | redirect | nudge | closing | answer
    item_index: int | None
    text: str
    method: str = "rules"
    analysis: dict[str, Any] | None = None
    masked_kinds: dict[str, int] = field(default_factory=dict)  # which kinds of data were masked, counts only

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "role": self.role,
            "kind": self.kind,
            "item_index": self.item_index,
            "text": self.text,
            "method": self.method,
            "analysis": self.analysis,
            "masked_kinds": dict(self.masked_kinds),
        }


@dataclass(frozen=True)
class TurnContext:
    """Everything a model may see about one answer: masked text and the plan's own words, nothing else (AI rule 3).

    Built only by `InterviewEngine.turn_context` from an already masked answer. `to_text` is the one place a prompt
    would take it from, so a test can check the whole model input for leaked personal data. Every field leaves through
    `sensitive.safe_text` here (`sections`), so a caller that never goes through `llm.prepare_turn` still gets nothing about
    age, gender or military service, by the vocabulary of `sensitive.py` (D61, D62).
    """

    question: str
    criterion_name: str | None
    importance: str | None
    rubric: tuple[tuple[str, str], ...]  # (point id, text)
    answer: str
    previous: tuple[str, ...] = ()  # masked lines before this answer, oldest first
    asked: tuple[str, ...] = ()  # every question already asked, so none is repeated

    def sections(self) -> tuple[tuple[str, tuple[SafeText, ...]], ...]:
        """The model view of this turn: every part cut through `safe_text`, in the tags of the turn prompt."""
        out: list[tuple[str, tuple[SafeText, ...]]] = [("question", (safe_text(self.question),))]
        if name := safe_text(self.criterion_name):
            out.append(("criterion", (safe_text(f"{name} ({self.importance or 'general'})"),)))
        out.append(("rubric", tuple(safe_text(f"{pid} | {safe_text(text) or '(excluded)'}") for pid, text in self.rubric)))
        if previous := tuple(line for line in map(safe_text, self.previous) if line):
            out.append(("previous", previous))
        out.append(("asked", tuple(line for line in map(safe_text, self.asked) if line)))
        out.append(("answer", (safe_text(self.answer),)))
        return tuple(out)

    def to_text(self) -> str:
        return render(self.sections())
