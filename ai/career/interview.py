"""Interview practice questions for one job (docs/DECISIONS.md D21). LLM when configured, templates otherwise.

The LLM sees the JD, the criteria (no weights) and up to 4 excerpts of the masked CV. Its output is checked:
`criterion_id` must be a criterion of the job (else null), `cv_quote` must be in the masked CV
(`verify_quotes`, else null), every question must pass the criteria guardrail (data/blocklist.yaml, else
dropped), URLs are stripped. Fewer than MIN_QUESTIONS left → the template.
"""
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from ai.embedding.model import Embedder
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.criteria import check_criterion
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR
from ai.scoring.retrieval import cv_chunks, retrieve

log = logging.getLogger(__name__)

MIN_QUESTIONS, MAX_QUESTIONS, MAX_EXCERPTS = 3, 10, 4
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


class _LlmQuestion(BaseModel):
    question: str = Field(max_length=300)
    criterion_id: int | None = None
    kind: Kind
    intent: str = Field(max_length=200)
    answer_tips: list[str] = Field(default_factory=list, max_length=3)
    cv_quote: str | None = Field(None, max_length=300)


class InterviewLlmOut(BaseModel):
    questions: list[_LlmQuestion] = Field(max_length=MAX_QUESTIONS)


def _clean(text: str, limit: int) -> str:
    return " ".join(_URL.sub("", text).split())[:limit]


# ── Template (AI_MODE=rules) ──

_TIPS_EXPERIENCE = ("상황과 본인의 역할을 먼저 설명하기", "어려웠던 점과 해결 과정을 구체적으로", "결과와 배운 점으로 마무리하기")
_BY_CATEGORY: dict[str, tuple[str, str, str]] = {
    # category: (question template, kind, intent template)
    "skill": ("{name}을(를) 실무나 프로젝트에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요.", "technical", "{name} 활용 경험과 이해 수준 확인"),
    "experience": ("지금까지의 경력 중 '{name}'와(과) 가장 관련 있는 경험을 소개해 주세요.", "experience", "직무 관련 경력의 깊이 확인"),
    "project": ("'{name}'와(과) 관련해 진행한 프로젝트에서 맡은 역할과 성과를 설명해 주세요.", "experience", "프로젝트 수행 방식과 기여도 확인"),
    "certificate": ("{name} 준비 과정에서 익힌 지식을 이 직무에 어떻게 적용할 수 있을까요?", "technical", "자격 관련 지식의 실무 적용 능력 확인"),
    "education": ("전공에서 배운 내용 중 이 직무에 가장 도움이 되는 것은 무엇인가요?", "experience", "전공 지식과 직무의 연결 확인"),
    "other": ("'{name}'에 해당하는 본인의 경험을 사례로 설명해 주세요.", "behavioral", "'{name}' 관련 태도와 경험 확인"),
}
_GENERAL = (
    Question("이 회사와 직무에 지원한 이유는 무엇인가요?", None, None, "behavioral", "지원 동기와 직무 이해도 확인",
             ("회사와 직무에서 끌린 점을 구체적으로", "본인의 경험과 연결하기")),
    Question("팀에서 의견이 달랐던 경험과 어떻게 해결했는지 말씀해 주세요.", None, None, "behavioral", "협업과 소통 방식 확인",
             _TIPS_EXPERIENCE),
    Question("최근에 새로 배운 기술과 학습 방법을 소개해 주세요.", None, None, "behavioral", "학습 태도와 성장 가능성 확인",
             ("무엇을 왜 배웠는지", "어떻게 적용해 봤는지")),
)


def interview_rules(criteria: list[CriterionInfo]) -> list[Question]:
    out = []
    for c in criteria:
        template, kind, intent = _BY_CATEGORY.get(c.category, _BY_CATEGORY["other"])
        tips = _TIPS_EXPERIENCE if kind != "technical" else ("핵심 개념을 먼저 설명하기", "실제로 사용한 사례 덧붙이기", "장단점이나 주의할 점 언급하기")
        out.append(Question(template.format(name=c.name), c.id, c.name, kind, intent.format(name=c.name), tips))
    seen, unique = set(), []
    for q in [*out, *_GENERAL]:  # education/experience templates do not depend on the name: keep one each
        if q.question not in seen:
            seen.add(q.question)
            unique.append(q)
    return unique[:MAX_QUESTIONS]


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


def interview_llm(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    excerpts: list[str],
    masked_text: str,
    blocklist: Blocklist,
    llm: LLMClient,
) -> list[Question]:
    """Validated LLM questions. Raises LLMError when fewer than MIN_QUESTIONS survive the checks."""
    prompt = (PROMPT_DIR / "interview_questions.md").read_text(encoding="utf-8")
    out = llm.complete_json(prompt, _llm_input(job_title, job_text, criteria, excerpts), InterviewLlmOut, max_tokens=3000)
    names = {c.id: c.name for c in criteria}
    kept, seen = [], set()
    for q in out.questions:
        text = _clean(q.question, 300)
        if not text or text in seen:
            continue
        intent = _clean(q.intent, 200)
        tips = tuple(t for t in (_clean(x, 150) for x in q.answer_tips) if t)
        # Questions about protected attributes (age, family, origin, …) are dropped, like criteria
        if not check_criterion(text, " ".join([intent, *tips]), blocklist).allowed:
            log.info("interview question dropped by the guardrail: %s", text)
            continue
        cid = q.criterion_id if q.criterion_id in names else None
        verified = verify_quotes([q.cv_quote], masked_text) if q.cv_quote else []
        seen.add(text)
        kept.append(Question(text, cid, names.get(cid), q.kind, intent, tips, verified[0] if verified else None))
    if len(kept) < MIN_QUESTIONS:
        raise LLMError(f"interview: only {len(kept)} usable questions")
    return kept[:MAX_QUESTIONS]


def make_questions(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    masked_text: str,
    embedder: Embedder,
    blocklist: Blocklist,
    llm: LLMClient | None,
) -> tuple[list[Question], str]:
    """(questions, method); method is "llm:<model>" or "rules". LLM failures fall back to the template."""
    if llm is not None:
        query = " ".join([job_title, *(c.name for c in criteria)])
        try:
            excerpts = cv_excerpts(masked_text, query, embedder)
            return interview_llm(job_title, job_text, criteria, excerpts, masked_text, blocklist, llm), f"llm:{llm.model}"
        except LLMError as e:
            log.warning("interview questions by LLM failed, using the template: %s", e)
    return interview_rules(criteria), "rules"
