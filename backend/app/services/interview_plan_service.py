"""The plan of a practice interview, made from the job and the CV and sealed in the one form the backend stores
(docs/DECISIONS.md D51, D52, D61, D62, D63).

The CV boundary (every line of it is enforced by a test, `ai/tests/test_interview_backend_boundary.py`):

1. `stored_cv`, the stored masked CV (it still has age, gender and military-service text, Q24), is used in exactly two
   places: `clean_cv(stored_cv)` and `build_plan(..., stored_cv, ...)`. Both are deterministic, local code. Nothing else sees it.
2. The planning model gets `clean.text` only, through `make_bank` -> `make_questions` -> `GatedClient` -> `compose` -> `ask`
   (`ai.interview.cv_context`, `ai.interview.boundary`). The model call, if any, is the one inside `make_bank`.
3. `build_plan` is given the stored text, not the cleaned one, on purpose: it cleans it itself and keeps `CleanCv.removed`,
   the lines `clean_cv` took out, to refuse a question that brings one of them back (D62). Given the cleaned text, that check
   would see nothing to compare with.
4. The bank is pre-filtered (`prefilter_bank`): a question that repeats a line of the cleaned CV word for word (12 characters
   or more), or a removed line, is dropped, and every `cv_quote` is cleared. `cv_lines` is empty, so there is no CV-grounded
   warm-up (R1): a warm-up question is a CV line read out.
5. The plan is validated twice more without the CV (`validate_plan(cv_text=None)`) and must not change nor report an issue, so
   what is stored is a fixed point of the validation that the engine and the views apply to a plan loaded from storage. A last
   scan (`leaks`) refuses a plan that still repeats a CV line or a removed line.

What is stored is `CanonicalPlan.data` and its SHA-256: never the raw or cleaned CV, an excerpt, a `cv_quote`, the question bank
or a weight. What it can still hold: professional questions that the model or a template wrote from the sanitized CV, which may
paraphrase it ("Java와 Spring Boot 경험을 설명해 주세요" after a CV line about Spring Boot). The word-for-word check cannot see a paraphrase, and
`clean_cv` is a vocabulary cut, so this is best effort and not a guarantee that the plan holds no CV-derived information.

Serialization (`seal`) is kept out of the function that calls the model-input builders on purpose: the architecture test
forbids raw serialization there.
"""
import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace

from ai.career.interview import CriterionInfo, Question
from ai.embedding.model import Embedder
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.interview import CleanCv, InterviewLimits, InterviewPlan, PlanCriterion, build_plan, clean_cv, make_bank, validate_plan
from ai.llm.client import LLMClient
from app.core.config import settings

NUL = "\x00"  # PostgreSQL TEXT and JSONB cannot hold it: a plan that has one is refused, never cleaned (D65)
MIN_CV_LINE_CHARS = 12  # a CV line shorter than this ("Java", "Spring Boot") is a word, not an excerpt
_BULLETS = "-•*·▪ "


class PlanRefused(Exception):
    """A plan that must not be stored. `code` says why and is never text of the plan or the CV."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _any_text(value: object, bad) -> bool:
    """True when `bad(text)` holds for a string anywhere in `value`: a string, the keys and values of a mapping, the items of a list, tuple
    or set, and the fields of a dataclass (a `Question` of the bank, a plan item). Pure and recursive; it never changes what it reads."""
    if isinstance(value, str):
        return bad(value)
    if isinstance(value, Mapping):
        return any(_any_text(key, bad) or _any_text(item, bad) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_any_text(item, bad) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return any(_any_text(getattr(value, field.name), bad) for field in fields(value))
    return False


def has_nul(value: object) -> bool:
    """True when U+0000 is in a string anywhere in `value` (see `_any_text`)."""
    return _any_text(value, lambda text: NUL in text)


def has_surrogate(value: object) -> bool:
    """True when a surrogate code point (0xD800 to 0xDFFF) is in a string anywhere in `value`. A valid pair is one character in a `str`
    (decoding JSON makes it one), so any that is left is not text: JSONB refuses it and UTF-8 cannot encode it (D73)."""
    return _any_text(value, lambda text: any(0xD800 <= ord(char) <= 0xDFFF for char in text))


@dataclass(frozen=True)
class CanonicalPlan:
    plan: InterviewPlan
    data: dict  # what is stored in `interview_sessions.plan`
    sha256: str  # of `data`, canonical JSON
    method: str  # how the question bank was made: "rules" or "llm:<model>"


def limits_from_settings() -> InterviewLimits:
    return InterviewLimits(
        max_questions=settings.INTERVIEW_MAX_QUESTIONS,
        max_seconds=settings.INTERVIEW_MAX_SECONDS,
        max_followups_per_item=settings.INTERVIEW_MAX_FOLLOWUPS_PER_ITEM,
        max_clarifies_per_item=settings.INTERVIEW_MAX_CLARIFIES_PER_ITEM,
        silence_nudge_seconds=settings.INTERVIEW_SILENCE_NUDGE_SECONDS,
        silence_skip_seconds=settings.INTERVIEW_SILENCE_SKIP_SECONDS,
        turn_llm_deadline_seconds=settings.INTERVIEW_TURN_LLM_DEADLINE_SECONDS,
    )


def limits_data(limits: InterviewLimits) -> dict[str, int]:
    """The limits of a session as stored (`interview_sessions.limits`)."""
    return {
        "max_questions": limits.max_questions,
        "max_seconds": limits.max_seconds,
        "max_followups_per_item": limits.max_followups_per_item,
        "max_clarifies_per_item": limits.max_clarifies_per_item,
        "silence_nudge_seconds": limits.silence_nudge_seconds,
        "silence_skip_seconds": limits.silence_skip_seconds,
        "turn_llm_deadline_seconds": limits.turn_llm_deadline_seconds,
        "wrap_reserve_seconds": limits.wrap_reserve_seconds,
    }


def plan_digest(data: dict) -> str:
    """SHA-256 of the canonical JSON of a stored plan (sorted keys, no spaces)."""
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_canonical_plan(
    *,
    stored_cv: str,
    job_title: str,
    job_text: str,
    criteria: Sequence[PlanCriterion],
    blocklists: Sequence[Blocklist],
    embedder: Embedder,
    skills: SkillDictionary | None,
    limits: InterviewLimits,
    llm: LLMClient | None,
    depth: int = 2,
) -> CanonicalPlan:
    """The plan to store, or `PlanRefused`. `llm` is None when no model attempt may be made (rules mode, the model quota
    used up): the bank is then the D21 template. This function calls the model (inside `make_bank`) and must be called with
    no database transaction open."""
    clean = clean_cv(stored_cv)
    if has_nul(clean.text):  # before any model sees it, and before anything is made from it
        raise PlanRefused("nul_cv")
    infos = [CriterionInfo(c.id, c.name, c.category, c.description) for c in criteria]
    bank, method = make_bank(job_title, job_text, infos, clean.text, embedder, blocklists, llm)
    if has_nul(bank):  # the generated questions, intents, tips and quotes
        raise PlanRefused("nul_bank")
    if has_surrogate(bank):  # a surrogate is refused the same way (D73)
        raise PlanRefused("surrogate_bank")
    plan = build_plan(criteria, prefilter_bank(bank, clean), stored_cv, (), blocklists, limits, skills, method, depth)
    return seal(plan, clean, blocklists)


def prefilter_bank(bank: Sequence[Question], clean: CleanCv) -> list[Question]:
    """The bank without the questions that repeat the CV, and without any `cv_quote`. Exact lines only: a paraphrase passes."""
    lines = _cv_lines(clean)
    kept: list[Question] = []
    for q in bank:
        texts = [t for t in (q.question, q.intent, *q.answer_tips) if t]
        if any(_copies(t, lines) or clean.mentions_removed(t) for t in texts):
            continue
        kept.append(replace(q, cv_quote=None))
    return kept


def seal(plan: InterviewPlan, clean: CleanCv, blocklists: Sequence[Blocklist]) -> CanonicalPlan:
    """The canonical form of a plan, or `PlanRefused`. Pure: no model, no database."""
    if not plan.items:
        raise PlanRefused("empty_plan")
    first = validate_plan(plan, blocklists=blocklists, cv_text=None)
    if first.issues or first.plan != plan:
        raise PlanRefused("not_canonical")
    second = validate_plan(first.plan, blocklists=blocklists, cv_text=None)
    if second.issues or second.plan != first.plan:
        raise PlanRefused("not_a_fixed_point")
    final = first.plan
    if any(item.cv_quote is not None for item in final.items):
        raise PlanRefused("cv_quote")
    if leaks(final, clean):
        raise PlanRefused("cv_text")
    data = final.to_dict()
    if has_nul(data):  # every string that will be stored, keys included
        raise PlanRefused("nul_plan")
    if has_surrogate(data):  # before `plan_digest`, whose UTF-8 encoding would raise on one (D73)
        raise PlanRefused("surrogate_plan")
    return CanonicalPlan(final, data, plan_digest(data), final.bank_method)


def leaks(plan: InterviewPlan, clean: CleanCv) -> bool:
    """True when a spoken or explanatory text of the plan repeats a line of the cleaned CV (12+ characters, word for word), or any
    text of the plan contains a line that `clean_cv` removed."""
    lines = _cv_lines(clean)
    for item in plan.items:
        if any(_copies(text, lines) for text in (item.question, item.rephrase, item.intent, *item.answer_tips)):
            return True
    return any(clean.mentions_removed(text) for text in _texts(plan))


def _texts(plan: InterviewPlan):
    for item in plan.items:
        yield from (item.question, item.rephrase, item.intent, item.criterion_name or "", item.cv_quote or "")
        yield from item.answer_tips
        yield from item.topic_keywords
        for point in item.rubric:
            yield point.text
            yield from point.keywords
    for entry in plan.uncovered:
        yield entry.name


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).lower()


def _cv_lines(clean: CleanCv) -> tuple[str, ...]:
    lines = (_norm(raw.strip().lstrip(_BULLETS)) for raw in clean.text.splitlines())
    return tuple(dict.fromkeys(line for line in lines if len(line) >= MIN_CV_LINE_CHARS))


def _copies(text: str, lines: Sequence[str]) -> bool:
    norm = _norm(text)
    return any(line in norm for line in lines)
