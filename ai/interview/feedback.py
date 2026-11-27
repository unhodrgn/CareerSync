"""The final feedback of a practice interview (docs/DECISIONS.md D51, D53, D54, D63).

Practice and learning only: the report has no number that scores, ranks or counts, no verdict and no hiring advice (AI rule 5).
It is made from two views and nothing else, `views.transcript_view(...)` and `views.plan_view(...)` (or the same views rebuilt
from what a backend persisted), so it never sees the interview state, the engine or a raw transcript, and it reads no CV.

    transcript = transcript_view(engine.state)
    plan = plan_view(engine.state)
    report = make_feedback(transcript, plan, resources=load_resources(), skills=skills, blocklists=blocklists, llm=client)

What the code owns: the topics and their statuses (from the engine, through the plan view), the list of criteria that were not
asked, the fixed notes, the learning links (only from `data/learning_resources.yaml`, found by the skill names in the plan's
own criterion text), and the whole rules report. What a model may write: the sentences of the strengths, the gaps and the
improvements, and the practice questions, in one strict JSON object. Every item of it is checked, and a failing item is
dropped on its own:

- a strength needs at least one quote that appears exactly in a candidate line of the same topic (an interviewer line, another
  topic or a changed word does not count), and the topic's status must be demonstrated or partial; without a verified quote
  the strength is dropped, and a bad quote never invalidates anything else;
- every sentence passes the spoken-line screens (URL, placeholder, verdict word, the age, gender and military-service
  vocabulary, both blocklists) and a score screen (a number with a unit, a rank, a grade), mentions no technology or
  certification that is not in the plan or the candidate's own lines, and is not a question unless it is a practice question; it says nothing about the company, a requirement or an
  expectation (a conservative word screen: the report never states what a job or a company wants);
- a practice question is grounded in its topic's name, question and rubric, repeats no question already asked, and is not a
  duplicate of another suggestion.

Fallback (D54): the rules report is always computed first. Without a client, on any failure of the call, on invalid JSON or an
invalid schema, or when nothing usable is left, the report is the rules report (`method` is "rules"). When the model's output has
usable items, a section with none falls back to the rules section for that section only (`rules_sections` names those), and
`method` is "llm:<model>". The model's call is `boundary.ask` of a `ModelInput` made by `boundary.compose`; no provider is imported.

Limits, honestly: the screens are a vocabulary and token rules, not understanding; a sentence can be fluent and still wrong; the
rules report judges cue words. Quote checks are exact on the sanitized transcript, so a quote of a sentence the sanitizer cut
cannot be used. The `AI_NOTICE` of a response is added by the backend schema (M4), not here.
"""
import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai.career.resources import Resources
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.interview import rules
from ai.interview.boundary import ModelInput, ask, compose
from ai.interview.guards import is_duplicate, screen_spoken
from ai.interview.sensitive import is_sensitive, safe_text
from ai.interview.types import IMPORTANCE_RANK, RUBRIC_NOTICE
from ai.interview.views import SafeItem, SafePlan, SafeTurn, SafeUncovered
from ai.llm.client import LLMClient
from ai.parsing.extract import PROMPT_DIR

log = logging.getLogger(__name__)

FEEDBACK_PROMPT = "interview_feedback.md"
FEEDBACK_MAX_TOKENS = 1800
# Size limits: engine defaults, [Recommended] in PROJECT_DOCUMENTATION.md §6.2, not decided by D63
MAX_STRENGTHS, MAX_GAPS, MAX_IMPROVEMENTS, MAX_PRACTICE, MAX_RESOURCES = 4, 4, 4, 3, 4
MAX_TEXT_CHARS, MAX_QUESTION_CHARS = 200, 200
MIN_QUOTE_CHARS, MAX_QUOTE_CHARS, MAX_QUOTES = 8, 120, 2  # evidence is a phrase, not a word
MAX_TRANSCRIPT_CHARS = 12000  # the earliest turns that fit go into the request; the quote check uses exactly those

WARMUP_LABEL = "CV-based experience"  # shown for the CV-grounded warm-up, whose question text is never repeated in the report
BEHAVIORAL_LABEL = "Behavioral example"
STRENGTH_STATUSES = frozenset({"demonstrated", "partial"})
GAP_STATUSES = frozenset({"partial", "not_shown", "skipped", "asked", "not_asked"})
SECTIONS = ("strengths", "gaps", "improvements", "practice_questions")

# Fixed sentences of the rules report; a test screens every one of them
NOTE_NO_ITEMS = "There are no prepared questions to review."
NOTE_NO_ANSWERS = "No answers were recorded to review. Please check your microphone and try practicing again."
NOTE_ABORTED = "The practice session ended early, so some questions were not covered."
NOTE_TIME = "Scheduled time ended before all questions were covered."
ADVICE_STRUCTURE = "Structuring answers by situation, your role, actions taken, and outcomes makes evidence clearer."
ADVICE_UNSURE = "Even on unfamiliar topics, start with what you do know so you can practice explaining your reasoning."
ADVICE_UNCOVERED = "Try practicing the topics that were not covered next time."
ADVICE_KEEP = "Carry the clear structure of your strongest answers into other questions as well."
BEHAVIORAL_PRACTICE = "If you have a similar experience, try explaining the situation, what you did, and the outcome."
FIXED_LINES = (NOTE_NO_ITEMS, NOTE_NO_ANSWERS, NOTE_ABORTED, NOTE_TIME, ADVICE_STRUCTURE, ADVICE_UNSURE, ADVICE_UNCOVERED, ADVICE_KEEP)

# A number with a unit, a rank, a grade, a verdict: things a feedback text must not say. (A bare number such as "Java 17" is fine.)
_SCORE_LIKE = re.compile(
    r"\d\s*(?:점|%|퍼센트|등|위|개|명|문항|문제|건|번째|회|/)"
    r"|\b\d+\s*(?:out of|points?|pts|percent)\b"
    r"|\b(?:scores?|scored|rating|rated|rank|ranked|ranking|percentile|grades?|graded|top\s*\d+|hire[d]?|hiring|reject(?:ed)?|pass(?:ed)?|fail(?:ed)?)\b"
    r"|순위|등수|등급|백분위|평점|상위|하위|적합|부적합|가산점|감점|우수한 지원자|다른 지원자|다른 사람보다|평균보다|비교하면",
    re.IGNORECASE,
)
# A model sentence about the company, a requirement or an expectation: the report never says what a job or a company wants
_CLAIMS = re.compile(r"회사|기업|공고|요구|필수|우대|요건|기대|\b(?:company|employer|requirements?|required|expect\w*)\b", re.IGNORECASE)
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:[.\-][A-Za-z0-9+#]+)*")
_SENTENCE_START_ALLOW = frozenset({
    "you", "your", "try", "consider", "explain", "describe", "share", "walk", "focus", "keep", "start",
    "finish", "build", "based", "overall", "when", "while", "where", "what", "how", "why", "this", "that",
    "these", "those", "the", "a", "an", "for", "in", "on", "to", "with", "without", "during", "before",
    "after", "more", "some", "no", "not", "none", "good", "clear", "specific", "concrete", "adding",
    "providing", "explaining", "describing", "highlighting", "discussing", "structuring", "connecting",
    "practicing", "reviewing", "preparing", "answering", "instead", "however", "additionally", "furthermore",
    "next", "remember", "make", "use", "avoid", "include", "cover", "mention", "even", "although", "though",
    "since", "because", "if", "as", "there", "here", "it", "also", "please", "give", "state", "clarify",
    "specify", "summarize", "practice", "review", "carry", "regarding", "having", "using", "showing", "star",
})
_WORD = re.compile(r"[a-z0-9+#.\-]{2,}|[가-힣]{2,}")  # Latin and Hangul runs apart: "API를" is "api" and a particle
_STOP = (
    "설명", "경험", "사례", "대해", "구체", "있는", "해보", "보세요", "주세요", "관련", "내용", "방법", "어떻게", "무엇", "실제", "이번", "연습", "활용", "능력", "이해", "수준", "지식",
    "explain", "describe", "experience", "example", "examples", "practical", "detail", "details", "about",
    "please", "could", "would", "should", "what", "how", "why", "this", "that", "your", "with", "from",
    "into", "related", "relevant", "topic", "question", "answer", "answers", "using", "used", "work",
    "concept", "concepts", "knowledge", "understanding", "proficiency", "skill", "skills", "share", "tell",
    "walk", "through", "concrete", "practice", "based", "real", "level", "more", "most",
)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@lru_cache(maxsize=None)
def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


# ── The report ──


@dataclass(frozen=True)
class TopicFeedback:
    topic_id: str
    name: str
    importance: str | None  # core / important / general, never a weight
    status: str  # decided by the engine: demonstrated, partial, not_shown, skipped, asked or not_asked


@dataclass(frozen=True)
class Strength:
    topic_id: str
    text: str
    quotes: tuple[str, ...]  # at least one, each found exactly in a candidate line of the same topic


@dataclass(frozen=True)
class Gap:
    topic_id: str
    text: str


@dataclass(frozen=True)
class PracticeQuestion:
    topic_id: str
    question: str


@dataclass(frozen=True)
class ResourceLink:
    topic_id: str
    skill: str
    title: str
    url: str  # only ever a URL of data/learning_resources.yaml


@dataclass(frozen=True)
class UncoveredTopic:
    topic_id: str
    name: str
    importance: str
    reason: str


@dataclass(frozen=True)
class FeedbackReport:
    method: str  # "rules" or "llm:<model>" (D54)
    topics: tuple[TopicFeedback, ...]
    strengths: tuple[Strength, ...]
    gaps: tuple[Gap, ...]
    improvements: tuple[str, ...]
    practice_questions: tuple[PracticeQuestion, ...]
    resources: tuple[ResourceLink, ...]
    uncovered: tuple[UncoveredTopic, ...]
    notes: tuple[str, ...] = ()
    rules_sections: tuple[str, ...] = ()  # with method "llm:...": the sections taken from the rules report
    rubric_notice: str = RUBRIC_NOTICE

    def to_data(self) -> dict[str, Any]:
        """The report as plain data (for a backend to store or return). It serializes the report, never interview state."""
        return {
            "method": self.method,
            "topics": [{"topic_id": t.topic_id, "name": t.name, "importance": t.importance, "status": t.status} for t in self.topics],
            "strengths": [{"topic_id": s.topic_id, "text": s.text, "quotes": list(s.quotes)} for s in self.strengths],
            "gaps": [{"topic_id": g.topic_id, "text": g.text} for g in self.gaps],
            "improvements": list(self.improvements),
            "practice_questions": [{"topic_id": q.topic_id, "question": q.question} for q in self.practice_questions],
            "resources": [{"topic_id": r.topic_id, "skill": r.skill, "title": r.title, "url": r.url} for r in self.resources],
            "uncovered": [{"topic_id": u.topic_id, "name": u.name, "importance": u.importance, "reason": u.reason} for u in self.uncovered],
            "notes": list(self.notes),
            "rules_sections": list(self.rules_sections),
            "rubric_notice": self.rubric_notice,
        }


# ── What a model may answer ──

_STRICT = ConfigDict(extra="forbid", strict=True)  # the types are strict; lengths and contents are checked item by item below


class StrengthOut(BaseModel):
    model_config = _STRICT
    topic_id: str
    text: str
    quotes: list[str] = Field(default_factory=list)  # may be empty or odd: the strength is then dropped, not the answer


class GapOut(BaseModel):
    model_config = _STRICT
    topic_id: str
    text: str


class PracticeOut(BaseModel):
    model_config = _STRICT
    topic_id: str
    question: str


class FeedbackLlmOut(BaseModel):
    """The only shape a model may answer in. No status, no number, no URL: those are not the model's to say."""

    model_config = _STRICT
    strengths: list[StrengthOut] = Field(default_factory=list, max_length=20)
    gaps: list[GapOut] = Field(default_factory=list, max_length=20)
    improvements: list[str] = Field(default_factory=list, max_length=20)
    practice_questions: list[PracticeOut] = Field(default_factory=list, max_length=20)


# ── What the checks need, built once from the two views ──


@dataclass(frozen=True)
class _Context:
    items: dict[str, SafeItem]
    uncovered: dict[str, SafeUncovered]
    answers: dict[str, tuple[str, ...]]  # topic id -> the candidate's lines (whitespace collapsed)
    stored_quotes: dict[str, tuple[str, ...]]  # topic id -> quotes the analyses stored for its candidate turns
    asked: tuple[str, ...]
    topic_text: dict[str, str]  # topic id -> name, question and rubric texts: what its sentences may be built on
    latin: frozenset[str]
    skills: frozenset[str]  # skills and certificates the plan or the candidate named
    lines: tuple[SafeTurn, ...]  # the transcript lines that were used (the earliest that fit the cap)

    @property
    def has_answers(self) -> bool:
        return any(self.answers.values())


def _norm(text: str) -> str:
    return " ".join(text.split())


def _name(item: SafeItem) -> str:
    return item.criterion_name.value or (WARMUP_LABEL if item.topic_id == "warmup" else BEHAVIORAL_LABEL)


def _check_inputs(transcript: Iterable[SafeTurn], plan: SafePlan) -> tuple[SafeTurn, ...]:
    if not isinstance(plan, SafePlan):
        raise TypeError("make_feedback takes the output of plan_view() or plan_view_from(), never interview state or an engine")
    lines = tuple(transcript)
    if not all(isinstance(t, SafeTurn) for t in lines):
        raise TypeError("make_feedback takes the output of transcript_view() or transcript_view_from(), never raw turns")
    return lines


def _within_cap(lines: Sequence[SafeTurn]) -> tuple[SafeTurn, ...]:
    kept, size = [], 0
    for line in lines:
        size += len(line.text.value) + 24
        if size > MAX_TRANSCRIPT_CHARS:
            break
        kept.append(line)
    return tuple(kept)


def _context(transcript: Sequence[SafeTurn], plan: SafePlan, skills: SkillDictionary | None) -> _Context:
    lines = _within_cap(transcript)
    items = {item.topic_id: item for item in plan.items}
    uncovered = {f"c{u.criterion_id}": u for u in plan.uncovered if f"c{u.criterion_id}" not in items and u.name}
    answers: dict[str, list[str]] = {}
    stored: dict[str, list[str]] = {}
    for line in lines:
        if line.role == "candidate" and line.topic_id in items:
            answers.setdefault(line.topic_id, []).append(_norm(line.text.value))
            stored.setdefault(line.topic_id, []).extend(q.value for q in line.quotes)
    asked = [item.question.value for item in plan.items if item.question]
    asked += [line.text.value for line in lines if line.role == "agent" and line.kind in ("question", "follow_up")]
    topic_text = {
        item.topic_id: " ".join([_name(item), item.question.value, *(text.value for _, text in item.rubric)]) for item in plan.items
    }
    topic_text.update({tid: u.name.value for tid, u in uncovered.items()})
    grounding = " ".join([*topic_text.values(), *(line for group in answers.values() for line in group)])
    named = frozenset(skills.find_in_text(grounding) + [name for name, _ in skills.find_certificates(grounding)]) if skills is not None else frozenset()
    return _Context(
        items,
        uncovered,
        {topic: tuple(group) for topic, group in answers.items()},
        {topic: tuple(group) for topic, group in stored.items()},
        tuple(dict.fromkeys(asked)),
        topic_text,
        frozenset(token.lower() for token in _LATIN.findall(grounding)),
        named,
        lines,
    )


# ── Checks ──


def screen_feedback(text: object, blocklists: Sequence[Blocklist], kind: str = "statement") -> str | None:
    """The cleaned sentence when it may be shown, else None: the spoken-line screens (no URL, email, placeholder, code, verdict
    word, nothing that matches the age, gender and military-service vocabulary, nothing either blocklist matches), no score-like
    number, rank or grade, and no question unless `kind` is "question"."""
    if not isinstance(text, str):
        return None
    line = screen_spoken(text, blocklists, "question" if kind == "question" else "statement")  # type: ignore[arg-type]
    if line is None or _SCORE_LIKE.search(line):
        return None
    if kind == "question":
        return line if len(line) <= MAX_QUESTION_CHARS else None
    return None if "?" in line or "？" in line else line


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if not any(t.startswith(stop) for stop in _STOP)}


def _same_word(a: str, b: str) -> bool:
    """One word is the start of the other ("자바" and "자바를"), or they share a stem of three letters ("문서화를", "문서화한")."""
    if a.startswith(b) or b.startswith(a):
        return True
    stem = 0
    for x, y in zip(a, b):
        if x != y:
            break
        stem += 1
    return stem >= 3


def _grounded_in(line: str, topic: str, ctx: _Context) -> bool:
    """The question shares a content word with its topic's name, question or rubric (so it is about that topic)."""
    context = _tokens(ctx.topic_text.get(topic, ""))
    return any(_same_word(q, c) for q in _tokens(line) for c in context)


def _looks_like_invented_tech(line: str, ctx: _Context) -> bool:
    for m in _LATIN.finditer(line):
        token = m.group(0)
        if len(token) < 2 or token.lower() in ctx.latin:
            continue
        if any(ch.isdigit() or ch in "+#." for ch in token):
            return True
        if token.isupper() or any(ch.isupper() for ch in token[1:]):
            return True
        if token[0].isupper():
            before = line[: m.start()].rstrip()
            at_sentence_start = not before or before[-1] in ".!?"
            if not at_sentence_start or token.lower() not in _SENTENCE_START_ALLOW:
                return True
    return False


def _invents(line: str, ctx: _Context, skills: SkillDictionary | None) -> bool:
    """The sentence names a technology or certification that neither the plan nor the candidate's own lines name."""
    if skills is not None:
        mentioned = set(skills.find_in_text(line)) | {name for name, _ in skills.find_certificates(line)}
        if not mentioned <= ctx.skills:
            return True
    return _looks_like_invented_tech(line, ctx)


def _valid_quotes(raw: Iterable[object], lines: Sequence[str]) -> tuple[str, ...]:
    """The quotes that appear exactly (whitespace collapsed, same case) in one line of `lines`, the candidate's lines of one topic."""
    out: list[str] = []
    for quote in raw:
        if not isinstance(quote, str):
            continue
        n = _norm(quote)
        if not MIN_QUOTE_CHARS <= len(n) <= MAX_QUOTE_CHARS or "[" in n or "]" in n or is_sensitive(n) or n in out:
            continue
        if any(n in line for line in lines):
            out.append(n)
        if len(out) == MAX_QUOTES:
            break
    return tuple(out)


# ── The rules report ──


def _ordered(plan: SafePlan) -> list[SafeItem]:
    ranked = sorted(enumerate(plan.items), key=lambda pair: (IMPORTANCE_RANK.get(pair[1].importance or "", len(IMPORTANCE_RANK)), pair[0]))
    return [item for _, item in ranked]


def _first_ok(candidates: Iterable[str], blocklists: Sequence[Blocklist], kind: str = "statement") -> str | None:
    return next((line for text in candidates if (line := screen_feedback(text, blocklists, kind)) is not None), None)


def _rules_strengths(ctx: _Context, plan: SafePlan, blocklists: Sequence[Blocklist]) -> tuple[Strength, ...]:
    out: list[Strength] = []
    for item in _ordered(plan):
        if item.status not in STRENGTH_STATUSES:
            continue
        quotes = _valid_quotes(ctx.stored_quotes.get(item.topic_id, ()), ctx.answers.get(item.topic_id, ()))
        if not quotes:  # no evidence, no strength
            continue
        levels = dict(item.levels)
        wanted = ("demonstrated",) if item.status == "demonstrated" else ("demonstrated", "partial")
        shown = [text.value for pid, text in item.rubric if levels.get(pid) in wanted and text]
        name = _name(item)
        if item.status == "demonstrated":
            candidates = [f"In '{name}', you clearly explained {', '.join(shown[:n])}." for n in (2, 1) if shown[:n]]
            candidates.append(f"In '{name}', you explained the topic with clear supporting details.")
        else:
            candidates = [f"In '{name}', you partially covered {', '.join(shown[:n])}." for n in (2, 1) if shown[:n]]
            candidates.append(f"In '{name}', you shared some relevant points.")
        if (text := _first_ok(candidates, blocklists)) is not None:
            out.append(Strength(item.topic_id, text, quotes))
        if len(out) == MAX_STRENGTHS:
            break
    return tuple(out)


def _gap_lines(item: SafeItem) -> list[str]:
    name = _name(item)
    if item.status == "skipped":
        return [f"You skipped the question on '{name}', so those details were not covered."]
    if item.status in ("asked", "not_asked"):
        return [f"'{name}' was not covered during this practice session."]
    levels = dict(item.levels)
    lines = []
    for pid, text in item.rubric:
        level = levels.get(pid, "not_shown")
        if level == "demonstrated" or not text:
            continue
        lines.append(
            f"In '{name}', {text.value} has not been covered yet."
            if level == "not_shown"
            else f"In '{name}', adding more detail on {text.value} would help."
        )
    return lines[:2] or [f"There was limited detail shown for '{name}'."]


def _rules_gaps(ctx: _Context, plan: SafePlan, blocklists: Sequence[Blocklist]) -> tuple[Gap, ...]:
    out: list[Gap] = []
    for item in _ordered(plan):
        if item.status in GAP_STATUSES:
            out += [Gap(item.topic_id, line) for text in _gap_lines(item) if (line := screen_feedback(text, blocklists)) is not None]
    for tid, u in ctx.uncovered.items():
        if line := screen_feedback(f"'{u.name.value}' was not covered during this practice session.", blocklists):
            out.append(Gap(tid, line))
    return tuple(out[:MAX_GAPS])


def _rules_improvements(ctx: _Context, plan: SafePlan, blocklists: Sequence[Blocklist]) -> tuple[str, ...]:
    statuses = {item.status for item in plan.items}
    wanted = []
    if statuses & {"partial", "not_shown"}:
        wanted.append(ADVICE_STRUCTURE)
    if statuses & {"not_shown", "skipped"}:
        wanted.append(ADVICE_UNSURE)
    if ctx.uncovered or statuses & {"asked", "not_asked"}:
        wanted.append(ADVICE_UNCOVERED)
    if "demonstrated" in statuses:
        wanted.append(ADVICE_KEEP)
    return tuple(line for text in wanted if (line := screen_feedback(text, blocklists)) is not None)[:MAX_IMPROVEMENTS]


def _rules_practice(ctx: _Context, plan: SafePlan, blocklists: Sequence[Blocklist]) -> tuple[PracticeQuestion, ...]:
    out: list[PracticeQuestion] = []
    seen: list[str] = list(ctx.asked)
    for item in _ordered(plan):
        if item.status not in GAP_STATUSES or len(out) >= MAX_PRACTICE:
            continue
        levels = dict(item.levels)
        missing = [text.value for pid, text in item.rubric if levels.get(pid, "not_shown") != "demonstrated" and text]
        if item.topic_id.startswith("c"):
            candidates = [f"Could you give a concrete example from your work about {missing[0]}?"] if missing else []
            candidates.append(rules.fallback_question(_name(item)))
        else:
            candidates = [BEHAVIORAL_PRACTICE]
        if (line := _first_ok(candidates, blocklists, "question")) is not None and not is_duplicate(line, seen, ratio=1.0):
            seen.append(line)
            out.append(PracticeQuestion(item.topic_id, line))
    for tid, u in ctx.uncovered.items():
        if len(out) < MAX_PRACTICE and (line := screen_feedback(rules.fallback_question(u.name.value), blocklists, "question")) is not None:
            if not is_duplicate(line, seen, ratio=1.0):
                seen.append(line)
                out.append(PracticeQuestion(tid, line))
    return tuple(out)


def _links(ctx: _Context, topic_ids: Iterable[str], resources: Resources | None, skills: SkillDictionary | None) -> tuple[ResourceLink, ...]:
    """Learning links for the topics with a gap: found in the code, from the skill and certificate names in the plan's own
    criterion text, in `data/learning_resources.yaml` only. The warm-up and the behavioral topic have none (their text is not
    about a skill the job asks for), and nothing here reads the CV."""
    if resources is None or skills is None:
        return ()
    out: list[ResourceLink] = []
    seen: set[str] = set()
    for tid in dict.fromkeys(topic_ids):
        if not tid.startswith("c") or tid not in ctx.topic_text:
            continue
        text = ctx.topic_text[tid]
        found = [(skill, "skill") for skill in skills.find_in_text(text)] + [(name, "certificate") for name, _ in skills.find_certificates(text)]
        for name, kind in found:
            for resource in resources.for_gap(name, kind):
                if resource.url not in seen:
                    seen.add(resource.url)
                    out.append(ResourceLink(tid, name, resource.title, resource.url))
    return tuple(out[:MAX_RESOURCES])


def _topics(plan: SafePlan) -> tuple[TopicFeedback, ...]:
    return tuple(TopicFeedback(item.topic_id, _name(item), item.importance, item.status) for item in plan.items)


def _uncovered(ctx: _Context) -> tuple[UncoveredTopic, ...]:
    return tuple(UncoveredTopic(tid, u.name.value, u.importance, u.reason) for tid, u in ctx.uncovered.items())


def _notes(ctx: _Context, plan: SafePlan) -> tuple[str, ...]:
    notes = []
    if not plan.items:
        notes.append(NOTE_NO_ITEMS)
    elif not ctx.has_answers:
        notes.append(NOTE_NO_ANSWERS)
    unfinished = any(item.status in ("asked", "not_asked") for item in plan.items)
    if plan.phase == "aborted":
        notes.append(NOTE_ABORTED)
    elif plan.end_reason == "time" and unfinished:
        notes.append(NOTE_TIME)
    return tuple(notes)


def _rules(ctx: _Context, plan: SafePlan, resources: Resources | None, skills: SkillDictionary | None, blocklists: Sequence[Blocklist]) -> FeedbackReport:
    gaps = _rules_gaps(ctx, plan, blocklists)
    return FeedbackReport(
        method="rules",
        topics=_topics(plan),
        strengths=_rules_strengths(ctx, plan, blocklists),
        gaps=gaps,
        improvements=_rules_improvements(ctx, plan, blocklists),
        practice_questions=_rules_practice(ctx, plan, blocklists),
        resources=_links(ctx, [g.topic_id for g in gaps], resources, skills),
        uncovered=_uncovered(ctx),
        notes=_notes(ctx, plan),
    )


def rules_feedback(
    transcript: Iterable[SafeTurn],
    plan: SafePlan,
    *,
    resources: Resources | None = None,
    skills: SkillDictionary | None = None,
    blocklists: Sequence[Blocklist] = (),
) -> FeedbackReport:
    """The deterministic report: no model, no key, the same input always gives the same report."""
    lines = _check_inputs(transcript, plan)
    return _rules(_context(lines, plan, skills), plan, resources, skills, blocklists)


# ── The model path ──


@dataclass(frozen=True)
class FeedbackRequest:
    """What to send (`model_input`) and what the answer is checked against (the rest, never sent)."""

    model_input: ModelInput
    context: _Context
    blocklists: tuple[Blocklist, ...]
    skills: SkillDictionary | None

    @property
    def system(self) -> str:
        return self.model_input.system

    @property
    def user(self) -> str:
        return self.model_input.user


@dataclass(frozen=True)
class ParsedFeedback:
    """The items of a model's answer that passed every check. `dropped`: codes of what did not (never text)."""

    strengths: tuple[Strength, ...] = ()
    gaps: tuple[Gap, ...] = ()
    improvements: tuple[str, ...] = ()
    practice_questions: tuple[PracticeQuestion, ...] = ()
    dropped: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return bool(self.strengths or self.gaps or self.improvements or self.practice_questions)


def _request(ctx: _Context, plan: SafePlan, blocklists: Sequence[Blocklist], skills: SkillDictionary | None) -> FeedbackRequest | None:
    if not plan.items or not ctx.has_answers:  # an empty or answerless interview gives a model nothing to work with
        return None
    plan_lines = [safe_text(f"{item.topic_id} | {_name(item)} | {item.importance or '-'} | {item.status}") for item in plan.items]
    plan_lines += [safe_text(f"{tid} | {u.name.value} | {u.importance} | not_asked") for tid, u in ctx.uncovered.items()]
    rubric_lines = []
    for item in plan.items:
        levels = dict(item.levels)
        rubric_lines += [safe_text(f"{item.topic_id}.{pid} | {text.value} | {levels.get(pid, 'not_shown')}") for pid, text in item.rubric if text]
    transcript_lines = [
        safe_text(f"{line.topic_id or '-'} | {'candidate' if line.role == 'candidate' else 'interviewer'} | {line.text.value}") for line in ctx.lines
    ]
    sections = [
        ("plan", tuple(p for p in plan_lines if p)),
        ("rubric", tuple(r for r in rubric_lines if r)),
        ("asked", tuple(q for q in (safe_text(a) for a in ctx.asked) if q)),
        ("transcript", tuple(t for t in transcript_lines if t)),
    ]
    try:
        model_input = compose("feedback", _prompt(FEEDBACK_PROMPT), sections, FeedbackLlmOut, FEEDBACK_MAX_TOKENS)
    except ValueError:  # the cut text still matches the vocabulary across a seam: no model is asked, the rules report stands
        return None
    return FeedbackRequest(model_input, ctx, tuple(blocklists), skills)


def feedback_request(
    transcript: Iterable[SafeTurn],
    plan: SafePlan,
    *,
    blocklists: Sequence[Blocklist] = (),
    skills: SkillDictionary | None = None,
) -> FeedbackRequest | None:
    """The request for the model, or None when no model should be asked (no questions, no answers, a seam that matches the
    vocabulary). Built from the two views only, through `boundary.compose`."""
    lines = _check_inputs(transcript, plan)
    return _request(_context(lines, plan, skills), plan, blocklists, skills)


def _load(raw: Any) -> tuple[FeedbackLlmOut | None, str]:
    """(validated output, "") or (None, reason). Accepts the model object, a dict, or JSON text (one code fence tolerated)."""
    if isinstance(raw, FeedbackLlmOut):
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
        return FeedbackLlmOut.model_validate(data), ""
    except ValidationError:
        return None, "schema"


def _sentence(text: object, request: FeedbackRequest, kind: str = "statement") -> str | None:
    line = screen_feedback(text, request.blocklists, kind)
    return None if line is None or _CLAIMS.search(line) or _invents(line, request.context, request.skills) else line


def parse_feedback(request: FeedbackRequest, raw: Any) -> tuple[ParsedFeedback | None, str]:
    """(the checked items, "ok"), or (None, reason) when the answer as a whole is unusable: invalid type, invalid JSON, schema,
    or nothing left. A bad item is dropped on its own; a bad quote costs only its strength."""
    out, reason = _load(raw)
    if out is None:
        return None, reason
    ctx, dropped = request.context, []

    strengths: list[Strength] = []
    for s in out.strengths:
        item = ctx.items.get(s.topic_id)
        if item is None or item.status not in STRENGTH_STATUSES:
            dropped.append("strength:topic")
        elif (text := _sentence(s.text, request)) is None:
            dropped.append("strength:text")
        elif not (quotes := _valid_quotes(s.quotes, ctx.answers.get(s.topic_id, ()))):
            dropped.append("strength:quote")  # no verified quote, no strength; nothing else is affected
        elif text not in (x.text for x in strengths):
            strengths.append(Strength(s.topic_id, text, quotes))

    gaps: list[Gap] = []
    for g in out.gaps:
        item = ctx.items.get(g.topic_id)
        if (item is None or item.status not in GAP_STATUSES) and g.topic_id not in ctx.uncovered:
            dropped.append("gap:topic")
        elif (text := _sentence(g.text, request)) is None:
            dropped.append("gap:text")
        elif text not in (x.text for x in gaps):
            gaps.append(Gap(g.topic_id, text))

    improvements: list[str] = []
    for advice in out.improvements:
        if (text := _sentence(advice, request)) is None:
            dropped.append("improvement:text")
        elif text not in improvements:
            improvements.append(text)

    practice: list[PracticeQuestion] = []
    seen = list(ctx.asked)
    for p in out.practice_questions:
        if p.topic_id not in ctx.items and p.topic_id not in ctx.uncovered:
            dropped.append("practice:topic")
        elif (line := _sentence(p.question, request, "question")) is None:
            dropped.append("practice:text")
        elif not _grounded_in(line, p.topic_id, ctx):
            dropped.append("practice:grounding")
        elif is_duplicate(line, seen):  # already asked, or already suggested
            dropped.append("practice:duplicate")
        else:
            seen.append(line)
            practice.append(PracticeQuestion(p.topic_id, line))

    parsed = ParsedFeedback(
        tuple(strengths[:MAX_STRENGTHS]), tuple(gaps[:MAX_GAPS]), tuple(improvements[:MAX_IMPROVEMENTS]), tuple(practice[:MAX_PRACTICE]), tuple(dropped)
    )
    return (parsed, "ok") if parsed.usable else (None, "empty")


def _merge(rules_report: FeedbackReport, parsed: ParsedFeedback, ctx: _Context, method: str, resources: Resources | None, skills: SkillDictionary | None) -> FeedbackReport:
    """The model's sections where it has usable items, the rules sections where it has none. Topics, statuses, the uncovered
    list, the notes and the links stay the code's: the links are looked up again for the gaps of the merged report."""
    chosen = {
        "strengths": parsed.strengths or rules_report.strengths,
        "gaps": parsed.gaps or rules_report.gaps,
        "improvements": parsed.improvements or rules_report.improvements,
        "practice_questions": parsed.practice_questions or rules_report.practice_questions,
    }
    from_rules = tuple(name for name in SECTIONS if not getattr(parsed, name) and chosen[name])
    return FeedbackReport(
        method=method,
        topics=rules_report.topics,
        strengths=chosen["strengths"],
        gaps=chosen["gaps"],
        improvements=chosen["improvements"],
        practice_questions=chosen["practice_questions"],
        resources=_links(ctx, [g.topic_id for g in chosen["gaps"]], resources, skills),
        uncovered=rules_report.uncovered,
        notes=rules_report.notes,
        rules_sections=from_rules,
    )


def make_feedback(
    transcript: Iterable[SafeTurn],
    plan: SafePlan,
    *,
    resources: Resources | None = None,
    skills: SkillDictionary | None = None,
    blocklists: Sequence[Blocklist] = (),
    llm: LLMClient | None = None,
) -> FeedbackReport:
    """The final feedback. `transcript` and `plan` are the outputs of `transcript_view` / `plan_view` (or `*_from`), nothing else.
    Never raises on a model problem: the rules report is computed first, and any failure of the call, an invalid answer or an
    answer with nothing usable returns it unchanged (D54). One request to the model at most."""
    lines = _check_inputs(transcript, plan)
    ctx = _context(lines, plan, skills)
    fallback = _rules(ctx, plan, resources, skills, blocklists)
    if llm is None:
        return fallback
    request = _request(ctx, plan, blocklists, skills)
    if request is None:
        return fallback
    try:
        raw = ask(llm, request.model_input)
    except Exception as e:  # noqa: BLE001  (every failure means the rules report; only the type is logged, never any text)
        log.warning("interview feedback by the model failed (%s); using the rules", type(e).__name__)
        return fallback
    parsed, reason = parse_feedback(request, raw)
    if parsed is None:
        log.warning("interview feedback by the model rejected (%s); using the rules", reason)
        return fallback
    return _merge(fallback, parsed, ctx, f"llm:{getattr(llm, 'model', 'unknown')}", resources, skills)
