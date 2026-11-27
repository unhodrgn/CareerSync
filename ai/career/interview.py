"""Interview practice questions for one job (docs/DECISIONS.md D21). LLM when configured, templates otherwise.

The LLM sees the JD, the criteria (no weights) and up to 4 excerpts of the masked CV. Its output is checked:
`criterion_id` must be a criterion of the job (else null), `cv_quote` must be in the masked CV
(`verify_quotes`, else null), URLs are stripped. Every question — LLM or template — must pass the criteria
guardrail (data/blocklist.yaml) and then the interview blocklist (data/interview_blocklist.yaml, written for
questions: marriage, children, dating, religion, age, appearance, origin, family, politics, health), checked
on the question, its intent and its tips; a hit drops the question. Fewer than MIN_QUESTIONS left → the template.
"""
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ai.embedding.model import Embedder
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.criteria import check_criterion
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR
from ai.scoring.retrieval import cv_chunks, retrieve

log = logging.getLogger(__name__)

MIN_QUESTIONS, MAX_QUESTIONS, MAX_BANK_QUESTIONS, MAX_EXCERPTS = 3, 10, 45, 4
DEPTHS: tuple[int, ...] = (1, 2, 3)
Depth = Literal[1, 2, 3]
Kind = Literal["technical", "experience", "behavioral"]
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)


@dataclass(frozen=True)
class CriterionInfo:
    id: int
    name: str
    category: str
    description: str = ""


@dataclass(frozen=True)
class Question:
    question: str
    criterion_id: int | None
    criterion_name: str | None
    kind: str
    intent: str
    answer_tips: tuple[str, ...]
    cv_quote: str | None = None
    depth: int | None = None


class _LlmQuestion(BaseModel):
    question: str = Field(max_length=300)
    criterion_id: int | None = None
    kind: Kind
    intent: str = Field(max_length=200)
    answer_tips: list[str] = Field(default_factory=list, max_length=3)
    cv_quote: str | None = Field(None, max_length=300)
    depth: Depth | None = None

    @field_validator("depth", mode="before")
    @classmethod
    def _coerce_depth(cls, value: object) -> int | None:
        # Coerce invalid model depths to None so validation can keep the question or fill missing depths from templates.
        return value if type(value) is int and value in DEPTHS else None


class InterviewLlmOut(BaseModel):
    questions: list[_LlmQuestion] = Field(max_length=MAX_BANK_QUESTIONS)


def _clean(text: str, limit: int) -> str:
    return " ".join(_URL.sub("", text).split())[:limit]


# ── Template (AI_MODE=rules) ──

_TIPS_EXPERIENCE = ("Describe the situation and your role first", "Explain the challenges and how you resolved them step by step", "Close with measurable results and lessons learned")
_TIPS_BY_DEPTH: dict[tuple[str, int], tuple[str, ...]] = {
    ("technical", 1): ("Define the core concept clearly first", "Explain why it is needed and its main benefits", "Include one brief usage example"),
    ("technical", 2): ("Share a concrete example from production or a project", "Explain problems you encountered and how you fixed them", "Mention the outcome or key caveats"),
    ("technical", 3): ("Compare architectural trade-offs and design choices", "Discuss troubleshooting or scalability considerations", "Explain why you chose it over alternatives"),
    ("other", 1): ("State the core context and why it matters first", "Summarize your principles or perspective concisely", "Connect it to a brief relevant experience"),
    ("other", 2): _TIPS_EXPERIENCE,
    ("other", 3): ("Explain the options and trade-offs you weighed", "Walk through the root cause and resolution steps concretely", "Close with how you prevented recurrence or improved the process"),
}
_BY_CATEGORY: dict[str, dict[int, tuple[str, Kind, str]]] = {
    # category: {depth: (question template, kind, intent template)}
    "skill": {
        1: ("What is the core concept of {name}, and why is it used?", "technical", "Check understanding of core {name} concepts and purpose"),
        2: ("Can you share a concrete example of how you used {name} in work or a project?", "technical", "Check hands-on experience and understanding of {name}"),
        3: ("What trade-offs, performance or scalability challenges, and alternatives do you consider when adopting or designing with {name}?", "technical", "Check advanced design, troubleshooting, and trade-off reasoning for {name}"),
    },
    "experience": {
        1: ("Why is competency in '{name}' important in day-to-day engineering work?", "experience", "Check foundational understanding and awareness of '{name}'"),
        2: ("Tell me about the experience in your career most relevant to '{name}'.", "experience", "Check depth of relevant work experience"),
        3: ("Describe a complex issue or incident in '{name}' where you diagnosed the root cause and improved the system or process.", "experience", "Check advanced problem-solving, trade-offs, and improvement ownership"),
    },
    "project": {
        1: ("What do you consider the most important principle when working on a project like '{name}'?", "experience", "Check baseline project understanding and approach for '{name}'"),
        2: ("Describe your role and measurable outcomes in a project related to '{name}'.", "experience", "Check project execution and individual contribution"),
        3: ("In a project related to '{name}', tell me about a key architecture trade-off, bottleneck fix, or scaling improvement you made.", "experience", "Check project design trade-offs, troubleshooting, and scaling depth"),
    },
    "certificate": {
        1: ("What are the core areas covered by {name}, and why do they matter for this role?", "technical", "Check understanding of {name} core concepts and job relevance"),
        2: ("How can you apply what you studied for {name} to daily work in this role?", "technical", "Check practical application of certification knowledge"),
        3: ("How would you use the principles from {name} in system design, troubleshooting, or evaluating alternatives?", "technical", "Check advanced design and problem-solving application of credential knowledge"),
    },
    "education": {
        1: ("Which foundational concepts from your major connect most closely to this role, and why?", "experience", "Check foundational academic knowledge and job relevance"),
        2: ("What part of your academic coursework has been most useful in practice?", "experience", "Check connection between academic study and practical work"),
        3: ("Have you applied principles from your major to analyze a design limitation, compare alternatives, and solve a real problem?", "experience", "Check advanced application, analysis, and trade-off thinking from coursework"),
    },
    "other": {
        1: ("Why do you think '{name}' is important for a team and its day-to-day work?", "behavioral", "Check baseline understanding of why '{name}' matters"),
        2: ("Tell me about an experience where you demonstrated '{name}'.", "behavioral", "Check attitude and past experience related to '{name}'"),
        3: ("Tell me about a time '{name}' involved competing priorities or technical disagreement, and how you navigated the trade-offs.", "behavioral", "Check complex judgment and conflict/problem resolution around '{name}'"),
    },
}
_GENERAL = (
    Question("What drew you to this company and role?", None, None, "behavioral", "Check motivation and understanding of the role",
             ("Highlight specific aspects of the company and role", "Connect them to your own background")),
    Question("Tell me about a time your team disagreed on an approach and how you resolved it.", None, None, "behavioral", "Check collaboration and communication style",
             _TIPS_EXPERIENCE),
    Question("Tell me about a technology you learned recently and how you studied it.", None, None, "behavioral", "Check learning mindset and growth potential",
             ("Explain what you learned and why", "Show how you put it into practice")),
)


def _template_question(c: CriterionInfo, depth: int) -> Question:
    by_depth = _BY_CATEGORY.get(c.category, _BY_CATEGORY["other"])
    template, kind, intent = by_depth[depth]
    tip_group = "technical" if kind == "technical" else "other"
    tips = _TIPS_BY_DEPTH[(tip_group, depth)]
    return Question(template.format(name=c.name), c.id, c.name, kind, intent.format(name=c.name), tips, depth=depth)


def allowed(question: str, intent: str, tips: Sequence[str], blocklists: Sequence[Blocklist]) -> bool:
    """False when any blocklist matches the question, its intent or a tip."""
    detail = " ".join([intent, *tips])
    return all(check_criterion(question, detail, bl).allowed for bl in blocklists)


def _log_dropped(reason: str, source: str, criterion_id: int | None) -> None:
    """What may be logged about a question that was dropped: why, where it came from and which criterion it was for (a number of the
    job's own criteria). Never its text, which can quote the CV (D65)."""
    log.info("interview question dropped: reason=%s source=%s criterion_id=%s", reason, source, criterion_id)


def screen(questions: list[Question], blocklists: Sequence[Blocklist]) -> list[Question]:
    kept = [q for q in questions if allowed(q.question, q.intent, q.answer_tips, blocklists)]
    for q in questions:
        if q not in kept:
            _log_dropped("blocklist", "template", q.criterion_id)
    return kept


def interview_rules(
    criteria: list[CriterionInfo],
    blocklists: Sequence[Blocklist] = (),
    *,
    depths: Sequence[int] = DEPTHS,
    max_questions: int = MAX_BANK_QUESTIONS,
) -> list[Question]:
    """Template questions, screened like LLM ones (a criterion name could carry a blocked word)."""
    out = [_template_question(c, d) for c in criteria for d in depths]
    seen, unique = set(), []
    for q in [*out, *_GENERAL]:  # education/experience templates do not depend on the name: keep one each
        if q.question not in seen:
            seen.add(q.question)
            unique.append(q)
    return screen(unique, blocklists)[:max_questions]


# ── LLM ──


def cv_excerpts(masked_text: str, query: str, embedder: Embedder) -> list[str]:
    """Up to MAX_EXCERPTS chunks of the masked CV most relevant to the job."""
    passages = retrieve(query, cv_chunks(masked_text), embedder, k=MAX_EXCERPTS, prefer=("project", "experience"))
    return [p.chunk.text for p in passages]


def _llm_input(job_title: str, job_text: str, criteria: list[CriterionInfo], excerpts: list[str]) -> str:
    lines = [f"{c.id} | {c.name} | {c.category} | {c.description}" for c in criteria]
    parts = ["<job>", job_title, job_text, "</job>", "<criteria>", *lines, "</criteria>"]
    parts += ["<cv_excerpts>", "\n---\n".join(excerpts), "</cv_excerpts>"]
    return "\n".join(parts)


def _select_single_per_criterion(questions: list[Question], preferred_depth: int, limit: int) -> list[Question]:
    """Keep at most one question per criterion (preferring `preferred_depth`, then untagged/nearest) plus general questions."""
    rank = {preferred_depth: 0, None: 1}
    for idx, d in enumerate((2, 1, 3), start=2):
        rank.setdefault(d, idx)
    by_cid: dict[int, list[Question]] = {}
    order: list[int | None] = []
    general: list[Question] = []
    for q in questions:
        if q.criterion_id is None:
            general.append(q)
        else:
            if q.criterion_id not in by_cid:
                order.append(q.criterion_id)
            by_cid.setdefault(q.criterion_id, []).append(q)
    selected: list[Question] = []
    for cid in order:
        best = min(by_cid[cid], key=lambda item: rank.get(item.depth, 99))
        selected.append(best)
    selected.extend(general)
    if len(selected) < MIN_QUESTIONS:
        picked = set(id(q) for q in selected)
        for q in questions:
            if id(q) not in picked:
                selected.append(q)
                if len(selected) >= MIN_QUESTIONS:
                    break
    return selected[:limit]


def interview_llm(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    excerpts: list[str],
    masked_text: str,
    blocklists: Sequence[Blocklist],
    llm: LLMClient,
    *,
    depths: Sequence[int] = DEPTHS,
    fill_missing: bool = True,
    max_questions: int = MAX_BANK_QUESTIONS,
    single_depth: int | None = None,
) -> list[Question]:
    """Validated LLM questions. Raises LLMError when fewer than MIN_QUESTIONS survive the checks."""
    prompt = (PROMPT_DIR / "interview_questions.md").read_text(encoding="utf-8")
    out = llm.complete_json(prompt, _llm_input(job_title, job_text, criteria, excerpts), InterviewLlmOut, max_tokens=8000)
    names = {c.id: c.name for c in criteria}
    kept, seen = [], set()
    for q in out.questions:
        text = _clean(q.question, 300)
        if not text or text in seen:
            continue
        intent = _clean(q.intent, 200)
        tips = tuple(t for t in (_clean(x, 150) for x in q.answer_tips) if t)
        cid = q.criterion_id if q.criterion_id in names else None
        # Questions about protected attributes (age, family, origin, …) are dropped
        if not allowed(text, intent, tips, blocklists):
            _log_dropped("blocklist", "llm", cid)
            continue
        depth = q.depth if cid is not None and type(q.depth) is int and q.depth in DEPTHS else None
        verified = verify_quotes([q.cv_quote], masked_text) if q.cv_quote else []
        seen.add(text)
        kept.append(Question(text, cid, names.get(cid), q.kind, intent, tips, verified[0] if verified else None, depth))
    if len(kept) < MIN_QUESTIONS:
        raise LLMError(f"interview: only {len(kept)} usable questions")
    if fill_missing:
        covered = {(q.criterion_id, q.depth) for q in kept if q.criterion_id is not None and q.depth is not None}
        for c in criteria:
            for d in depths:
                if (c.id, d) in covered:
                    continue
                tq = _template_question(c, d)
                if tq.question in seen:
                    continue
                if not allowed(tq.question, tq.intent, tq.answer_tips, blocklists):
                    _log_dropped("blocklist", "template", c.id)
                    continue
                seen.add(tq.question)
                kept.append(tq)
                covered.add((c.id, d))
    if single_depth is not None:
        return _select_single_per_criterion(kept, single_depth, max_questions)
    return kept[:max_questions]


def make_questions(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    masked_text: str,
    embedder: Embedder,
    blocklists: Sequence[Blocklist],
    llm: LLMClient | None,
    *,
    depths: Sequence[int] = DEPTHS,
    fill_missing: bool = True,
    max_questions: int = MAX_BANK_QUESTIONS,
    single_depth: int | None = None,
) -> tuple[list[Question], str]:
    """`blocklists`: the criteria guardrail first, then the interview blocklist.
    (questions, method); method is "llm:<model>" or "rules". LLM failures fall back to the template."""
    if llm is not None:
        query = " ".join([job_title, *(c.name for c in criteria)])
        try:
            excerpts = cv_excerpts(masked_text, query, embedder)
            return (
                interview_llm(
                    job_title,
                    job_text,
                    criteria,
                    excerpts,
                    masked_text,
                    blocklists,
                    llm,
                    depths=depths,
                    fill_missing=fill_missing,
                    max_questions=max_questions,
                    single_depth=single_depth,
                ),
                f"llm:{llm.model}",
            )
        except LLMError as e:
            # The type only: the message of an LLM error can quote the model's output, which can quote CV lines (D65)
            log.warning("interview questions by LLM failed, using the template: %s", type(e).__name__)
    return interview_rules(criteria, blocklists, depths=depths, max_questions=max_questions), "rules"
