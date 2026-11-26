"""Build the interview plan: which questions, in which order, each with its rubric points (docs/DECISIONS.md D51, D57).

Deterministic: the same criteria, question bank and CV lines always give the same plan, whatever order the criteria arrive
in. The question bank is the D21 one (`ai.career.interview`: LLM or template questions, both blocklists), reused as it is;
a criterion without a usable bank question gets the D21 template, then a neutral fallback question.

Shape of a plan: an optional CV-grounded warm-up, the criteria by importance (핵심, 중요, 일반; then their order in the job),
and one behavioral question last. The number of questions is capped (`InterviewLimits.max_questions`). A 핵심 criterion
outranks the warm-up; a criterion that gets no slot is listed in `plan.uncovered`, never dropped silently. No weights
anywhere: criteria arrive with their importance label only (D30).
"""
from collections.abc import Iterable, Sequence

from ai.career.interview import CriterionInfo, Question, allowed, interview_rules
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.evidence import verify_quotes
from ai.interview import rules
from ai.interview.cv_context import CleanCv, clean_cv
from ai.interview.guards import is_duplicate, screen_spoken
from ai.interview.sensitive import for_model_block, is_sensitive
from ai.interview.types import (
    DEFAULT_LIMITS,
    IMPORTANCE_RANK,
    InterviewLimits,
    InterviewPlan,
    PlanCriterion,
    PlanItem,
    UncoveredCriterion,
)
from ai.interview.validate import validate_plan
from ai.parsing.sections import heading_key
from ai.scoring.retrieval import has_content

_EVIDENCE_MIN_CHARS, _EVIDENCE_MAX_CHARS = 12, 90
_TIPS = ("상황과 본인의 역할을 먼저 설명하기", "어려웠던 점과 해결 과정을 구체적으로", "결과와 배운 점으로 마무리하기")
_KIND = {"skill": "technical", "certificate": "technical", "other": "behavioral"}  # any other category: "experience"
_VALID_DEPTHS = frozenset({1, 2, 3})


def _depth_order(depth: int) -> tuple[int, ...]:
    """Requested depth first, then nearest other depth (2 first, then the other)."""
    if depth == 1:
        return (1, 2, 3)
    if depth == 2:
        return (2, 1, 3)
    return (3, 2, 1)


def evidence_lines(excerpts: Iterable[str]) -> list[str]:
    """Lines of the masked CV excerpts that can ground a warm-up question: bullet lines first, then the others.
    No headings, no contact lines, nothing with a placeholder in it, nothing about age, gender or military service, a
    readable length."""
    bullets: list[str] = []
    others: list[str] = []
    for excerpt in excerpts:
        for raw in excerpt.splitlines():
            line = raw.strip().lstrip("-•*· ").strip()
            if not _EVIDENCE_MIN_CHARS <= len(line) <= _EVIDENCE_MAX_CHARS or "[" in line or "]" in line:
                continue
            if heading_key(line) is not None or not has_content(line):
                continue
            if is_sensitive(line):  # a CV line about age, gender or military service is never read out as a question
                continue
            target = bullets if raw.strip().startswith(("-", "•", "*", "·")) else others
            if line not in bullets and line not in others:
                target.append(line)
    return bullets + others


def _screened(q: Question, blocklists: Sequence[Blocklist], clean: CleanCv) -> bool:
    """A question is usable when its intent and tips pass the blocklists (D21), the spoken question passes every guard, and
    nothing of it (question, intent, tips, quote) matches the age, gender and military-service vocabulary or contains a line
    that `clean_cv` removed from the CV (D61, D62). `validate_plan` checks the finished plan again."""
    if any(is_sensitive(text) or clean.mentions_removed(text) for text in (q.question, q.intent, q.cv_quote or "", *q.answer_tips)):
        return False
    return allowed(q.question, q.intent, q.answer_tips, blocklists) and screen_spoken(q.question, blocklists, "question") is not None


def _item(
    topic_id: str,
    q: Question,
    *,
    category: str,
    name: str | None,
    description: str,
    importance: str | None,
    blocklists: Sequence[Blocklist],
    skills: SkillDictionary | None,
    topic_text: Sequence[str],
) -> PlanItem:
    rephrase = rules.rephrase_text(name, q.kind)
    if screen_spoken(rephrase, blocklists) is None:
        rephrase = rules.GENERIC_REPHRASE
    keywords = () if q.kind == "behavioral" else rules.topic_keywords(*topic_text, skills=skills)
    depth = q.depth if q.criterion_id is not None and type(q.depth) is int and q.depth in _VALID_DEPTHS else None
    return PlanItem(
        topic_id=topic_id,
        kind=q.kind,
        question=q.question,
        rephrase=rephrase,
        rubric=rules.make_rubric(name or "이 질문", category, description, skills),
        topic_keywords=keywords,
        criterion_id=q.criterion_id,
        criterion_name=name,
        importance=importance,  # type: ignore[arg-type]
        intent=q.intent,
        answer_tips=tuple(q.answer_tips),
        cv_quote=q.cv_quote,
        depth=depth,
    )


def _criterion_item(
    c: PlanCriterion,
    bank: dict[int, list[Question]],
    asked: Sequence[str],
    blocklists: Sequence[Blocklist],
    skills: SkillDictionary | None,
    clean: CleanCv,
    depth: int,
) -> PlanItem | None:
    description = for_model_block(c.description)  # the company's text, cut of what touches age, gender or military service
    bank_questions = list(bank.get(c.id, ()))
    info = CriterionInfo(c.id, c.name, c.category, description)
    templates = [q for q in interview_rules([info], blocklists) if q.criterion_id == c.id]
    candidates: list[Question] = []
    for d in _depth_order(depth):
        candidates.extend(q for q in bank_questions if type(q.depth) is int and q.depth == d)
        candidates.extend(q for q in templates if type(q.depth) is int and q.depth == d)
    candidates.extend(q for q in bank_questions if not (type(q.depth) is int and q.depth in _VALID_DEPTHS))
    fallback = Question(
        rules.fallback_question(c.name), c.id, c.name, _KIND.get(c.category, "experience"), f"'{c.name}' 관련 경험과 이해 수준 확인", _TIPS[:2]
    )
    for q in [*candidates, fallback]:
        # Exact duplicates only: templates of two criteria differ in the name alone and are still two questions
        if _screened(q, blocklists, clean) and not is_duplicate(q.question, asked, ratio=1.0):
            return _item(
                f"c{c.id}",
                q,
                category=c.category,
                name=c.name,
                description=description,
                importance=c.importance,
                blocklists=blocklists,
                skills=skills,
                topic_text=(c.name, description),
            )
    return None


def _warmup(
    general: Sequence[Question], lines: Sequence[str], clean: CleanCv, blocklists: Sequence[Blocklist], skills: SkillDictionary | None
) -> PlanItem | None:
    """A question grounded in a line of the candidate's own CV, or None when the CV gives no usable line. `clean` is the
    cleaned CV (`clean_cv`): a quote or line that is not in it, however it got here, grounds nothing."""
    for q in general:  # an LLM bank question that already quotes the CV (verified there, and again here)
        if q.cv_quote and q.kind != "behavioral" and verify_quotes([q.cv_quote], clean.text) and _screened(q, blocklists, clean):
            return _item("warmup", q, category="experience", name=None, description="", importance=None,
                         blocklists=blocklists, skills=skills, topic_text=(q.cv_quote,))
    for line in evidence_lines(lines):  # the caller's lines get the same filters as lines made by `evidence_lines`
        if not clean.contains(line):  # word for word: a line that only resembles a cleaned one is not grounded
            continue
        q = Question(rules.warmup_question(line), None, None, "experience", "이력서에 적은 경험의 역할과 기여 확인", _TIPS, line)
        if _screened(q, blocklists, clean):
            return _item("warmup", q, category="experience", name=None, description="", importance=None,
                         blocklists=blocklists, skills=skills, topic_text=(line,))
    return None


def _behavioral(general: Sequence[Question], blocklists: Sequence[Blocklist], skills: SkillDictionary | None, clean: CleanCv) -> PlanItem | None:
    pool = [q for q in general if q.kind == "behavioral"]
    pool += [q for q in interview_rules([], blocklists) if q.kind == "behavioral"]  # the D21 general questions
    for q in pool:
        if _screened(q, blocklists, clean):
            return _item("behavioral", q, category="other", name=None, description="", importance=None,
                         blocklists=blocklists, skills=skills, topic_text=())
    return None


def build_plan(
    criteria: Sequence[PlanCriterion],
    questions: Sequence[Question] = (),
    masked_cv: str = "",
    cv_lines: Sequence[str] = (),
    blocklists: Sequence[Blocklist] = (),
    limits: InterviewLimits = DEFAULT_LIMITS,
    skills: SkillDictionary | None = None,
    bank_method: str = "rules",
    depth: int = 2,
) -> InterviewPlan:
    """`questions`: the D21 bank (may be empty, never trusted). `cv_lines`: candidate lines from `evidence_lines` over the CV
    excerpts. `masked_cv`: the stored masked CV. It is cleaned here (`clean_cv`, D62) and every quote and line is verified
    against the cleaned text only. The finished plan then goes through `validate_plan` (D61), the same function the engine
    applies to any plan it is given, so a bank question, its intent, tips and quote, and the rubric are all checked."""
    if type(depth) is not int or depth not in _VALID_DEPTHS:
        raise ValueError("depth must be 1, 2, or 3")
    for c in criteria:
        if c.importance not in IMPORTANCE_RANK:
            raise ValueError(f"criterion {c.id}: importance must be one of {', '.join(IMPORTANCE_RANK)}")
    ordered = sorted({c.id: c for c in criteria}.values(), key=lambda c: (IMPORTANCE_RANK[c.importance], c.position, c.id))
    bank: dict[int, list[Question]] = {}
    general: list[Question] = []
    for q in questions:
        if q.criterion_id is None:
            general.append(q)
        else:
            bank.setdefault(q.criterion_id, []).append(q)

    clean = clean_cv(masked_cv)
    warmup = _warmup(general, cv_lines, clean, blocklists, skills)
    behavioral = _behavioral(general, blocklists, skills, clean)
    asked = [i.question for i in (warmup, behavioral) if i is not None]
    built: list[tuple[PlanCriterion, PlanItem | None]] = []
    for c in ordered:
        item = _criterion_item(c, bank, asked, blocklists, skills, clean, depth)
        if item is not None:
            asked.append(item.question)
        built.append((c, item))

    slots = limits.max_questions - (behavioral is not None) - (warmup is not None)
    core = sum(1 for c, item in built if item is not None and c.importance == "핵심")
    if warmup is not None and core > slots:  # a 핵심 criterion outranks the warm-up
        warmup, slots = None, slots + 1
    slots = max(0, slots)
    eligible = [(c, item) for c, item in built if item is not None]
    uncovered = [UncoveredCriterion(c.id, c.name, c.importance, "no_slot") for c, _ in eligible[slots:]]
    uncovered += [UncoveredCriterion(c.id, c.name, c.importance, "no_question") for c, item in built if item is None]
    items = [i for i in (warmup,) if i is not None] + [item for _, item in eligible[:slots]] + [i for i in (behavioral,) if i is not None]
    plan = InterviewPlan(tuple(items), tuple(uncovered), bank_method=bank_method, depth=depth)
    return validate_plan(plan, blocklists=blocklists, cv_text=masked_cv, skills=skills).plan
